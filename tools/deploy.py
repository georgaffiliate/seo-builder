#!/usr/bin/env python3
"""Upload a built site to the hosting panel.

Steps (same as the manual procedure):
  1. GET  {panel}/api/v1/stores?q=<domain>  -> store id (must have can_upload:true)
  2. zip sites/<domain> (without .DS_Store)
  3. POST {panel}/api/v1/stores/<id>/zip    (panel rejects .htaccess - that is fine,
     the custom 404 works through 404.php)
  4. best-effort GET https://<domain>/ to report the public status code
     (DNS / IP whitelist may not be ready yet - this never fails the upload)

Secrets: PANEL_API_KEY env, or a file via PANEL_API_KEY_FILE
(defaults tried: /run/secrets/panel_api_key, ./.panel_api_key).

Output: progress goes to stderr; a single JSON object is printed to stdout
(the API wrapper parses it). Exit 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PANEL_DEFAULT = os.environ.get("PANEL_API_URL", "https://florentina-tr.shop")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _load_key() -> str | None:
    key = os.environ.get("PANEL_API_KEY", "").strip()
    if key:
        return key
    candidates = [os.environ.get("PANEL_API_KEY_FILE", ""),
                  "/run/secrets/panel_api_key",
                  str(ROOT / ".panel_api_key")]
    for c in candidates:
        if c and pathlib.Path(c).is_file():
            for line in pathlib.Path(c).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    return line.split("=", 1)[1].strip() if "=" in line else line.strip()
    _log("!! no panel API key: set PANEL_API_KEY or PANEL_API_KEY_FILE")
    return None


def _request(url: str, key: str, *, method: str = "GET", data: bytes | None = None,
             content_type: str | None = None, timeout: int = 60) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    # panel sits behind Cloudflare: default "Python-urllib/x" UA trips error 1010
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                 "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e.reason}") from e


def _find_store(panel: str, key: str, domain: str) -> dict:
    code, body = _request(f"{panel}/api/v1/stores?q={domain}", key)
    if code != 200:
        raise RuntimeError(f"stores lookup HTTP {code}: {body[:300]!r}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"stores lookup: non-JSON response") from e
    items = data if isinstance(data, list) else next(
        (data[k] for k in ("stores", "data", "items", "results")
         if isinstance(data.get(k), list)), [])
    if not isinstance(items, list):
        raise RuntimeError("stores lookup: unexpected response shape")
    matches = [s for s in items if isinstance(s, dict)
               and str(s.get("domain", s.get("name", ""))).lower().rstrip("/") == domain]
    if not matches and len(items) == 1:
        matches = items
    if not matches:
        raise RuntimeError(f"store for {domain} not found (create it in the panel first)")
    return matches[0]


def _zip_site(site: pathlib.Path, domain: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(site.rglob("*")):
            if p.is_file() and p.name != ".DS_Store":
                z.write(p, p.relative_to(site).as_posix())
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--site", required=True, help="path to sites/<domain>")
    ap.add_argument("--panel", default=PANEL_DEFAULT)
    a = ap.parse_args()

    result: dict = {"ok": False, "domain": a.domain, "panel": a.panel}
    site = pathlib.Path(a.site)
    pages = list(site.glob("*.php")) + list(site.glob("*.html")) if site.is_dir() else []
    if not pages:
        result["error"] = f"built site not found at {site}"
        print(json.dumps(result))
        sys.exit(1)

    try:
        key = _load_key()
        if not key:
            result["error"] = "no panel API key: set PANEL_API_KEY (env) or PANEL_API_KEY_FILE"
            print(json.dumps(result))
            sys.exit(1)

        _log("== 1/4 looking up the store")
        store = _find_store(a.panel, key, a.domain)
        sid = store.get("id", store.get("store_id"))
        if sid is None:
            raise RuntimeError(f"store entry has no id: {store}")
        result["store_id"] = sid
        _log(f"   store id: {sid}")

        if not store.get("can_upload", True):
            result["error"] = "can_upload is false for this store"
            print(json.dumps(result))
            sys.exit(1)
        result["can_upload"] = True

        _log("== 2/4 zipping the site")
        blob = _zip_site(site, a.domain)
        _log(f"   {len(blob)} bytes")

        _log("== 3/4 uploading the zip")
        boundary = uuid.uuid4().hex
        part = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{a.domain}.zip"\r\nContent-Type: application/zip\r\n\r\n')
        body = part.encode() + blob + f"\r\n--{boundary}--\r\n".encode()
        code, resp = _request(f"{a.panel}/api/v1/stores/{sid}/zip", key, method="POST",
                              data=body, content_type=f"multipart/form-data; boundary={boundary}",
                              timeout=120)
        result["upload_http"] = code
        if code != 200:
            result["error"] = f"upload HTTP {code}: {resp[:300]!r}"
            print(json.dumps(result))
            sys.exit(1)
        result["upload_response"] = resp[:500].decode("utf-8", "replace")
        result["note_htaccess"] = ".htaccess rejected by the panel - expected (custom 404 via 404.php)"

        _log("== 4/4 public status check (best effort)")
        url = f"https://{a.domain}/"
        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "seo-builder/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                result["public_check"] = {"url": url, "status": r.status}
        except Exception as exc:  # noqa: BLE001 - DNS may simply not be ready
            result["public_check"] = {"url": url, "status": None, "note": str(exc)[:200],
                                      "hint": "DNS / IP whitelist may need manual setup"}

        # The panel console may regenerate sitemap.xml without the .php suffix
        # (observed on legacy sites). Best-effort comparison against the local file.
        try:
            with urllib.request.urlopen(f"https://{a.domain}/sitemap.xml", timeout=20) as r:
                live_locs = re.findall(r"<loc>([^<]+)</loc>", r.read().decode("utf-8", "replace"))
            want_locs = re.findall(r"<loc>([^<]+)</loc>", (site / "sitemap.xml").read_text(encoding="utf-8"))
            if want_locs and live_locs and sorted(live_locs) != sorted(want_locs):
                result["sitemap_note"] = ("panel rewrote sitemap.xml (live != local); extensionless "
                                          "URLs are tolerated only via the per-page 301 guard")
                result["sitemap_live_first"] = live_locs[:4]
        except Exception:  # noqa: BLE001 - DNS may simply not be ready
            pass

        result["ok"] = True
        _log("== upload OK")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:500]

    print(json.dumps(result))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
