# AI Agent Modular Monolith

基於 **模組化單體 (Modular Monolith)** 架構開發的智慧型代理人系統。整合了 **FastAPI** 與 **GitHub Copilot SDK**，支援多模態輸入感知（API/Telegram）、動態意圖路由與長期記憶生命週期管理。

## 🌟 核心特性

- **模組化單體架構**: 清楚的層級劃分：感知層、大腦層、記憶層、工具層。
- **GitHub Copilot SDK 原生持久化**: 利用 SDK 的 `config_dir` 機制，自動保存與恢復對話狀態，支援跨重啟的長期記憶。
- **兩級意圖路由**: 支援快速指令解析與基於關鍵字的 LLM 路由（Coding vs Chat）。
- **記憶重生機制 (Summarize & Respawn)**: 自動監控轉載輪次 (turn_count)，在對話過長時執行重生策略。
- **雙軌輸入支援**: 同時支援 FastAPI REST API 與 Telegram Bot (已預留架構)。

## 📁 目錄結構

```text
my-assistant/
├── src/
│   ├── core/          # 標準化事件與介面定義
│   ├── perception/    # 感知層 (FastAPI, Telegram Bot, Gateway)
│   ├── brain/         # 大腦層 (Router, Orchestrator, Prompts)
│   ├── memory/        # 記憶層 (Session Manager, Compression)
│   └── tools/         # 工具層 (Registry, Base Classes)
├── examples/          # 原始 SDK 使用範例
└── pyproject.toml     # 專案依賴管理
```

## 🚀 快速開始

### 1. 環境準備

建立 `.env` 檔案並填入必要的 Token：

```bash
cp .env.example .env
```

必填變數：
- `COPILOT_GITHUB_TOKEN`: 用於 GitHub Copilot SDK。
- `TELEGRAM_BOT_TOKEN`: 用於 Telegram Bot 控制（選填）。

### 2. 安裝

```bash
pip install -e .
```

### 3. 啟動服務 (本機開發優先)
為了快速迭代，建議優先在本機執行：

```bash
# 啟動 API 伺服器
python -m src.main
```

### 4. Docker 驗證
本機測試完成後，使用 Docker 驗證建置與持久化：

```bash
docker compose up --build -d
```

### 5. 測試與驗證

#### Session 持久化驗證
系統目前支援自動持久化 Session 狀態至 `./storage`。

1. **初始對話**：傳送包含個人資訊的訊息。
2. **重啟**：關閉並重啟伺服器。
3. **恢復**：使用相同 `session_id` 詢問先前提供的資訊，確認 Agent 是否保留記憶。

#### 使用 PowerShell 測試範例

#### A. 使用 WSL (Ubuntu) 或 Linux 終端機
```bash
# 檢查健康狀態
curl http://localhost:8000/health

# 進行對話測試
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"content": "請幫我寫一個 Python 的費式數列函式", "session_id": "user_123"}'
```

#### B. 使用 Windows PowerShell
由於 PowerShell 的 `curl` 與標準不同，請使用以下指令：

```powershell
# 檢查健康狀態
Invoke-RestMethod -Uri http://localhost:8000/health

# 進行對話測試
$body = @{
    content = "你好，請寫一個 Python Hello World"
    session_id = "test_user"
} | ConvertTo-Json -Compress

Invoke-RestMethod -Method Post -Uri http://localhost:8000/chat -ContentType "application/json" -Body $body
```

## 🛠️ 開發與擴充

### 註冊新工具
在 `src/tools/` 下繼承 `BaseTool` 並在 `main.py` 的 `tool_registry` 中註冊即可讓 AI 使用。

### 調整重生策略
修改 `src/config.py` 中的 `SESSION_MAX_TURNS` 來決定幾輪後觸發 Session 重生。

---
Developed with ❤️ for AI Agent research.
