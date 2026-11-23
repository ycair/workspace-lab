from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from engine.workspace import GoogleAdapter, GoogleSettings, MockAdapter, WorkspaceConfigError


class WorkspaceTest(unittest.TestCase):
    def test_settings_fail_closed_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(WorkspaceConfigError):
                GoogleSettings.from_env()

    def test_allowlist(self):
        adapter = GoogleAdapter(GoogleSettings("/tmp/none.json", "admin@ycair.online", True, ["@ycair.online"]))
        self.assertTrue(adapter._is_allowed("sales@ycair.online"))
        self.assertFalse(adapter._is_allowed("buyer@example.com"))

    def test_mock_adapter_success(self):
        result = MockAdapter().run({"actor": "sales", "tool": "Gmail", "action": "send_email", "target": "x", "summary": "test"})
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "success")

    def test_real_dry_run_does_not_call_api(self):
        adapter = GoogleAdapter(GoogleSettings("/tmp/none.json", "admin@ycair.online", True, ["@ycair.online"]))
        result = adapter.run({
            "actor": "sales", "actor_email": "sales@ycair.online", "tool": "Gmail",
            "action": "send_email", "to": "customer@ycair.online", "target": "customer@ycair.online",
            "summary": "dry run", "body": "hi", "subject": "test",
        })
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "dry_run")

    def test_real_from_env_dry_run(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{}")
            path = f.name
        try:
            with patch.dict(os.environ, {
                "GOOGLE_SERVICE_ACCOUNT_JSON": path,
                "GOOGLE_ADMIN_EMAIL": "admin@ycair.online",
                "DRY_RUN": "1",
                "ALLOWLIST": "@ycair.online",
            }, clear=True):
                adapter = GoogleAdapter.from_env()
                result = adapter.run({
                    "actor": "sales", "actor_email": "sales@ycair.online", "tool": "Gmail",
                    "action": "send_email", "to": "customer@ycair.online",
                    "target": "customer@ycair.online", "summary": "dry", "body": "hi", "subject": "t",
                })
                self.assertEqual(result.status, "dry_run")
        finally:
            os.unlink(path)

    def test_real_allowlist_blocks_external(self):
        adapter = GoogleAdapter(GoogleSettings("/tmp/none.json", "admin@ycair.online", True, ["@ycair.online"]))
        result = adapter.run({
            "actor": "sales", "actor_email": "sales@ycair.online", "tool": "Gmail",
            "action": "send_email", "to": "buyer@example.com", "target": "buyer@example.com",
            "summary": "blocked", "body": "hi", "subject": "test",
        })
        self.assertFalse(result.ok)
        self.assertIn("allowlist", result.error)


if __name__ == "__main__":
    unittest.main()
