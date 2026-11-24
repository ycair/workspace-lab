#!/usr/bin/env python3
"""Validate service account + domain-wide delegation for WorkspaceLab."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import load_env  # noqa: E402
from engine.workspace import GoogleAdapter, GoogleSettings, WorkspaceConfigError  # noqa: E402

load_env(ROOT / ".env")

try:
    settings = GoogleSettings.from_env()
    print("settings: OK")
    print("admin:", settings.admin_email)
    print("dry_run:", settings.dry_run)
    print("allowlist:", settings.allowlist)
    try:
        import json
        with open(settings.credentials_path, encoding="utf-8") as f:
            key = json.load(f)
        print("client_id:", key.get("client_id", "(not found)"))
        print("service_account:", key.get("client_email", "(not found)"))
    except Exception as exc:  # noqa: BLE001
        print("key metadata: WARN", type(exc).__name__, exc)
    adapter = GoogleAdapter(settings)
    gmail = adapter._service("gmail", "v1", settings.admin_email)
    profile = gmail.users().getProfile(userId="me").execute()
    print("gmail profile: OK", profile.get("emailAddress"), profile.get("messagesTotal"))
    for name, version in (
        ("drive", "v3"), ("docs", "v1"), ("sheets", "v4"),
        ("slides", "v1"), ("calendar", "v3"), ("forms", "v1"),
    ):
        try:
            adapter._service(name, version, settings.admin_email)
            print(f"{name}: build OK")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: BUILD WARN {type(exc).__name__}: {exc}")
    print("RESULT: real adapter can authenticate.")
except WorkspaceConfigError as exc:
    print("CONFIG ERROR:", exc)
    raise SystemExit(2)
except Exception as exc:  # noqa: BLE001
    print("AUTH ERROR:", type(exc).__name__, exc)
    raise SystemExit(3)
