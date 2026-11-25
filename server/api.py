#!/usr/bin/env python3
"""HTTP API wrapper around the site factory pipeline.

A client container sends POST /build with the same parameters as the CLI
(--brand/--lang/--cc/--geo/--currency/--domain/--with-llm). The service runs
gen_plan.py (plan -> content -> assemble -> gates -> icons -> profile), then
optionally uploads the built site to the hosting panel (tools/deploy.py) and
returns a JSON verdict.

Endpoints:
  POST /build       enqueue a build  {"job_id":..., "status":"queued"}
  POST /build?wait=1  same, but hold the connection until the job finishes
  POST /blog/article  generate ONE blog article as content JSON (no markup)
  GET  /jobs/<id>   job status / result
  GET  /healthz     liveness

Stdlib only - no extra dependencies.
"""
from __future__ import annotations

import json
import os
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent

API_TOKEN = os.environ.get("API_TOKEN", "").strip()
BUILD_TIMEOUT = int(os.environ.get("BUILD_TIMEOUT", "3600"))
DEPLOY_TIMEOUT = int(os.environ.get("DEPLOY_TIMEOUT", "600"))
LOG_TAIL = 4000

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

_lock = threading.Lock()
_jobs: dict[str, dict] = {}
# running child processes live OUTSIDE the job dict: json.dumps() must never meet a Popen
_procs: dict[str, subprocess.Popen] = {}
_queue: "queue.Queue[str]" = queue.Queue()
# Порядок черги для діагностики (queue_pos у /jobs). Тримаємо окремо, бо queue.Queue
# не дає зазирнути всередину; елементи знімаються, коли воркер бере job або його скасовано.
_queued_order: list[str] = []


# --------------------------------------------------------------------------- jobs

def _log(job: dict, line: str) -> None:
    job["log"].append(line)
    if len(job["log"]) > 400:
        job["log"] = job["log"][-400:]


def _tail(text: str, limit: int = LOG_TAIL) -> str:
    return text[-limit:] if len(text) > limit else text


ACTIVE_STATES = ("queued", "running", "deploying")


def _active_job_for(domain: str) -> dict | None:
    """Уже поставлене в чергу/збирається завдання для цього домену (захист від дублів)."""
    with _lock:
        for job in _jobs.values():
            if job.get("domain") == domain and job["status"] in ACTIVE_STATES:
                return job
    return None


def _job_summary(job: dict, order: list[str] | None = None) -> dict:
    """Компактний стан job для панелі: хто збирається, хто в черзі і скільки вже чекає."""
    now = time.time()
    started, finished = job.get("started_at"), job.get("finished_at")
    created = job.get("created_at") or now
    pos = None
    if order is not None and job["job_id"] in order:
        pos = order.index(job["job_id"]) + 1
    return {
        "job_id": job["job_id"],
        "domain": job.get("domain"),
        "status": job["status"],
        "stage": job.get("stage"),
        "queue_pos": pos,
        "created_at": created,
        "started_at": started,
        "finished_at": finished,
        # скільки чекав у черзі; для тих, хто ще чекає — скільки чекає зараз
        "wait_sec": int((started if started else now) - created),
        # скільки вже збирається/збирався
        "run_sec": int((finished if finished else now) - started) if started else None,
        "error": job.get("error"),
        "pages": job.get("pages"),
        "active": job["status"] in ACTIVE_STATES,
    }


def _run(cmd: list[str], timeout: int, job: dict | None = None) -> tuple[int, str, str]:
    """Run a child with a hard timeout; the handle is kept so the job can be cancelled."""
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    jid = (job or {}).get("job_id")
    if jid:
        with _lock:
            _procs[jid] = p
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        out, err = p.communicate()
        raise
    finally:
        if jid:
            with _lock:
                _procs.pop(jid, None)
    return p.returncode, out or "", err or ""


def _kill_tree(p: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _worker() -> None:
    while True:
        try:
            jid = _queue.get()
        except Exception:  # noqa: BLE001 - the queue thread must never die silently
            time.sleep(1.0)
            continue
        job = _jobs.get(jid)
        if job is None:
            continue
        with _lock:
            try:
                _queued_order.remove(jid)
            except ValueError:
                pass
        if job["status"] != "queued":   # скасовано, поки стояв у черзі
            _log(job, "== skipped: cancelled before start")
            job.setdefault("finished_at", time.time())
            continue
        job["started_at"] = time.time()
        try:
            _execute(job)
        except Exception as exc:  # noqa: BLE001 - worker must never die
            job["status"] = "failed"
            job["error"] = f"internal error: {exc}"
            _log(job, f"!! internal error: {exc}")
        finally:
            job["finished_at"] = time.time()
            if job["status"] in ("done", "failed"):
                job["stage"] = job["status"]
            _log(job, f"== job {jid} finished: {job['status']}")


def _execute(job: dict) -> None:
    req = job["request"]
    domain = req["domain"]

    job["status"] = "running"
    job["stage"] = "build"
    _log(job, "== building: gen_plan.py --build")
    cmd = [sys.executable, str(ROOT / "gen_plan.py"),
           "--brand", req["brand"], "--lang", req["lang"], "--domain", domain]
    for flag, key in (("--geo", "geo"), ("--cc", "cc"), ("--currency", "currency")):
        val = req.get(key)
        # "auto" (or nothing) means "let the country decide": JP→JPY, GB→GBP, …
        if val and str(val).lower() != "auto":
            cmd += [flag, str(val)]
    if req.get("seed"):
        cmd += ["--seed", str(req["seed"])]
    if req.get("calculator") in ("on", "off"):
        cmd += ["--calculator", req["calculator"]]
    if req.get("force"):
        cmd += ["--force"]
    if req.get("llm_model"):
        cmd += ["--llm-model", req["llm_model"]]
    if req.get("llm_provider"):
        cmd += ["--llm-provider", req["llm_provider"]]
    if req.get("with_llm"):
        cmd += ["--with-llm"]
    else:
        cmd += ["--build"]
    if req.get("blog"):
        cmd += ["--blog"]

    try:
        code, out, err = _run(cmd, BUILD_TIMEOUT, job)
    except subprocess.TimeoutExpired:
        job["status"] = "failed"
        job["error"] = f"build timed out after {BUILD_TIMEOUT}s"
        return

    job["build_log"] = _tail(out + ("\n[stderr]\n" + err if err.strip() else ""))
    m = re.search(r"PLAN OK .*\(seed (\d+)\)", out)
    if m:
        job["seed"] = int(m.group(1))
    _log(job, f"== gen_plan exit {code}")

    if code != 0:
        job["status"] = "failed"
        job["error"] = "build failed (see build_log); nothing deployed"
        return

    site = ROOT / "sites" / domain
    job["pages"] = len(list(site.glob("*.php"))) + len(list(site.glob("*.html"))) \
        if site.is_dir() else 0

    if req.get("deploy"):
        job["status"] = "deploying"
        job["stage"] = "deploy"
        _log(job, "== deploying via tools/deploy.py")
        dcmd = [sys.executable, str(ROOT / "tools" / "deploy.py"),
                "--domain", domain, "--site", str(site)]
        try:
            dcode, dout, derr = _run(dcmd, DEPLOY_TIMEOUT, job)
        except subprocess.TimeoutExpired:
            job["status"] = "failed"
            job["error"] = "site built, but deploy timed out"
            job["deploy"] = {"ok": False, "error": "deploy timed out"}
            return
        job["deploy_log"] = _tail(derr)
        dep = None
        for line in reversed(dout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    dep = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass
        if dep is None:
            dep = {"ok": False, "error": f"deploy exit {dcode} (see deploy_log)"}
        job["deploy"] = dep
        _log(job, f"== deploy exit {dcode}")
        if dcode != 0 or not dep.get("ok"):
            job["status"] = "failed"
            job["error"] = "site built, but deploy failed (see deploy)"
            return

    job["status"] = "done"


# --------------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "seo-builder/1.0"

    def log_message(self, fmt, *args):  # quieter default logging
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # -- helpers ------------------------------------------------------------
    def _auth(self) -> bool:
        if not API_TOKEN:
            return True
        h = self.headers.get("Authorization", "")
        return h == f"Bearer {API_TOKEN}"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _job_public(self, job: dict) -> dict:
        # only JSON-safe fields: a Popen (or any live object) in the job dict used to
        # raise "Object of type Popen is not JSON serializable" and Caddy answered 502
        pub = {k: v for k, v in job.items()
               if k != "log" and not k.startswith("_")
               and isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        with _lock:
            order = list(_queued_order)
        pub.update(_job_summary(job, order))
        pub["log_tail"] = "\n".join(job["log"][-12:])
        return pub

    # -- routes -------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            with _lock:
                order = list(_queued_order)
                all_jobs = list(_jobs.values())
            running = [_job_summary(j, order) for j in all_jobs
                       if j["status"] in ("running", "deploying")]
            queue = [_job_summary(_jobs[jid], order) for jid in order
                     if jid in _jobs and _jobs[jid]["status"] == "queued"]
            return self._send(200, {"ok": True, "service": "seo-builder",
                                    "queued": len(queue), "jobs": len(all_jobs),
                                    "running": running, "queue": queue})
        if path == "/jobs":
            if not self._auth():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            with _lock:
                order = list(_queued_order)
                all_jobs = list(_jobs.values())
            jobs = [_job_summary(j, order) for j in all_jobs]
            # спочатку те, що зараз робиться, далі черга за порядком, далі завершені
            rank = {"running": 0, "deploying": 0, "queued": 1}
            jobs.sort(key=lambda j: (rank.get(j["status"], 2),
                                     j["queue_pos"] if j["queue_pos"] else 10**6,
                                     -(j.get("finished_at") or j.get("created_at") or 0)))
            return self._send(200, {"ok": True, "queued": sum(1 for j in jobs if j["status"] == "queued"),
                                    "jobs": jobs})
        m = re.fullmatch(r"/jobs/([a-f0-9-]{16,})", path)
        if m:
            if not self._auth():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            job = _jobs.get(m.group(1))
            if job is None:
                return self._send(404, {"ok": False, "error": "job not found"})
            code = 200 if job["status"] in ("done", "failed") else 202
            return self._send(code, self._job_public(job))
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        cancel = re.fullmatch(r"/jobs/([a-f0-9-]{16,})/cancel", self.path.split("?", 1)[0])
        if cancel:
            if not self._auth():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            job = _jobs.get(cancel.group(1))
            if job is None:
                return self._send(404, {"ok": False, "error": "job not found"})
            with _lock:
                proc = _procs.get(job["job_id"])
                try:
                    _queued_order.remove(job["job_id"])   # скасоване в черзі не має займати місце
                except ValueError:
                    pass
            if proc is not None and proc.poll() is None:
                _kill_tree(proc)
            if job["status"] not in ("done", "failed"):
                job["status"] = "failed"
                job["error"] = "cancelled by operator"
                job["finished_at"] = time.time()
                _log(job, "!! cancelled by operator")
            return self._send(200, {"ok": True, "job_id": job["job_id"], "status": job["status"]})
        if self.path.split("?", 1)[0] == "/blog/article":
            if not self._auth():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 200_000:
                    return self._send(413, {"ok": False, "error": "payload too large"})
                req = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(400, {"ok": False, "error": "invalid JSON body"})
            err = _validate_article_req(req)
            if err:
                return self._send(400, {"ok": False, "error": err})
            try:
                from article import ArticleError, generate as generate_article
                payload = generate_article(req)
            except ArticleError as e:
                return self._send(502, {"ok": False, "error": str(e)[:800]})
            except Exception as e:  # noqa: BLE001  (never leak a traceback to the panel)
                return self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"[:800]})
            return self._send(200, {"ok": True, "article": payload,
                                    "domain": req.get("domain")})

        if self.path.split("?", 1)[0] != "/build":
            return self._send(404, {"ok": False, "error": "not found"})
        if not self._auth():
            return self._send(401, {"ok": False, "error": "unauthorized"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                return self._send(413, {"ok": False, "error": "payload too large"})
            req = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"ok": False, "error": "invalid JSON body"})

        err = _validate(req)
        if err:
            return self._send(400, {"ok": False, "error": err})

        domain = req["domain"]
        # Дубль по домену: якщо збірка вже в черзі або виконується — повертаємо її job_id.
        # Це головний захист від «ретраїв», які плодили по кілька збірок одного сайту.
        active = _active_job_for(domain)
        if active is not None:
            return self._send(200, {"ok": True, "job_id": active["job_id"], "status": active["status"],
                                    "domain": domain, "deduped": True,
                                    "poll": f"/jobs/{active['job_id']}"})

        if (ROOT / "plans" / f"{domain}.json").exists() and not req.get("force"):
            return self._send(409, {"ok": False,
                                    "error": f"domain {domain} already has a plan; pass force=true to rebuild"})

        jid = uuid.uuid4().hex
        job = {"job_id": jid, "status": "queued", "domain": domain, "stage": "queued",
               "request": req, "log": [], "created_at": time.time()}
        deduped = False
        with _lock:
            again = next((j for j in _jobs.values()
                          if j.get("domain") == domain and j["status"] in ACTIVE_STATES), None)
            if again is not None:          # паралельний POST встиг першим
                jid, job, deduped = again["job_id"], again, True
            else:
                _jobs[jid] = job
                _queued_order.append(jid)
        if deduped:
            return self._send(200, {"ok": True, "job_id": jid, "status": job["status"],
                                    "domain": domain, "deduped": True, "poll": f"/jobs/{jid}"})

        _queue.put(jid)

        wait = self.path.split("?", 1)[-1] if "?" in self.path else ""
        if "wait=1" in wait or req.get("wait"):
            deadline = time.time() + BUILD_TIMEOUT + DEPLOY_TIMEOUT + 30
            while time.time() < deadline and job["status"] in ("queued", "running", "deploying"):
                time.sleep(1.0)
            code = 200 if job["status"] in ("done", "failed") else 202
            return self._send(code, self._job_public(job))
        return self._send(202, {"ok": True, "job_id": jid, "status": "queued",
                                "domain": domain, "poll": f"/jobs/{jid}"})


def _validate_article_req(req: dict) -> str | None:
    if not isinstance(req, dict):
        return "body must be a JSON object"
    for key in ("lang", "brand"):
        v = req.get(key)
        if not isinstance(v, str) or not v.strip():
            return f"missing required field: {key}"
    for key in ("domain", "hub_label"):
        if key in req and req[key] is not None and not isinstance(req[key], str):
            return f"field {key} must be a string"
    existing = req.get("existing")
    if existing is not None and not isinstance(existing, list):
        return "existing must be an array"
    if isinstance(existing, list) and len(existing) > 60:
        return "existing has too many entries"
    topic = req.get("topic")
    if topic is not None and not isinstance(topic, dict):
        return "topic must be an object or null"
    return None


def _validate(req: dict) -> str | None:
    if not isinstance(req, dict):
        return "body must be a JSON object"
    for key in ("brand", "lang", "domain"):
        v = req.get(key)
        if not isinstance(v, str) or not v.strip():
            return f"missing required field: {key}"
    d = req["domain"].strip().lower()
    if not DOMAIN_RE.fullmatch(d):
        return "invalid domain (expected like infinity-shop.site)"
    req["domain"] = d
    for key in ("brand", "lang", "geo", "cc", "currency", "llm_model", "llm_provider"):
        if key in req and not isinstance(req[key], str):
            return f"field {key} must be a string"
    if req.get("calculator") not in (None, "auto", "on", "off"):
        return "calculator must be auto|on|off"
    if req.get("llm_provider") not in (None, "", "auto", "http", "cli"):
        return "llm_provider must be auto|http|cli"
    if "seed" in req and not isinstance(req["seed"], int):
        return "seed must be an integer"
    if "blog" in req and not isinstance(req["blog"], bool):
        return "blog must be a boolean"
    return None


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8080"))
    threading.Thread(target=_worker, daemon=True).start()
    if not API_TOKEN:
        print("WARN: API_TOKEN is empty - /build is open to anyone with network access",
              file=sys.stderr)
    print(f"seo-builder API listening on :{port} (root {ROOT})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
