---
trigger: always_on
---

# 專案開發規範

- **工作流強制執行協定 (Workflow-First Protocol)**：任何涉及 `src/` 變更的任務，**必須**優先讀取對應的工作流檔案（如 `.agent/workflows/dev-flow.md`），並將其步驟完全整合至 `task.md`。禁止跳過任何標註為「必做」的步驟（如同步更新文件）。
- **同步更新（必須在同一次對話完成）**：功能驗證後，必須在**同一次對話 (session)** 內同步更新 `README.md`。不可等到下次對話或功能部署後再補。
  - 新增工具 → 更新 `## 🧰 內建原子工具` 表格。
  - 修改架構行為 → 更新架構圖或 Troubleshooting 章節。
- **任務交付合規表 (Compliance Table)**：在呼叫 `notify_user` 交付最終成果前，必須在對話中列出合規表，逐一確認工作流中所有必要步驟（語法檢查、本機測試、文件同步）是否已完成。未達標前禁止宣告任務結束。
- **雙軌驗證流程**：
    1. 優先在虛擬環境 (`venv`) 進行本機功能開發與測試。
    2. 本機驗證成功後，再進行 Docker 映像檔建置與運行測試。
- **主動檢查文件**：開發新功能時，務必主動查看 `README.md` 來確保新功能可以與專案目前的內容、架構及操作步驟相符。

# 架構與穩定性守則

- **Session 歷史潔淨度**：嚴禁在 `orchestrator.py` 的 User Message 中注入重複的背景資訊（如長短期記憶、System Context）。所有靜態或背景資訊必須注入到 `system_prompt` 中，以防止 Session History 隨對話次數膨脹導致 `400 invalid_request_body`。
- **工具 Schema 完整性**：建立新技能時，必須確保 `parameters` 符合標準 JSON Schema 規範。特別是 `type: array` 必須包含 `items`，`type: object` 必須包含 `properties`，否則 Copilot API 會報錯。
- **異步與執行緒安全**：
    - 所有涉及 Copilot SDK 的通訊必須在「主事件迴圈」(Main Event Loop) 中執行。
    - Telegram Bot 等外部感知層應使用異步啟動，嚴禁開啟獨立執行緒與 SDK 搶奪 stdin/stdout 管道，以避免 `OSError: [Errno 22] Invalid argument`。
- **衍生狀態一致性守則**：當 `orchestrator.py` 的任何程式碼路徑中更新了 `sdk_tools`（例如 Session 升級、重試），**必須**同步重新計算所有由其衍生的狀態，特別是 `route_config.system_prompt` 中的 **Tool Catalog**。禁止在未更新衍生狀態的情況下重建 Session，以防止 AI 產生重複激活的循環。
- **SUPERVISOR Session 不可侵犯原則**：`telegram_6673258916_supervisor` 等主流程 Session 在任何架構升級或優化改動中**必須保持持久性**。Copilot SDK 的 Session 在工具集設定後即鎖定，無法動態修改。任何需要擴充工具的情境，**唯一合法路徑**是透過 `delegate_to_mechanic` 委派給 Sub-agent，絕不允許在 SUPERVISOR 自身重建 Session 以換取工具。違反此原則會導致使用者對話記憶永久消失。
- **事件監聽回收**：確保所有 SDK 事件監聽 (session.on) 都在對話結束後正確呼叫 `unsubscribe()`。
