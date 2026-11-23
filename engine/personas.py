from __future__ import annotations

from .models import Persona

AGENTS = {
    "DIRECTOR": {"label": "總控", "color": "#f59e0b", "mission": "排班、分派、卡住喊停"},
    "SALES": {"label": "業務", "color": "#e11d48", "mission": "詢價、報價、客戶往來"},
    "PLANNER": {"label": "生管", "color": "#14b8a6", "mission": "排程、缺料、產銷會議"},
    "QA": {"label": "品保", "color": "#3b82f6", "mission": "異常、8D、客訴"},
    "DOC": {"label": "文件", "color": "#8b5cf6", "mission": "圖面、SOP、知識庫"},
    "VERIFIER": {"label": "驗證", "color": "#22c55e", "mission": "截圖、KPI、報告"},
}

PERSONAS: list[Persona] = [
    Persona("admin", "系統管理員", "IT／管理", "admin@ycair.online", "DIRECTOR", "#f59e0b",
            "Admin console、權限、audit、2SV。", ["Admin", "2SV", "Audit"]),
    Persona("boss", "王總經理", "總經理", "boss@ycair.online", "DIRECTOR", "#f59e0b",
            "看 KPI、做決策、核准插單與報價。", ["Gmail", "Chat", "Sheets"]),
    Persona("plant", "陳廠長", "廠長", "plant@ycair.online", "PLANNER", "#14b8a6",
            "產能、交期、跨組調度。", ["Sheets", "Chat", "Calendar"]),
    Persona("plan", "林生管", "生管", "plan@ycair.online", "PLANNER", "#14b8a6",
            "工單、排程、急單、缺料。", ["Sheets", "Gemini", "Calendar"]),
    Persona("sales", "張業務", "業務", "sales@ycair.online", "SALES", "#e11d48",
            "詢價、報價、客戶回覆。", ["Gmail", "Gemini", "Docs"]),
    Persona("purchase", "李採購", "採購", "purchase@ycair.online", "PLANNER", "#14b8a6",
            "供應商、交期、請購。", ["Gmail", "Sheets"]),
    Persona("qa", "黃品保", "品保", "qa@ycair.online", "QA", "#3b82f6",
            "檢驗、異常、8D、客訴。", ["Forms", "AppSheet", "Docs"]),
    Persona("eng", "吳工程", "研發工程", "eng@ycair.online", "DOC", "#8b5cf6",
            "圖面、BOM、SOP、試模。", ["Drive", "Gemini", "Notebook"]),
    Persona("finance", "周財務", "財務／人資", "finance@ycair.online", "VERIFIER", "#22c55e",
            "成本、費用、訓練紀錄。", ["Sheets", "Docs"]),
    Persona("customer", "王小姐", "客戶", "customer@ycair.online", "SALES", "#64748b",
            "詢價、規格確認、收報價。", ["Gmail", "Meet"]),
]

PERSONA_BY_ID = {p.id: p for p in PERSONAS}
PERSONA_BY_EMAIL = {p.email: p for p in PERSONAS}


def persona_for(actor_id: str) -> Persona:
    return PERSONA_BY_ID.get(actor_id) or PERSONA_BY_ID["admin"]
