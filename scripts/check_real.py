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
    adapter = GoogleAdapter(settings)
    gmail = adapter._service("gmail", "v1", settings.admin_email)
    profile = gmail.users().getProfile(userId="me").execute()
    print("gmail profile: OK", profile.get("emailAddress"), profile.get("messagesTotal"))
    print("RESULT: real adapter can authenticate.")
except WorkspaceConfigError as exc:
    print("CONFIG ERROR:", exc)
    raise SystemExit(2)
except Exception as exc:  # noqa: BLE001
    print("AUTH ERROR:", type(exc).__name__, exc)
    raise SystemExit(3)
