# WorkspaceLab

用 MiroFish 式「種子 → persona → 模擬 → 報告」架構，對 **真實 Google Workspace** 做企業導入實驗。

- 10 個製造業 persona／6 個 agent
- 3 個核心場景：詢價報價、排程急單、品質客訴
- Mock 模式：沒有 Google 憑證也能完整跑
- Real 模式：Gmail、Drive、Docs、Sheets、Calendar、Forms
- 預設 Dry-run、收件人 allowlist、Kill switch、audit log
- 實驗報告：timeline、KPI、失敗、建議

## 快速開始（Mock）

```bash
cd WorkspaceLab
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

開 http://127.0.0.1:8787

1. Scenario 選「詢價報價」
2. Mode 選「Mock」
3. 按 **Start experiment**
4. 看 live feed、KPI、report
5. 可注入急單／缺料／客訴事件

## Real Workspace 設定

> 先確認你有一個測試 tenant／測試 OU，且 trial 只有一次。**不要拿真實客戶信箱做測試。**

### 1. Google Cloud

1. 建一個 Google Cloud project
2. 啟用 APIs：
   - Gmail API
   - Google Drive API
   - Google Docs API
   - Google Sheets API
   - Google Calendar API
   - Google Forms API
3. 建立 **Service Account**
4. 建立 JSON key，下載到本機（不要進 git）

### 2. Domain-wide delegation

1. Google Cloud console → Service Account → 複製 **Client ID**
2. Google Workspace Admin console → Security → API controls → Domain-wide delegation
3. 新增 client ID，授權 scopes：

```
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/forms.body
```

4. 管理員 email 必須是 Workspace 管理員（例：`admin@ycair.online`）

### 3. `.env`

```bash
cp .env.example .env
```

```env
GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/service-account.json
GOOGLE_ADMIN_EMAIL=admin@ycair.online
DRY_RUN=1
ALLOWLIST=@ycair.online
```

`ALLOWLIST=@ycair.online` 只允許寄給同網域；要寄到外部測試信箱，請加該位址，例如：

```env
ALLOWLIST=@ycair.online,buyer@example-test.com
```

### 4. 驗證憑證

```bash
.venv/bin/python scripts/check_real.py
```

看到 `RESULT: real adapter can authenticate.` 才代表 service account + delegation 正確。

### 5. 先 Dry-run

```bash
DRY_RUN=1 .venv/bin/python app.py
```

- Mode 選 **Real Workspace**
- Start
- 所有動作會顯示 `dry_run`，不會真的寄信／寫檔
- 若有 allowlist 或憑證錯誤，會顯示在 config note / feed

### 6. 第一次真實動作

只測一封，且只寄給 allowlist 內的測試信箱：

```env
DRY_RUN=0
ALLOWLIST=sales@ycair.online
```

在 UI 選 Real、Start，確認：

- Gmail 收到信
- audit log 有 `success`
- 沒有寄給外部真實客戶

## 安全護欄

- 預設 `DRY_RUN=1`
- 非 allowlist 收件人直接拒絕
- `KILL` 會停止新動作
- 一次只跑一個 experiment
- 每個 action 寫入 SQLite audit log
- 建議只在測試 OU、測試使用者、測試信箱執行
- 不要把 service account JSON、`.env`、`data/` 進 git

## API

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/state` | 完整狀態（experiment、actions、metrics、personas） |
| GET | `/api/config` | real 設定狀態、scenarios |
| POST | `/api/start` | `{scenario, mode, delay}` |
| POST | `/api/pause` | 暫停 |
| POST | `/api/resume` | 繼續 |
| POST | `/api/reset` | 清除本次實驗 |
| POST | `/api/event` | `{type, payload}` 注入事件 |
| GET | `/api/report` | Markdown 報告；`?download=1` 下載 |

## 測試

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 目前限制

- **Chat 以使用者身分發訊息**：Google Chat API 主要支援 Chat app；本版不做。
- **Meet 錄影／逐字稿／Gemini 筆記**：需 UI／權限；本版只建立 Calendar + Meet link。
- **Gemini in Gmail／Docs 的 UI**：本版用模板／log 表示 AI 步驟，不直接驅動 UI。
- **AppSheet App 建立**：沒有公開建立 API。

第二階段再用 Playwright／Chat app 補。

## 檔案結構

```
WorkspaceLab/
├── app.py                 # HTTP server + API
├── engine/
│   ├── models.py
│   ├── store.py           # SQLite
│   ├── personas.py        # 10 personas / 6 agents
│   ├── scenarios.py       # 3 scenarios
│   ├── simulator.py       # run / pause / event
│   ├── workspace.py       # Mock + Google adapter
│   └── report.py
├── web/                   # dashboard
├── tests/
├── data/                  # SQLite + logs（不進 git）
└── exports/               # screenshots / reports
```
