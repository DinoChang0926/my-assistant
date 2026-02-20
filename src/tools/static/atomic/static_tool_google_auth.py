from src.tools.base import BaseTool
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path
import pickle
import json

class GoogleAuthTool(BaseTool):
    """
    Google API 認證工具，提供 Service 實例供其他工具使用。
    """

    @property
    def name(self) -> str:
        return "google_auth"

    @property
    def description(self) -> str:
        return "處理 Google API 認證。支援從環境變數或檔案載入憑證，並回傳指定的 API service。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "api_name": {
                    "type": "string",
                    "description": "API 名稱 (e.g., 'gmail', 'calendar', 'drive')"
                },
                "version": {
                    "type": "string",
                    "description": "API 版本 (e.g., 'v1')",
                    "default": "v1"
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要的權限範圍 (Scopes)"
                }
            },
            "required": ["api_name", "scopes"]
        }

    async def execute(self, **kwargs) -> dict:
        # 註：這是一個基礎實作。在實際環境中，驗證流程（特別是 OAuth2 瀏覽器跳轉）
        # 需要在 Agent 啟動前或透過特定指令完成。
        api_name = kwargs.get("api_name")
        version = kwargs.get("version", "v1")
        scopes = kwargs.get("scopes")

        # 預設憑證檔案路徑
        creds_path = "storage/google_credentials.json"
        token_path = "storage/google_token.pickle"

        creds = None
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # 如果沒有憑證或憑證無效，嘗試重新整理或重新驗證
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    return {
                        "status": "error", 
                        "message": f"Missing credentials file at {creds_path}. Please provide client_secret.json."
                    }
                
                # 這裡假設是在可以進行互動的環境（或已有授權）
                # 注意：在完全自動化伺服器中，應優先選用 Service Account
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
                creds = flow.run_local_server(port=0)
                
            # 儲存憑證
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        try:
            # build() 返回的是一個 Resource 物件，通常無法直接轉為 JSON 回傳給 Agent
            # 因此這裡我們回報成功，但在內部工具設計上，其他工具應直接調用此邏輯
            service = build(api_name, version, credentials=creds)
            
            return {
                "status": "success",
                "message": f"Successfully authenticated Google {api_name} {version}.",
                "data": {"api": api_name, "version": version, "scopes": scopes}
            }
        except Exception as e:
            return {"status": "error", "message": f"Google Auth failed: {str(e)}"}
