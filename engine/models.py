from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ActionResult:
    ok: bool
    status: str
    tool: str
    actor: str
    target: str
    summary: str
    external_id: str = ""
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "tool": self.tool,
            "actor": self.actor,
            "target": self.target,
            "summary": self.summary,
            "external_id": self.external_id,
            "error": self.error,
            "payload": self.payload,
        }


@dataclass
class Persona:
    id: str
    name: str
    role: str
    email: str
    agent: str
    color: str
    description: str
    tools: list[str] = field(default_factory=list)
    status: str = "standby"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "email": self.email,
            "agent": self.agent,
            "color": self.color,
            "description": self.description,
            "tools": self.tools,
            "status": self.status,
        }
