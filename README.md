# AI Agent Modular Monolith

基於 **模組化單體 (Modular Monolith)** 架構開發的智慧型代理人系統。整合了 **FastAPI** 與 **GitHub Copilot SDK**，支援多模態輸入感知（API/Telegram）、動態意圖路由與長期記憶生命週期管理。

## 🌟 核心特性

- **模組化單體架構**: 清楚的層級劃分：感知層、大腦層、記憶層、技能層 (Skills)。
- **自我進化機制 (Agentic Self-Evolution)**: Agent 可於運行時偵測能力缺失，自動編寫、測試並部署新技能，無需重啟服務。
- **元技能系統 (Meta-Skills)**: 提供 `create_tool`、`inspect_tool`、`reload_tools` 等核心開發技能。
- **本機記憶體持久化 (Local Memory Persistence)**: 提供跨會話 (Session Resumption) 連續對話能力，重啟不流失過往記憶。
- **安全代碼驗證**: 整合 AST 靜態分析，確保生成的技能符合安全與行數規範。
- **GitOps PR 工作流**: 自動建立 GitHub Branch 並發起 PR，實現人類在環 (Human-in-the-loop) 的代碼審核。

## 📁 目錄結構

```text
my-assistant/
├── src/
│   ├── core/          # 標準化事件與介面定義
│   ├── perception/    # 感知層 (FastAPI, Gateway, Telegram session 處理)
│   ├── brain/         # 大腦層 (Router, Orchestrator, Prompts)
│   ├── memory/        # 記憶層 (Session Manager, Session Mapping)
│   └── tools/         # 技能層 (Skills)
│       └── static/    # 靜態/元技能 (Reload, Create, Inspect, SubmitPR)
├── pyproject.toml     # 專案依賴管理
└── storage/           # Session 與記憶持久化區
    ├── local_memory.json     # 本機記憶與對話歷史紀錄
    ├── session_mapping.json  # 外部平台 (如 Telegram) 與核心 Session ID 的對照表
    └── dynamic_tools/        # AI 自動生成的技能 (按分類存放持久化於 Volume)
        └── skills_index.json # 動態技能的快速檢索總表
```

## 🚀 快速開始

### 1. 環境準備

建立 `.env` 檔案並填入必要的 Token：

```bash
cp .env.example .env
```

必填變數：
- `COPILOT_GITHUB_TOKEN`: GitHub Token (需具備 `repo` 權限以支援 PR 功能)。
- `GITHUB_REPO_NAME`: 持久化與 PR 的目標儲存庫 (格式: `owner/repo`)。
- `TELEGRAM_BOT_TOKEN`: 用於啟動 Telegram Bot (選填，若設定則自動啟動。會自動處理 Chat ID 記憶與映射，實現無縫的會話接續)。

### 2. 安裝

本專案支援 Docker 部署與本機開發。

#### 方法 A：Docker (推薦)

```bash
docker-compose up --build
```

#### 方法 B：本機開發 (Local Development)

若要進行開發或除錯，建議使用虛擬環境：

1. **建立並啟用虛擬環境**:
   
   Windows:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

   Linux/macOS:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. **安裝依賴**:
   ```bash
   pip install -e .
   ```

3. **啟動服務**:
   ```bash
   # 務必使用 module 方式啟動，否則會遇到 Import Error
   python -m src.main
   ```

### 3. Skills API 端點

本系統提供專用的 API 來管理與監控代理人的技能：

- **`GET /skills`**: 列出當前所有已註冊的技能及其詳細參數規範。
- **`POST /skills/reload`**: 觸發熱重載，立即使新編寫的技能生效。
- **`GET /skills/{name}`**: 查詢特定技能的實作細節與 Schema。

### 4. 常見問題 (Troubleshooting)

- **Failed to list models (400)**: 代表 `COPILOT_GITHUB_TOKEN` 無效、過期或權限不足。請重新生成 Token 並確保勾選 `repo` 與 `Copilot` 相關權限（若有）。
- **ModuleNotFoundError: No module named 'src'**: 請確認您是在專案根目錄執行，且使用 `python -m src.main` 而非 `python src/main.py`。
- **SMTPAuthenticationError (535): Username and Password not accepted**: 若使用 Gmail，這是因為您使用了「登入密碼」而非「應用程式密碼 (App Password)」。
  - 請至 [Google 帳戶安全性](https://myaccount.google.com/security) 開啟 **兩步驟驗證 (2-Step Verification)**。
  - 搜尋或找到 **應用程式密碼 (App passwords)**。
  - 建立一組新的密碼（選擇「郵件」和「Windows 電腦」），並將生成的 16 碼密碼（無需空格）填入 `.env` 的 `SMTP_PASS`。

## 🛠️ 自我進化工作流 (Evolution Flow)

1. **偵測缺失**: 模型發現無法完成任務。
2. **自動開發**: 模型呼叫 `create_tool` 寫入程式碼（經 AST 驗證）。
3. **熱重載**: 模型呼叫 `reload_tools` 或透過 API `POST /skills/reload` 啟動新功能。
4. **回饋碼庫**: 模型呼叫 `submit_tool_pr` 提交 PR 給人類審核。

---
Developed with ❤️ for AI Agent research.
