---
description: 標準開發流程：本機測試 -> Docker 驗證 -> 更新 README
---

本工作流定義了在 `my-assistant` 專案中開發新功能的標準步驟，以確保開發效率與部署穩定性。

### 1. 本機環境開發與測試 (Local Development)
- **環境**：務必在開啟虛擬環境 (`venv`) 的情況下進行開發。
- **執行**：使用 `python -m src.main` 啟動應用程式。
- **優點**：啟動速度快，除錯資訊完整，方便快速迭代。
- **驗證**：開發完成後，撰寫或使用現有的測試腳本（如 `urllib` 版本）確保功能邏輯無誤。

### 2. Docker 環境驗證 (Container Validation)
- **建置**：本機測試成功後，執行 `wsl docker compose build`。
- **啟動**：執行 `wsl docker compose up -d`。
- **驗證**：確保 Dockerfile 的權限設定、相依套件與 Volume 掛載在容器內運作正常。

### 3. 文件同步更新 (Documentation)
- **更新 README**：所有的功能與部署驗證完成後，同步更新專案根目錄的 `README.md`，反映最新的功能特性或操作方式。
