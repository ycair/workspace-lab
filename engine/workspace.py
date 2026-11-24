from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
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
    "https://www.googleapis.com/auth/presentations",
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
    chat_webhook_url: str = ""

    @classmethod
    def from_env(cls) -> "GoogleSettings":
        path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        admin = os.getenv("GOOGLE_ADMIN_EMAIL", "").strip()
        dry = os.getenv("DRY_RUN", "1").strip().lower() not in ("0", "false", "no")
        raw = os.getenv("ALLOWLIST", "").strip()
        allow = [x.strip().lower() for x in raw.split(",") if x.strip()]
        chat = os.getenv("CHAT_WEBHOOK_URL", "").strip()
        if not path:
            raise WorkspaceConfigError("GOOGLE_SERVICE_ACCOUNT_JSON 未設定")
        if not os.path.exists(path):
            raise WorkspaceConfigError(f"找不到 service account JSON：{path}")
        if not admin:
            raise WorkspaceConfigError("GOOGLE_ADMIN_EMAIL 未設定（domain-wide delegation 的管理員）")
        if not allow:
            allow = ["@ycair.online"]
        return cls(path, admin, dry, allow, chat)


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
        self.last_message_id = ""
        self.last_draft_id = ""
        self.label_ids: dict[str, str] = {}
        self.created_files: list[dict[str, str]] = []
        self.folder_id = ""

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

    def _track_file(self, file_id: str, actor: str, title: str, kind: str) -> None:
        if file_id:
            self.created_files.append({"id": file_id, "actor": actor, "title": title, "kind": kind})

    def _label_id(self, svc, name: str) -> str:
        if name in self.label_ids:
            return self.label_ids[name]
        labels = svc.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label.get("name") == name:
                lid = label.get("id", "")
                if lid:
                    self.label_ids[name] = lid
                return lid
        res = svc.users().labels().create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).execute()
        lid = res.get("id", "")
        if lid:
            self.label_ids[name] = lid
        return lid

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
            if action == "create_slides":
                return self._create_slides(step, actor, tool, target, summary)
            if action == "create_event":
                return self._create_event(step, actor, tool, target, summary)
            if action == "create_form":
                return self._create_form(step, actor, tool, target, summary)
            if action == "label_message":
                return self._label_message(step, actor, tool, target, summary)
            if action == "send_draft":
                return self._send_draft(step, actor, tool, target, summary)
            if action == "post_chat":
                return self._post_chat(step, actor, tool, target, summary)
            if action == "archive_folder":
                return self._archive_folder(step, actor, tool, target, summary)
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
        self.last_message_id = mid
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
        did = res.get("id", "")
        self.last_draft_id = did
        url = f"https://mail.google.com/mail/u/?authuser={quote(actor)}#drafts"
        return ActionResult(True, "success", tool, actor, target, summary, external_id=did,
                            payload={"url": url, "title": step.get("subject", "") or target,
                                     "draft_id": did})

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
        self._track_file(sid, actor, title, "Sheets")
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
        self._track_file(did, actor, title, "Docs")
        return ActionResult(True, "success", tool, actor, target, summary, external_id=did,
                            payload={"url": f"https://docs.google.com/document/d/{did}",
                                     "title": title, "shared_with_admin": shared})

    @staticmethod
    def _placeholder_id(slide: dict, kinds: tuple[str, ...]) -> str:
        for element in slide.get("pageElements", []):
            placeholder = (element.get("shape") or {}).get("placeholder") or {}
            if placeholder.get("type") in kinds:
                return element.get("objectId", "")
        return ""

    def _add_slide(self, svc, presentation_id: str, spec: dict, index: int) -> None:
        suffix = uuid.uuid4().hex[:12]
        slide_id = f"slide_{suffix}"
        title_id = f"title_{suffix}"
        body_id = f"body_{suffix}"
        requests = [
            {"createSlide": {
                "objectId": slide_id,
                "insertionIndex": index,
                "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                "placeholderIdMappings": [
                    {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": title_id},
                    {"layoutPlaceholder": {"type": "BODY", "index": 0}, "objectId": body_id},
                ],
            }},
        ]
        if spec.get("title"):
            requests.append({"insertText": {"objectId": title_id, "text": spec["title"]}})
        if spec.get("body"):
            requests.append({"insertText": {"objectId": body_id, "text": spec["body"]}})
        svc.presentations().batchUpdate(
            presentationId=presentation_id, body={"requests": requests}
        ).execute()

    def _create_slides(self, step, actor, tool, target, summary):
        svc = self._service("slides", "v1", actor)
        title = step.get("title", target)
        presentation = svc.presentations().create(body={"title": title}).execute()
        pid = presentation.get("presentationId", "")
        specs = step.get("slides", [])
        try:
            if specs:
                current = presentation
                if not current.get("slides") or not current["slides"][0].get("pageElements"):
                    current = svc.presentations().get(presentationId=pid).execute()
                first = (current.get("slides") or [{}])[0]
                title_id = self._placeholder_id(first, ("TITLE", "CENTERED_TITLE"))
                body_id = self._placeholder_id(first, ("SUBTITLE", "BODY"))
                requests = []
                if title_id and specs[0].get("title"):
                    requests.append({"insertText": {"objectId": title_id, "text": specs[0]["title"]}})
                if body_id and specs[0].get("body"):
                    requests.append({"insertText": {"objectId": body_id, "text": specs[0]["body"]}})
                if requests:
                    svc.presentations().batchUpdate(
                        presentationId=pid, body={"requests": requests}
                    ).execute()
                for index, spec in enumerate(specs[1:], start=1):
                    try:
                        self._add_slide(svc, pid, spec, index)
                    except Exception:  # noqa: BLE001
                        # A partial deck is still a valid, screenshot-ready artifact.
                        pass
        except Exception:  # noqa: BLE001
            pass
        shared = self._share_with_admin(pid, actor)
        self._track_file(pid, actor, title, "Slides")
        return ActionResult(True, "success", tool, actor, target, summary, external_id=pid,
                            payload={"url": f"https://docs.google.com/presentation/d/{pid}/edit",
                                     "title": title, "shared_with_admin": shared})

    def _create_event(self, step, actor, tool, target, summary):
        svc = self._service("calendar", "v3", actor)
        title = step.get("title", target)
        attendees = [{"email": e} for e in step.get("attendees", [])]
        admin = (self.settings.admin_email or "").strip()
        if admin and all(a["email"].lower() != admin.lower() for a in attendees):
            # Make the event visible to the operator account for screenshots.
            attendees.append({"email": admin, "optional": True})
        body = {
            "summary": title,
            "start": {"dateTime": step.get("start"), "timeZone": "Asia/Taipei"},
            "end": {"dateTime": step.get("end"), "timeZone": "Asia/Taipei"},
            "attendees": attendees,
        }
        if step.get("meet"):
            body["conferenceData"] = {
                "createRequest": {"requestId": f"lab-{uuid.uuid4().hex[:10]}",
                                  "conferenceSolutionKey": {"type": "hangoutsMeet"}}
            }
        res = svc.events().insert(
            calendarId="primary", body=body, conferenceDataVersion=1, sendUpdates="none"
        ).execute()
        link = res.get("htmlLink", "")
        meet = res.get("hangoutLink", "")
        links = [{"label": "Google Meet", "url": meet}] if meet else []
        return ActionResult(True, "success", tool, actor, target, summary, external_id=res.get("id", ""),
                            payload={"url": link, "htmlLink": link, "title": title,
                                     "meetUrl": meet, "links": links})

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
        self._track_file(fid, actor, title, "Forms")
        return ActionResult(True, "success", tool, actor, target, summary, external_id=fid,
                            payload={"url": f"https://docs.google.com/forms/d/{fid}/edit",
                                     "title": title,
                                     "responderUri": res.get("responderUri", ""),
                                     "shared_with_admin": shared})

    def _label_message(self, step, actor, tool, target, summary):
        svc = self._service("gmail", "v1", actor)
        name = step.get("label") or target or "WorkspaceLab"
        label_id = self._label_id(svc, name)
        subject = step.get("subject", "")
        message_id = step.get("message_id", "") or self.last_message_id
        if subject:
            query = f'subject:"{subject}"'
            messages = []
            for attempt in range(5):
                found = svc.users().messages().list(userId="me", q=query, maxResults=1).execute()
                messages = found.get("messages", [])
                if messages:
                    break
                if attempt < 4:
                    time.sleep(2)
            if messages:
                message_id = messages[0]["id"]
        if not message_id:
            return ActionResult(False, "error", tool, actor, target, summary,
                                error="找不到可標記的 Gmail 訊息")
        svc.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [label_id]}
        ).execute()
        url = f"https://mail.google.com/mail/u/?authuser={quote(actor)}#label/{quote(name)}"
        return ActionResult(True, "success", tool, actor, target, summary, external_id=message_id,
                            payload={"url": url, "title": name, "label_id": label_id,
                                     "message_id": message_id})

    def _send_draft(self, step, actor, tool, target, summary):
        svc = self._service("gmail", "v1", actor)
        draft_id = step.get("draft_id", "") or self.last_draft_id
        if not draft_id:
            return ActionResult(False, "error", tool, actor, target, summary,
                                error="找不到可寄出的 Gmail 草稿")
        res = svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()
        mid = res.get("id", "")
        url = f"https://mail.google.com/mail/u/?authuser={quote(actor)}#sent/{mid}" if mid else ""
        return ActionResult(True, "success", tool, actor, target, summary, external_id=mid,
                            payload={"url": url, "title": step.get("subject", "") or target,
                                     "message_id": mid})

    def _post_chat(self, step, actor, tool, target, summary):
        webhook = (self.settings.chat_webhook_url or "").strip()
        text = step.get("body") or step.get("text") or summary
        if not webhook:
            return ActionResult(True, "skipped", tool, actor, target, summary,
                                error="CHAT_WEBHOOK_URL 未設定；已跳過 Chat 通知")
        payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook, data=payload, method="POST",
            headers={"Content-Type": "application/json; charset=UTF-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                body = resp.read().decode("utf-8", errors="replace")
            message_name = ""
            try:
                message_name = json.loads(body).get("name", "")
            except (TypeError, ValueError):
                pass
            return ActionResult(True, "success", tool, actor, target, summary,
                                external_id=message_name,
                                payload={"url": "https://chat.google.com/", "title": target or "Chat",
                                         "message": text[:500]})
        except Exception as exc:  # noqa: BLE001
            return ActionResult(False, "error", tool, actor, target, summary,
                                error=f"Chat webhook 失敗：{type(exc).__name__}")

    def _archive_folder(self, step, actor, tool, target, summary):
        title = step.get("title") or target or "WorkspaceLab-成果"
        drive = self._service("drive", "v3", actor)
        folder = drive.files().create(
            body={"name": title, "mimeType": "application/vnd.google-apps.folder"},
            fields="id,webViewLink",
        ).execute()
        folder_id = folder.get("id", "")
        self.folder_id = folder_id
        admin = (self.settings.admin_email or "").strip().lower()

        # Pattern A: the folder owner grants writer access to each artifact
        # owner, then each owner moves their own file into the folder. A super
        # admin cannot move another user's My Drive file by impersonation.
        owners = sorted({(item.get("actor") or "").lower() for item in self.created_files if item.get("actor")})
        for owner in owners:
            if not owner or owner == admin:
                continue
            try:
                drive.permissions().create(
                    fileId=folder_id,
                    body={"type": "user", "role": "writer", "emailAddress": owner},
                    sendNotificationEmail=False,
                    fields="id",
                ).execute()
            except Exception:  # noqa: BLE001
                pass

        moved = 0
        failed: list[str] = []
        for item in self.created_files:
            file_id = item.get("id", "")
            owner = (item.get("actor") or actor or "").strip()
            if not file_id or not owner:
                continue
            try:
                owner_drive = self._service("drive", "v3", owner)
                meta = owner_drive.files().get(
                    fileId=file_id, fields="parents,capabilities/canMove"
                ).execute()
                if not (meta.get("capabilities") or {}).get("canMove", True):
                    failed.append(item.get("title", file_id))
                    continue
                parents = meta.get("parents", [])
                kwargs = {"fileId": file_id, "addParents": folder_id, "fields": "id,parents"}
                if parents:
                    kwargs["removeParents"] = ",".join(parents)
                owner_drive.files().update(**kwargs).execute()
                moved += 1
            except Exception:  # noqa: BLE001
                failed.append(item.get("title", file_id))

        url = folder.get("webViewLink", "") or f"https://drive.google.com/drive/folders/{folder_id}"
        return ActionResult(True, "success", tool, actor, target, summary, external_id=folder_id,
                            payload={"url": url, "title": title, "moved": moved,
                                     "failed": len(failed), "folder_id": folder_id})

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
        self._track_file(fid, actor, name, "Drive")
        return ActionResult(True, "success", tool, actor, target, summary, external_id=fid,
                            payload={"url": res.get("webViewLink", ""),
                                     "title": name, "shared_with_admin": shared})
