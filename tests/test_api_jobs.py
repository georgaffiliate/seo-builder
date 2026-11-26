"""Черга /build: один активний job на домен, queue_pos, cancel і healthz.

Запуск (без залежностей, stdlib):
    python3 -m pytest tests/test_api_jobs.py      # якщо є pytest
    python3 tests/test_api_jobs.py                # або як звичайний скрипт
"""
from __future__ import annotations

import json
import pathlib
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import api  # noqa: E402


def _server():
    srv = api.ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _call(port: int, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_dedupe_queue_and_cancel():
    api.API_TOKEN = ""          # у тесті не носимо токен
    srv, port = _server()
    try:
        domain = f"dedupe-{uuid.uuid4().hex[:10]}.site"
        body = {"brand": "Dedupe Test", "lang": "en", "domain": domain}
        code, first = _call(port, "POST", "/build", body)
        assert code == 202 and first["job_id"], first

        # повторний POST того ж домену не створює другу збірку
        code, again = _call(port, "POST", "/build", body)
        assert code == 200 and again["deduped"] is True, again
        assert again["job_id"] == first["job_id"]

        code, jobs = _call(port, "GET", "/jobs")
        assert code == 200
        mine = next(j for j in jobs["jobs"] if j["job_id"] == first["job_id"])
        assert mine["status"] == "queued" and mine["queue_pos"] == 1, mine
        assert mine["wait_sec"] is not None and mine["run_sec"] is None

        code, health = _call(port, "GET", "/healthz")
        assert code == 200 and health["queued"] >= 1, health
        assert any(j["job_id"] == first["job_id"] for j in health["queue"])

        # скасований job звільняє домен — новий POST створює нову збірку
        code, cancelled = _call(port, "POST", f"/jobs/{first['job_id']}/cancel")
        assert code == 200 and cancelled["status"] == "failed", cancelled
        code, second = _call(port, "POST", "/build", body)
        assert code == 202 and second["job_id"] != first["job_id"], second
    finally:
        srv.shutdown()


def _drain_queue():
    while True:
        try:
            api._queue.get_nowait()
        except queue.Empty:
            return


def _cleanup_job(jid: str):
    _drain_queue()
    api._jobs.pop(jid, None)
    with api._lock:
        api._queued_order[:] = [x for x in api._queued_order if x != jid]


def test_retry_budget():
    """A failed build goes to the END of the queue and gives up after 3 attempts."""
    _drain_queue()
    jid = uuid.uuid4().hex
    job = {"job_id": jid, "status": "running", "domain": "retry-test.site",
           "request": {"brand": "Retry", "lang": "en", "domain": "retry-test.site"},
           "log": [], "created_at": time.time(), "attempt": 1}
    api._jobs[jid] = job
    try:
        assert api._retry_or_fail(job, "boom 1") is True
        assert job["status"] == "queued" and job["attempt"] == 2, job
        assert api._queued_order[-1] == jid
        job["status"] = "running"
        assert api._retry_or_fail(job, "boom 2") is True
        assert job["attempt"] == 3 and job["status"] == "queued"
        job["status"] = "running"
        assert api._retry_or_fail(job, "boom 3") is False
        assert job["status"] == "failed" and "after 3 attempt" in job["error"], job
        assert job["retryable"] is False and job["failure_kind"] == "build", job
        deploy_job = {"job_id": uuid.uuid4().hex, "status": "running", "log": [],
                      "attempt": 3}
        assert api._retry_or_fail(deploy_job, "panel down", retryable=True,
                                  kind="deploy") is False
        assert deploy_job["retryable"] is True and deploy_job["failure_kind"] == "deploy"
        cancelled = {"job_id": uuid.uuid4().hex, "status": "running", "log": [],
                     "attempt": 1, "cancelled": True}
        assert api._retry_or_fail(cancelled, "cancelled by operator") is False
        assert cancelled["status"] == "failed" and cancelled["retryable"] is False
    finally:
        _cleanup_job(jid)


def test_execute_requeues_on_build_failure():
    _drain_queue()
    orig = api._run
    api._run = lambda *a, **k: (1, "", "boom")
    jid = uuid.uuid4().hex
    job = {"job_id": jid, "status": "queued", "domain": "retry-exec.site",
           "request": {"brand": "Retry", "lang": "en", "domain": "retry-exec.site"},
           "log": [], "created_at": time.time(), "attempt": 1}
    api._jobs[jid] = job
    try:
        api._execute(job)
        assert job["status"] == "queued" and job["attempt"] == 2, job
        api._execute(job)
        assert job["status"] == "queued" and job["attempt"] == 3, job
        api._execute(job)
        assert job["status"] == "failed" and "after 3 attempt" in job["error"], job
        assert job["retryable"] is False and job["failure_kind"] == "build", job
    finally:
        api._run = orig
        _cleanup_job(jid)


if __name__ == "__main__":
    test_dedupe_queue_and_cancel()
    test_retry_budget()
    test_execute_requeues_on_build_failure()
    print("OK: dedupe / queue_pos / cancel / healthz / retry budget")
