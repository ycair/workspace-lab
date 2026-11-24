from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.report import build_html_report, build_report  # noqa: E402
from engine.simulator import Simulator  # noqa: E402
from engine.store import Store  # noqa: E402
from engine.workspace import GoogleAdapter, GoogleSettings, MockAdapter, WorkspaceConfigError  # noqa: E402


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


load_env(ROOT / ".env")
STORE = Store(ROOT / "data" / "workspace_lab.db")
SIM = Simulator(STORE)
SIM.load_latest()
WEB = ROOT / "web"


def real_status() -> dict:
    try:
        s = GoogleSettings.from_env()
        return {"configured": True, "dry_run": s.dry_run, "allowlist": s.allowlist,
                "admin": s.admin_email}
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkspaceLab/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---------- helpers ----------
    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _static(self, rel: str):
        rel = rel.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = (WEB / rel).resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.exists() or target.is_dir():
            self._json({"error": "not found"}, 404)
            return
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        if target.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/state":
            self._json(SIM.state())
        elif path == "/api/personas":
            self._json({"personas": SIM.state()["personas"]})
        elif path == "/api/actions":
            q = parse_qs(parsed.query)
            limit = int(q.get("limit", ["200"])[0])
            eid = SIM.experiment_id
            self._json({"actions": STORE.list_actions(eid, limit) if eid else []})
        elif path == "/api/metrics":
            eid = SIM.experiment_id
            self._json({"metrics": STORE.list_metrics(eid) if eid else []})
        elif path == "/api/events":
            eid = SIM.experiment_id
            self._json({"events": STORE.list_events(eid) if eid else []})
        elif path == "/api/config":
            self._json({"real": real_status(), "scenarios": list_scenarios()})
        elif path == "/api/report":
            q = parse_qs(parsed.query)
            fmt = q.get("format", ["md"])[0]
            company = q.get("company", [None])[0]
            if fmt == "html":
                text = build_html_report(STORE, SIM.experiment_id, company)
                ctype = "text/html; charset=utf-8"
                filename = "workspacelab-report.html"
            else:
                text = build_report(STORE, SIM.experiment_id, company)
                ctype = "text/markdown; charset=utf-8"
                filename = "workspacelab-report.md"
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if q.get("download", ["0"])[0] == "1":
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/health":
            self._json({"ok": True, "status": SIM.status, "experiment": SIM.experiment_id})
        elif path.startswith("/api/"):
            self._json({"error": "unknown endpoint"}, 404)
        else:
            self._static(path)

    # ---------- POST ----------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()
        if path == "/api/start":
            scenario = body.get("scenario", "quote")
            mode = body.get("mode", "mock")
            delay = float(body.get("delay", 1.2))
            company = str(body.get("company", "")).strip()
            if mode == "real":
                try:
                    adapter = GoogleAdapter.from_env()
                except WorkspaceConfigError as exc:
                    self._json({"error": str(exc), "real": real_status()}, 400)
                    return
            else:
                adapter = MockAdapter()
            state = SIM.start(scenario, mode, adapter, delay, company=company)
            self._json(state)
        elif path == "/api/pause":
            self._json(SIM.pause())
        elif path == "/api/resume":
            self._json(SIM.resume())
        elif path == "/api/reset":
            self._json(SIM.reset())
        elif path == "/api/event":
            typ = body.get("type", "unknown")
            payload = body.get("payload", "")
            self._json(SIM.inject_event(typ, payload))
        else:
            self._json({"error": "unknown endpoint"}, 404)


def list_scenarios():
    from engine.scenarios import SCENARIOS
    return [
        {"id": s["id"], "name": s["name"], "pain": s["pain"], "gain": s["gain"],
         "description": s["description"], "steps": len(s["steps"])}
        for s in SCENARIOS.values()
    ]


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8787"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"WorkspaceLab on http://{host}:{port}")
    print(f"real: {real_status()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
        STORE.close()


if __name__ == "__main__":
    main()
