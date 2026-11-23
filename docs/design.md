# WorkspaceLab 設計文件

日期：2026-11-23
狀態：待核准
目的：用 MiroFish 式「種子 → 圖譜 → persona → 模擬 → 報告」架構，對真實 Google Workspace 做企業導入實驗。

---

## 1. 意圖

建立一個可在本機執行的實驗工具，讓 10 個工廠 persona／6 個 agent 在同一個實驗腳本下，對**真實 Workspace** 執行動作：

- 寄 Gmail、建立 Draft
- 上傳／分享 Drive 檔案
- 建立與更新 Docs
- 建立與更新 Sheets
- 建立 Calendar 事件（可含 Meet 連結）
- 建立 Forms

同時提供：

- 實驗控制台（開始／暫停／重置／事件注入）
- 即時動作時間軸
- 10 個 persona 狀態
- KPI 與實驗報告
- Mock 模式（沒有 Google 憑證也能完整跑一次）

## 2. 目標與非目標

### 目標

1. 今天可完成一個 end-to-end 可跑的完整版。
2. 同一套劇本可切換 **Mock** 與 **Real Workspace**。
3. Real 模式預設 **Dry-run**，需明確開啟才會真的寄信／寫檔。
4. 每個動作都有 audit log、actor、target、timestamp、結果。
5. 匯出 Markdown／HTML 實驗報告。

### 非目標（今天不做）

- Chat 以「使用者身分」發訊息（Google Chat API 限制；需要 Chat app／UI 自動化）
- Meet 錄影、逐字稿、Gemini 會議筆記（需 UI／權限）
- Gemini in Gmail／Docs 的完整 UI 自動化（第一版用 Gemini API／模板產生內容，再寫入 Gmail／Docs）
- AppSheet App 建立（無公開建立 API）
- 多租戶、計費、正式產品化

> 這些不是忽略，是第二階段用 Playwright／Chat app／Meet API 補。

## 3. 架構

```
┌──────────────────────────────────────────────────────────┐
│ Web Dashboard（vanilla JS / CSS）                        │
│ 控制台、persona roster、live feed、KPI、report           │
└───────────────────────┬──────────────────────────────────┘
                        │ HTTP JSON / polling
┌───────────────────────▼──────────────────────────────────┐
│ Python App（http.server + sqlite3）                      │
│                                                          │
│  Experiment Engine                                       │
│   ├─ Persona / Agent registry                            │
│   ├─ Scenario script                                     │
│   ├─ Event injector                                      │
│   ├─ Tick loop（背景 thread）                            │
│   └─ Metrics / Report                                    │
│                                                          │
│  Workspace Adapter（interface）                          │
│   ├─ MockAdapter（預設，無憑證可跑）                     │
│   └─ GoogleAdapter（service account + delegation）       │
│        Gmail / Drive / Docs / Sheets / Calendar / Forms  │
└───────────────────────┬──────────────────────────────────┘
                        │ Google APIs
┌───────────────────────▼──────────────────────────────────┐
│ 真實 Google Workspace tenant（ycair.online）             │
└──────────────────────────────────────────────────────────┘
```

## 4. 資料模型

SQLite tables：

- `experiments`：id, name, mode, status, started_at, ended_at, scenario
- `personas`：id, name, role, email, agent, color, status
- `events`：id, experiment_id, type, payload, created_at
- `actions`：id, experiment_id, actor, agent, tool, target, summary, status, error, created_at
- `metrics`：id, experiment_id, key, value, unit, created_at
- `artifacts`：id, experiment_id, kind, name, path/url, created_at
- `logs`：id, experiment_id, level, message, created_at

## 5. Persona 與 Agent

10 個 persona：

`customer`, `sales`, `planner`, `qa`, `boss`, `purchase`, `eng`, `finance`, `it`, `guest`

6 個 agent：

`DIRECTOR`, `SALES`, `PLANNER`, `QA`, `DOC`, `VERIFIER`

Mapping：

- DIRECTOR → boss + it
- SALES → sales + customer（外部互動由 sales 代理）
- PLANNER → planner + purchase
- QA → qa
- DOC → eng
- VERIFIER → finance + it

## 6. 三個核心場景

### 6.1 詢價報價

1. customer 寄詢價信 → sales 收信
2. sales 產生摘要／回覆草稿
3. sales 建 Sheets 報價成本
4. sales 建 Docs 報價提案
5. boss 核准（action log）
6. sales 寄回客戶

KPI：回覆時間、缺漏資訊數、報價版本數

### 6.2 排程急單

1. sales 收到急單
2. planner 建／更新工單 Sheet
3. planner 標記逾期與急單
4. boss 決定插單
5. planner 建 Calendar 產銷會議（含 Meet link）
6. planner 通知（Gmail／log）

KPI：排程更新時間、受影響工單數、回覆時間

### 6.3 品質客訴

1. qa 建 Forms 異常通報
2. qa 建 Docs 8D
3. boss 核准對策
4. qa 更新狀態
5. VERIFIER 記錄 containment 時間

KPI：containment 時間、8D 完成時間、重複異常數

## 7. Workspace Adapter

### Interface

```python
class WorkspaceAdapter:
    def send_email(actor, to, subject, body) -> ActionResult
    def create_draft(actor, to, subject, body) -> ActionResult
    def upload_drive(actor, name, content, mime, folder_id=None) -> ActionResult
    def create_doc(actor, title, body) -> ActionResult
    def append_doc(actor, doc_id, body) -> ActionResult
    def create_sheet(actor, title, rows) -> ActionResult
    def append_sheet(actor, sheet_id, rows) -> ActionResult
    def create_event(actor, title, start, end, attendees, meet=True) -> ActionResult
    def create_form(actor, title, questions) -> ActionResult
```

### MockAdapter

- 把動作寫入 `actions` table，回傳假 ID。
- 不呼叫網路。
- 預設模式；沒有憑證也能完整跑。

### GoogleAdapter

- `service_account.Credentials.from_service_account_file(...).with_subject(actor)`
- Scopes：
  - `gmail.send`, `gmail.modify`
  - `drive`
  - `documents`
  - `spreadsheets`
  - `calendar`
  - `forms.body`
- 預設 `DRY_RUN=1`：只驗證參數與權限，不真的送出。
- `ALLOWLIST`：只允許寄到指定測試信箱；非 allowlist 直接拒絕。
- `MAX_ACTIONS`：防止暴走。
- 每次動作寫 audit log。

## 8. 控制台 UI

- Header：模式（Mock／Real）、狀態、Run／Pause／Reset、Kill switch
- Left：10 個 persona 卡片（角色、email、agent、狀態）
- Center：live action feed（時間、actor、tool、target、status）
- Right：KPI 卡片、場景進度、事件注入按鈕
- Bottom：Report preview + 匯出 Markdown／HTML

设计方向：control room，不是表格；深色背景、狀態燈、動作流。

## 9. 安全與實驗倫理

- 只用測試 tenant／測試 OU。
- 預設 Dry-run；Real 模式需在 UI 明確切換並二次確認。
- 收件人 allowlist；禁止真實客戶。
- 外部分享只給 `guest@`，只放範例資料。
- 每次實驗有 kill switch。
- 所有動作寫 audit log；可匯出。
- 實驗結束後提供清理清單（刪測試檔、撤分享、關帳號）。

## 10. 完成定義（今天）

必要：

- [ ] `python3 app.py` 啟動 dashboard
- [ ] Mock 模式可完整跑 3 個場景
- [ ] 10 personas / 6 agents 顯示與狀態更新
- [ ] 事件注入可用
- [ ] KPI 與報告可匯出
- [ ] Real adapter 可載入 service account；Dry-run 可跑
- [ ] Real 模式可執行 Gmail／Drive／Docs／Sheets／Calendar／Forms 的基本動作（有憑證時）
- [ ] 安全護欄（dry-run、allowlist、max actions、audit）
- [ ] README 與憑證設定指南

非必要（第二階段）：

- Chat 使用者訊息、Meet 錄影、Gemini UI、AppSheet。

## 11. 驗收方式

1. 無憑證啟動 → Mock 模式跑完 3 場景 → 報告產生。
2. 放入 service account JSON → Real 模式 Dry-run → 每個 adapter 回傳「驗證成功，未送出」。
3. 将 allowlist 設為測試信箱 → 執行一封信 → 收到信；audit log 有紀錄。
4. Kill switch → 動作停止。
5. 匯出報告 → 含 timeline、KPI、失敗/成功數。

## 12. 風險

- Google API 憑證與 domain-wide delegation 需要管理員權限；今天可能拿不到，先用 Mock/Dry-run 驗證。
- Chat／Meet／Gemini UI 不在第一版；不要假裝有。
- 真實 trial 只有一次；Real 模式預設 Dry-run，避免燒掉 trial。
- 10 個 agent 並行會撞配額；引擎預設一次跑 3 個 agent。
