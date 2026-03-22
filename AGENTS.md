# Agent Definition

## System Instructions
- **Rule Enforcement**: 在執行任何操作或生成程式碼前，必須先讀取並遵循根目錄下的 `.agents/rules/my-assistant.md`。
- **Consistency**: 所有的輸出邏輯必須與 `.agents/rules/my-assistant.md` 中定義的 [架構規範/命名準則] 保持 100% 一致。
- **Pre-flight Check**: 若 `.agents/rules/my-assistant.md` 與當前指令衝突，以 `.agents/rules/my-assistant.md` 為準。