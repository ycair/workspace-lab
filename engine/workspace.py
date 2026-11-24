from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import quote

from .models import ActionResult

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/forms.body",
]


class WorkspaceConfigError(RuntimeError):
    pass


@dataclass
class GoogleSettings:
    credentials_path: str
    admin_email: str
    dry_run: bool
    allowlist: list[str]

    @classmethod
    def from_env(cls) -> "GoogleSettings":
        path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        admin = os.getenv("GOOGLE_ADMIN_EMAIL", "").strip()
        dry = os.getenv("DRY_RUN", "1").strip().lower() not in ("0", "false", "no")
        raw = os.getenv("ALLOWLIST", "").strip()
        allow = [x.strip().lower() for x in raw.split(",") if x.strip()]
        if not path:
            raise WorkspaceConfigError("GOOGLE_SERVICE_ACCOUNT_JSON 未設定")
        if not os.path.exists(path):
            raise WorkspaceConfigError(f"找不到 service account JSON：{path}")
        if not admin:
            raise WorkspaceConfigError("GOOGLE_ADMIN_EMAIL 未設定（domain-wide delegation 的管理員）")
        if not allow:
            allow = ["@ycair.online"]
        return cls(path, admin, dry, allow)


class MockAdapter:
    """No-network adapter. Every action succeeds with a fake ID."""

    mode = "mock"

    def run(self, step: dict[str, Any]) -> ActionResult:
        actor = step.get("actor", "admin")
        target = step.get("target", "")
        tool = step.get("tool", "Workspace")
        action = step.get("action", "log")
        summary = step.get("summary", action)
        if action == "log":
            return ActionResult(True, "success", tool, actor, target, summary, external_id=f"mock-{uuid.uuid4().hex[:8]}")
        return ActionResult(
            True, "success", tool, actor, target, summary,
            external_id=f"mock-{uuid.uuid4().hex[:8]}",
            payload={"dry_run": False, "mock": True},
        )


class GoogleAdapter:
    """Real Google Workspace adapter. Defaults to dry-run."""

    mode = "real"

    def __init__(self, settings: GoogleSettings):
        try:
            from google.oauth2 import service_account  # noqa: F401
            from googleapiclient.discovery import build  # noqa: F401
        except ImportError as exc:
            raise WorkspaceConfigError(
                "缺少 Google API 套件；請在 .venv 執行 pip install -r requirements.txt"
            ) from exc
        self.settings = settings
        self._services: dict[tuple[str, str, str], Any] = {}

    @classmethod
    def from_env(cls) -> "GoogleAdapter":
        return cls(GoogleSettings.from_env())

    def _is_allowed(self, email: str) -> bool:
        email = (email or "").lower()
        for rule in self.settings.allowlist:
            if rule == "*":
                return True
            if rule.startswith("@"):
                if email.endswith(rule):
                    return True
            elif email == rule:
                return True
        return False

    def _check_recipient(self, email: str) -> None:
        if email and not self._is_allowed(email):
            raise WorkspaceConfigError(f"收件人不在 allowlist：{email}")

    def _service(self, name: str, version: str, actor: str) -> Any:
        key = (name, version, actor)
        if key in self._services:
            return self._services[key]
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            self.settings.credentials_path, scopes=SCOPES
        )
        creds = creds.with_subject(actor)
        svc = build(name, version, credentials=creds, cache_discovery=False)
        self._services[key] = svc
        return svc

    def _share_with_admin(self, file_id: str, actor: str) -> bool:
        """Share a Drive-backed artifact with the admin so screenshots are easy.

        The action still succeeds if sharing fails; the payload records the
        result so the UI can show whether the admin can open it directly.
        """
        if not file_id:
            return False
        admin = (self.settings.admin_email or "").strip().lower()
        actor = (actor or "").strip().lower()
        if not admin or actor == admin:
            return True
        try:
            drive = self._service("drive", "v3", actor)
            drive.permissions().create(
                fileId=file_id,
                body={"type": "user", "role": "writer", "emailAddress": self.settings.admin_email},
                sendNotificationEmail=False,
                fields="id",
            ).execute()
            return True
        except Exception:  # noqa: BLE001
            return False

    def run(self, step: dict[str, Any]) -> ActionResult:
        actor = step.get("actor_email") or step.get("actor", "admin")
        tool = step.get("tool", "Workspace")
        target = step.get("target", "")
        summary = step.get("summary", step.get("action", ""))
        action = step.get("action", "log")
        try:
            if action in ("send_email", "create_draft"):
                recipient = step.get("to", "")
                self._check_recipient(recipient)
            if action == "create_event":
                for attendee in step.get("attendees", []):
                    self._check_recipient(attendee)
            if self.settings.dry_run:
                return ActionResult(
                    True, "dry_run", tool, actor, target,
                    f"[DRY RUN] {summary}", external_id="dry-run",
                    payload={"dry_run": True},
                )
            if action == "send_email":
                return self._send_email(step, actor, tool, target, summary)
            if action == "create_draft":
                return self._create_draft(step, actor, tool, target, summary)
            if action == "create_sheet":
                return self._create_sheet(step, actor, tool, target, summary)
            if action == "create_doc":
                return self._create_doc(step, actor, tool, target, summary)
            if action == "create_event":
                return self._create_event(step, actor, tool, target, summary)
            if action == "create_form":
                return self._create_form(step, actor, tool, target, summary)
            if action == "upload_drive":
                return self._upload_drive(step, actor, tool, target, summary)
            return ActionResult(True, "success", tool, actor, target, summary)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(False, "error", tool, actor, target, summary, error=str(exc))

    # --- individual operations ---
    def _send_email(self, step, actor, tool, target, summary):
        svc = self._service("gmail", "v1", actor)
        msg = MIMEText(step.get("body", ""), "plain", "utf-8")
        msg["to"] = step.get("to", "")
        msg["from"] = actor
        msg["subject"] = step.get("subject", "(no subject)")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        mid = res.get("id", "")
        url = f"https://mail.google.com/mail/u/?authuser={quote(actor)}#sent/{mid}" if mid else ""
        return ActionResult(True, "success", tool, actor, target, summary, external_id=mid,
                            payload={"url": url, "message_id": mid,
                                     "title": step.get("subject", "") or target})

    def _create_draft(self, step, actor, tool, target, summary):
        svc = self._service("gmail", "v1", actor)
        msg = MIMEText(step.get("body", ""), "plain", "utf-8")
        msg["to"] = step.get("to", "")
        msg["from"] = actor
        msg["subject"] = step.get("subject", "(no subject)")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        res = svc.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
        url = f"https://mail.google.com/mail/u/?authuser={quote(actor)}#drafts"
        return ActionResult(True, "success", tool, actor, target, summary, external_id=res.get("id", ""),
                            payload={"url": url, "title": step.get("subject", "") or target})

    def _create_sheet(self, step, actor, tool, target, summary):
        svc = self._service("sheets", "v4", actor)
        title = step.get("title", target)
        res = svc.spreadsheets().create(body={"properties": {"title": title}}).execute()
        sid = res.get("spreadsheetId", "")
        rows = step.get("rows", [])
        if rows:
            svc.spreadsheets().values().update(
                spreadsheetId=sid, range="A1", valueInputOption="RAW",
                body={"values": rows},
            ).execute()
        shared = self._share_with_admin(sid, actor)
        return ActionResult(True, "success", tool, actor, target, summary, external_id=sid,
                            payload={"url": f"https://docs.google.com/spreadsheets/d/{sid}",
                                     "title": title, "shared_with_admin": shared})

    def _create_doc(self, step, actor, tool, target, summary):
        svc = self._service("docs", "v1", actor)
        title = step.get("title", target)
        res = svc.documents().create(body={"title": title}).execute()
        did = res.get("documentId", "")
        body = step.get("body", "")
        if body:
            svc.documents().batchUpdate(
                documentId=did,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": body}}]},
            ).execute()
        shared = self._share_with_admin(did, actor)
        return ActionResult(True, "success", tool, actor, target, summary, external_id=did,
                            payload={"url": f"https://docs.google.com/document/d/{did}",
                                     "title": title, "shared_with_admin": shared})

    def _create_event(self, step, actor, tool, target, summary):
        svc = self._service("calendar", "v3", actor)
        title = step.get("title", target)
        body = {
            "summary": title,
            "start": {"dateTime": step.get("start"), "timeZone": "Asia/Taipei"},
            "end": {"dateTime": step.get("end"), "timeZone": "Asia/Taipei"},
            "attendees": [{"email": e} for e in step.get("attendees", [])],
        }
        if step.get("meet"):
            body["conferenceData"] = {
                "createRequest": {"requestId": f"lab-{uuid.uuid4().hex[:10]}",
                                  "conferenceSolutionKey": {"type": "hangoutsMeet"}}
            }
        res = svc.events().insert(
            calendarId="primary", body=body, conferenceDataVersion=1
        ).execute()
        link = res.get("htmlLink", "")
        return ActionResult(True, "success", tool, actor, target, summary, external_id=res.get("id", ""),
                            payload={"url": link, "htmlLink": link, "title": title})

    def _create_form(self, step, actor, tool, target, summary):
        svc = self._service("forms", "v1", actor)
        title = step.get("title", target)
        res = svc.forms().create(body={"info": {"title": title}}).execute()
        fid = res.get("formId", "")
        questions = step.get("questions", [])
        if questions:
            requests = []
            for i, q in enumerate(questions):
                requests.append({
                    "createItem": {
                        "item": {"title": q, "questionItem": {"question": {"required": False}}},
                        "location": {"index": i},
                    }
                })
            svc.forms().batchUpdate(formId=fid, body={"requests": requests}).execute()
        shared = self._share_with_admin(fid, actor)
        return ActionResult(True, "success", tool, actor, target, summary, external_id=fid,
                            payload={"url": f"https://docs.google.com/forms/d/{fid}/edit",
                                     "title": title,
                                     "responderUri": res.get("responderUri", ""),
                                     "shared_with_admin": shared})

    def _upload_drive(self, step, actor, tool, target, summary):
        from googleapiclient.http import MediaInMemoryUpload
        svc = self._service("drive", "v3", actor)
        media = MediaInMemoryUpload(step.get("content", "").encode("utf-8"),
                                    mimetype=step.get("mime", "text/plain"))
        name = step.get("name", target)
        res = svc.files().create(
            body={"name": name}, media_body=media, fields="id,webViewLink"
        ).execute()
        fid = res.get("id", "")
        shared = self._share_with_admin(fid, actor)
        return ActionResult(True, "success", tool, actor, target, summary, external_id=fid,
                            payload={"url": res.get("webViewLink", ""),
                                     "title": name, "shared_with_admin": shared})
