from __future__ import annotations

import copy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SCENARIOS = {
    "quote": {
        "id": "quote",
        "name": "詢價報價",
        "pain": "2 天",
        "gain": "4 小時",
        "description": "客戶詢價 → Gemini 摘要 → Sheets 成本 → Docs 提案 → 廠長核准 → 回信。",
        "metrics": [
            ("quote_baseline_hours", 48, "h"),
            ("quote_result_hours", 4, "h"),
            ("quote_gain_pct", 91.7, "%"),
        ],
        "steps": [
            {
                "actor": "customer", "agent": "SALES", "tool": "Gmail", "action": "send_email",
                "to": "sales@ycair.online", "subject": "【YC】詢價：SUS304 沖壓件 500 pcs",
                "target": "sales@ycair.online",
                "summary": "客戶寄來詢價：500 件、SUS304、3 週交期。",
                "body": "您好，想詢問 SUS304 沖壓件 500 pcs，t=2.0，交期 3 週，請提供單價與模具費。",
            },
            {
                "actor": "sales", "agent": "SALES", "tool": "Docs", "action": "create_doc",
                "target": "YC-詢價摘要-2026-11-23",
                "title": "YC-詢價摘要-2026-11-23",
                "summary": "Gemini 摘要詢價信並寫入 Docs：列出缺的 3 個規格。",
                "body": "YC 詢價摘要\n\n客戶：範例家電\n品項：SUS304 沖壓件\n數量：500 pcs\n交期：3 週\n\n缺漏規格：\n1. 厚度公差\n2. 表面處理\n3. 包裝方式\n\n下一步：請業務補齊規格後回覆客戶。",
            },
            {
                "actor": "sales", "agent": "SALES", "tool": "Sheets", "action": "create_sheet",
                "target": "YC-報價成本-2026-11-23",
                "summary": "建立報價成本表：材料、加工、模具攤提、管銷、毛利。",
                "title": "YC-報價成本-2026-11-23",
                "rows": [
                    ["項目", "金額", "備註"],
                    ["材料 SUS304 t2.0", 180, "含裁切"],
                    ["沖壓加工", 45, "機台＋人工"],
                    ["模具攤提", 60, "5,000 件"],
                    ["表面處理", 25, "委外拉絲"],
                    ["管銷 8%", 26.4, ""],
                    ["毛利 15%", 50.16, ""],
                    ["總價", 406.56, "未稅"],
                ],
            },
            {
                "actor": "sales", "agent": "SALES", "tool": "Docs", "action": "create_doc",
                "target": "YC-報價提案-2026-11-23",
                "summary": "建立報價提案 Docs，含規格、交期、付款條件。",
                "title": "YC-報價提案-2026-11-23",
                "body": "YC 金屬加工報價提案\n\n客戶：範例家電\n品項：SUS304 沖壓件\n數量：500 pcs\n單價：NT$406.56（未稅）\n交期：3 週\n付款：月結 30 天\n\n備註：模具費已攤提 5,000 件。",
            },
            {
                "actor": "boss", "agent": "DIRECTOR", "tool": "Docs", "action": "create_doc",
                "target": "YC-報價核准紀錄-2026-11-23",
                "title": "YC-報價核准紀錄-2026-11-23",
                "summary": "廠長核准報價並寫入 Docs 核准紀錄：毛利 15%，可接受。",
                "body": "YC 報價核准紀錄\n\n核准人：王總經理\n報價：NT$406.56／件（未稅）\n毛利：15%\n交期：3 週\n\n決策：核准，可回覆客戶。",
            },
            {
                "actor": "sales", "agent": "SALES", "tool": "Gmail", "action": "send_email",
                "to": "customer@ycair.online", "subject": "【YC】回覆：SUS304 沖壓件報價",
                "target": "customer@ycair.online",
                "summary": "回覆客戶報價：NT$406.56／件，3 週交期。",
                "body": "您好，附件為報價提案。單價 NT$406.56（未稅），交期 3 週。請確認規格。\n\nYC 業務部",
            },
        ],
    },
    "schedule": {
        "id": "schedule",
        "name": "排程急單",
        "pain": "6 小時",
        "gain": "2 小時",
        "description": "急單進 Chat → 工單匯入 Sheets → 找風險工單 → 廠長決策 → 開產銷會議。",
        "metrics": [
            ("schedule_baseline_hours", 6, "h"),
            ("schedule_result_hours", 2, "h"),
            ("schedule_gain_pct", 66.7, "%"),
        ],
        "steps": [
            {
                "actor": "sales", "agent": "SALES", "tool": "Docs", "action": "create_doc",
                "target": "YC-急單通知-2026-11-23",
                "title": "YC-急單通知-2026-11-23",
                "summary": "業務在 Chat 丟急單並寫入 Docs 通知紀錄：明天要 300 件。",
                "body": "YC 急單通知\n\n來源：Chat #production\n內容：明天要 300 件，請生管評估插單。\n影響：待確認。\n\n下一步：生管匯入工單並找出風險工單。",
            },
            {
                "actor": "plan", "agent": "PLANNER", "tool": "Sheets", "action": "create_sheet",
                "target": "YC-工單排程-2026-11-23",
                "summary": "工單匯入 Sheets，標記 5 張逾期與 2 張急單。",
                "title": "YC-工單排程-2026-11-23",
                "rows": [
                    ["工單", "品號", "機台", "數量", "交期", "狀態"],
                    ["WO-001", "YC-1001", "CT-160", 500, "2026-12-05", "未開工"],
                    ["WO-002", "YC-1002", "CT-250", 800, "2026-12-03", "生產中"],
                    ["WO-003", "YC-1003", "CT-110", 2000, "2026-12-08", "未開工"],
                    ["WO-004", "YC-1004", "CT-160", 1200, "2026-12-02", "逾期"],
                    ["WO-005", "YC-1005", "CT-250", 300, "2026-12-10", "未開工"],
                ],
            },
            {
                "actor": "plan", "agent": "PLANNER", "tool": "Docs", "action": "create_doc",
                "target": "YC-排程風險分析-2026-11-23",
                "title": "YC-排程風險分析-2026-11-23",
                "summary": "Gemini 找出風險工單並寫入 Docs：3 張交期最緊、尚未開工。",
                "body": "YC 排程風險分析\n\nGemini 找出交期最緊、尚未開工的 3 張工單：\n- WO-003 / YC-1003 / 2026-12-08 / 2000 pcs\n- WO-005 / YC-1005 / 2026-12-10 / 300 pcs\n- WO-001 / YC-1001 / 2026-12-05 / 500 pcs\n\n建議：先確認 CT-110 與 CT-160 產能。",
            },
            {
                "actor": "boss", "agent": "DIRECTOR", "tool": "Docs", "action": "create_doc",
                "target": "YC-急單決策紀錄-2026-11-23",
                "title": "YC-急單決策紀錄-2026-11-23",
                "summary": "廠長決策並寫入 Docs：急單插入，WO-004 延 1 天。",
                "body": "YC 急單決策紀錄\n\n決策：急單插入，WO-004 延 1 天。\n與會：廠長、生管、業務。\n\n下一步：建立產銷會議並通知相關人員。",
            },
            {
                "actor": "plan", "agent": "PLANNER", "tool": "Calendar", "action": "create_event",
                "target": "產銷會議",
                "summary": "建立產銷會議（含 Meet），討論插單與交期。",
                "title": "YC 產銷會議：急單插單",
                "start": "2026-11-24T09:00:00+08:00",
                "end": "2026-11-24T09:30:00+08:00",
                "attendees": ["boss@ycair.online", "plant@ycair.online", "sales@ycair.online"],
                "meet": True,
            },
            {
                "actor": "plan", "agent": "PLANNER", "tool": "Docs", "action": "create_doc",
                "target": "YC-插單影響分析",
                "summary": "建立插單影響分析 Docs：受影響工單與替代方案。",
                "title": "YC-插單影響分析",
                "body": "急單：300 件，明天交。\n受影響：WO-004 延 1 天、WO-005 延 0.5 天。\n建議：WO-004 改夜班、WO-005 維持。",
            },
        ],
    },
    "quality": {
        "id": "quality",
        "name": "品質客訴",
        "pain": "1 天",
        "gain": "2 小時",
        "description": "品保開 Forms → 8D Docs → 通知廠長 → 異常追蹤 Sheet → containment 2 小時。",
        "metrics": [
            ("quality_baseline_hours", 24, "h"),
            ("quality_result_hours", 2, "h"),
            ("quality_gain_pct", 91.7, "%"),
        ],
        "steps": [
            {
                "actor": "qa", "agent": "QA", "tool": "Forms", "action": "create_form",
                "target": "YC-製程異常通報",
                "summary": "建立異常通報 Forms：產線、工單、不良類型、照片。",
                "title": "YC-製程異常通報",
                "questions": [
                    "產線", "工單", "不良類型", "不良數量", "可能原因", "暫處理", "照片連結",
                ],
            },
            {
                "actor": "qa", "agent": "QA", "tool": "Docs", "action": "create_doc",
                "target": "YC-8D-A線刮傷-2026-11-23",
                "summary": "建立 8D 報告：D1–D8 框架，含暫時對策。",
                "title": "YC-8D-A線刮傷-2026-11-23",
                "body": "D1 小組：廠長、品保、生管、模具\nD2 問題：A 線刮傷 8/200\nD3 暫對策：停線清模、客戶端全檢\nD4 原因：模具表面異物\nD5 永久對策：清模 SOP＋工作燈\nD6 驗證：連續 2 批 0 不良\nD7 預防：訓練與稽核\nD8 結案：2026-12-05",
            },
            {
                "actor": "qa", "agent": "QA", "tool": "Docs", "action": "create_doc",
                "target": "YC-客訴通知紀錄-2026-11-23",
                "title": "YC-客訴通知紀錄-2026-11-23",
                "summary": "Chat 通知廠長與現場並寫入 Docs：先停線，containment 開始。",
                "body": "YC 客訴通知紀錄\n\n來源：Chat #quality\n內容：A 線刮傷 8 件，先停線清模，客戶端全檢。\n\n下一步：完成 8D 永久對策並核准。",
            },
            {
                "actor": "boss", "agent": "DIRECTOR", "tool": "Docs", "action": "create_doc",
                "target": "YC-8D核准紀錄-2026-11-23",
                "title": "YC-8D核准紀錄-2026-11-23",
                "summary": "廠長核准永久對策並寫入 Docs：清模 SOP 與工作燈。",
                "body": "YC 8D 核准紀錄\n\n核准人：王總經理\n永久對策：清模 SOP＋工作燈\n驗證：連續 2 批 0 不良\n\n決策：核准，結案日 2026-12-05。",
            },
            {
                "actor": "qa", "agent": "QA", "tool": "Sheets", "action": "create_sheet",
                "target": "YC-異常追蹤-2026-11-23",
                "summary": "建立異常追蹤表：8 件、責任人、狀態、結案日。",
                "title": "YC-異常追蹤-2026-11-23",
                "rows": [
                    ["日期", "產線", "不良", "數量", "責任人", "狀態"],
                    ["2026-11-23", "A", "刮傷", 8, "黃品保", "處理中"],
                    ["2026-11-23", "A", "刮傷", 0, "模具組", "待驗證"],
                ],
            },
        ],
    },
}


def _render_text(value: str, company: str) -> str:
    # Keep the real Workspace domain (ycair.online) intact; only replace the
    # demo company label that appears in titles, bodies and subjects.
    return (
        value.replace("YC 金屬加工", company)
        .replace("【YC】", f"【{company}】")
        .replace("YC-", f"{company}-")
        .replace("YC ", f"{company} ")
        .replace("YC", company)
    )


def render_scenario(scenario: dict, company: str = "") -> dict:
    """Return a deep copy with the company name and current demo dates applied."""
    company = " ".join((company or "").strip().split()) or "YC 金屬加工"
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    rendered = copy.deepcopy(scenario)

    def walk(value):
        if isinstance(value, str):
            # Replace the calendar date first so a today == 2026-11-24 run does
            # not accidentally turn 2026-11-23 into tomorrow.
            value = value.replace("2026-11-24", tomorrow).replace("2026-11-23", today)
            return _render_text(value, company)
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    return walk(rendered)


def get_scenario(key: str, company: str = "") -> dict:
    return render_scenario(SCENARIOS.get(key) or SCENARIOS["quote"], company)
