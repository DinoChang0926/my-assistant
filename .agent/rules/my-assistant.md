---
trigger: always_on
---

# 專案開發規範

- **工作流強制執行協定 (Workflow-First Protocol)**：任何涉及 `src/` 變更的任務，**必須**優先讀取對應的工作流檔案（如 `.agent/workflows/dev-flow.md`），並透過 todo list 追蹤其步驟的完成狀態。禁止跳過任何標註為「必做」的步驟（如同步更新文件）。
- **同步更新文件**：依照 `.agent/workflows/dev-flow.md` 第 4 步規範執行。功能驗證後，必須在**同一次對話 (session)** 內同步更新 `README.md`，不可留待後續對話補充。
- **任務交付合規表 (Compliance Table)**：在向使用者交付最終成果前，必須在對話中列出合規表，逐一確認工作流中所有必要步驟（語法檢查、本機測試、文件同步）是否已完成。未達標前禁止宣告任務結束。
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
- **事件監聽回收**：確保所有 SDK 事件監聯 (session.on) 都在對話結束後正確呼叫 `unsubscribe()`。
- **Import 集中管理**：所有 `import` 語句必須置於檔案頂部的 import 區塊。禁止在函式體、closure 或 except 區塊內散落 `import`（唯一例外：為避免循環依賴而刻意延遲的 import，須加上 `# deferred import` 註解說明原因）。
- **禁止破壞性檔案操作**：程式碼中嚴禁對使用者原始碼或工具檔案執行 `rename`、`unlink`、`remove` 等不可逆操作。載入失敗的模組應記錄至記憶體黑名單（如 `_broken_modules`），不得自動改名或刪除原始檔案。

# 依賴管理守則

- **單一事實來源 (Single Source of Truth)**：`pyproject.toml` 為專案依賴的唯一定義來源。`requirements.txt` 應由 `pip-compile` 或等效工具自動生成，禁止手動編輯版本。兩者的套件清單必須保持一致。
- **白名單自動同步**：`code_validator.py` 中的 `ALLOWED_MODULES` 應從 `requirements.txt` 動態解析，不得硬編碼第三方套件名稱。新增依賴時只需更新 `pyproject.toml` 並重新生成 lock file。

# 目錄與檔案收納守則

- **測試集中管理**：所有撰寫的測試程式碼（不論單元測試、整合測試），**必須**統一放置於 `tests/` 目錄下管理，保持專案根目錄整潔。
- **除錯與專用腳本集中管理**：所有用來臨時除錯、實驗功能或特定任務的獨立腳本（如 `debug_*.py`, `diagnose_*.py` 等），**必須**統一收納於 `scripts/` 目錄內。
- **測試與程式碼同步**：當架構變更導致方法簽名、模組路徑或核心流程改變時，**必須**同步檢查 `tests/` 下是否有測試依賴了被修改的介面，並於同一次對話內更新或移除已失效的測試。禁止留下測試對象為空殼或已不存在之方法的測試檔案。
