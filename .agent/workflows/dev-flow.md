---
description: 標準開發流程：語法驗證 -> 本機測試 -> Docker 驗證 -> 更新 README
---

本工作流定義了在 `my-assistant` 專案中開發新功能的標準步驟，以確保開發效率與部署穩定性。

### 1. 程式碼編寫與靜態驗證 (Static Validation)
- **語法檢查**：修改任何 `.py` 檔案後，必須先對**所有變更的檔案**執行靜態語法驗證，確保語法無誤。

// turbo
```powershell
python -c "
import ast, sys
files = [  # ← 替換為本次修改的檔案清單
    'src/brain/orchestrator.py',
    'src/perception/rest_api.py',
]
ok = True
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'[OK] {f}')
    except SyntaxError as e:
        print(f'[FAIL] {f}: {e}')
        ok = False
if not ok: sys.exit(1)
"
```

- **工具 Schema 驗證**：若新增了動態工具，確認 `parameters` 符合 JSON Schema 規範：
  - `type: array` 必須包含 `items`
  - `type: object` 必須包含 `properties`
  - 系統啟動時 ToolRegistry 會自動攔截不合法的工具並印出警告

### 2. 測試執行 (Test Execution)
- **單元測試**：語法驗證通過後，必須執行 `pytest` 確認既有測試不被破壞。

// turbo
```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

- **測試同步**：若本次變更涉及架構重構（如方法簽名變更、模組搬遷），須檢查 `tests/` 下是否有測試依賴了被修改的介面，並同步更新或移除已失效的測試。

### 3. 本機環境開發與測試 (Local Development)
- **環境**：務必使用虛擬環境 (`venv`) 啟動。
- **Windows 執行**：
// turbo
```powershell
.\venv\Scripts\python.exe -m src.main
```
- **Linux/macOS 執行**：
```bash
python -m src.main
```
- **驗證**：觀察啟動 log 確認所有工具正常載入，透過 Telegram 或 REST API 驗證功能。

### 4. Docker 環境驗證 (Container Validation)
- **建置**：本機測試成功後，執行 `wsl docker compose build`。
- **啟動**：執行 `wsl docker compose up -d`。
- **驗證**：確保 Dockerfile 的權限設定、相依套件與 Volume 掛載在容器內運作正常。

### 5. 文件同步更新 (Documentation) ← 必做，勿跳過
- **同一次對話內更新**：功能開發完成並驗證後，必須在**同一次對話 (session)** 內完成 `README.md` 的更新，不可等到下次對話再補。
- **更新範圍**：
  - 若新增工具 → 更新 `## 🧰 內建原子工具` 表格
  - 若修改架構 → 更新 `## 🧠 記憶系統架構` 或 `## 📁 目錄結構`
  - 若修復常見問題 → 更新 `### 4. 常見問題 (Troubleshooting)`
