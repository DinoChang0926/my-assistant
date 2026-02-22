---
trigger: always_on
---

# 專案開發規範

- **主動檢查文件**：開發新功能時，務必主動查看 `README.md` 來確保新功能可以與專案目前的內容、架構及操作步驟相符。
- **雙軌驗證流程**：
    1. 優先在虛擬環境 (`venv`) 進行本機功能開發與測試。
    2. 本機驗證成功後，再進行 Docker 映像檔建置與運行測試。
- **同步更新（必須在同一次對話完成）**：功能驗證後，必須在**同一次對話 (session)** 內同步更新 `README.md`。不可等到下次對話或功能部署後再補。
  - 新增工具 → 更新 `## 🧰 內建原子工具` 表格。
  - 修改架構行為 → 更新架構圖或 Troubleshooting 章節。

# 架構與穩定性守則

- **Session 歷史潔淨度**：嚴禁在 `orchestrator.py` 的 User Message 中注入重複的背景資訊（如長短期記憶、System Context）。所有靜態或背景資訊必須注入到 `system_prompt` 中，以防止 Session History 隨對話次數膨脹導致 `400 invalid_request_body`。
- **工具 Schema 完整性**：建立新技能時，必須確保 `parameters` 符合標準 JSON Schema 規範。特別是 `type: array` 必須包含 `items`，`type: object` 必須包含 `properties`，否則 Copilot API 會報錯。
- **異步與執行緒安全**：
    - 所有涉及 Copilot SDK 的通訊必須在「主事件迴圈」(Main Event Loop) 中執行。
    - Telegram Bot 等外部感知層應使用異步啟動，嚴禁開啟獨立執行緒與 SDK 搶奪 stdin/stdout 管道，以避免 `OSError: [Errno 22] Invalid argument`。
- **事件監聽回收**：確保所有 SDK 事件監聽 (session.on) 都在對話結束後正確呼叫 `unsubscribe()`。
