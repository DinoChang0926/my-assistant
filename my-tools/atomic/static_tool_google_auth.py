import os
import pickle

from copilot.tools import define_tool
from pydantic import BaseModel, Field
from typing import List


class GoogleAuthParams(BaseModel):
    api_name: str = Field(description="API 名稱 (e.g., 'gmail', 'calendar', 'drive')")
    version: str = Field(default="v1", description="API 版本 (e.g., 'v1')")
    scopes: List[str] = Field(description="需要的權限範圍 (Scopes)")


@define_tool(
    description="處理 Google API 認證。支援從環境變數或檔案載入憑證，並回傳指定的 API service。"
)
async def google_auth(params: GoogleAuthParams) -> dict:
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds_path = "storage/google_credentials.json"
    token_path = "storage/google_token.pickle"

    creds = None
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                return {
                    "status": "error",
                    "message": f"Missing credentials file at {creds_path}. Please provide client_secret.json.",
                }
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, params.scopes)
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    try:
        service = build(params.api_name, params.version, credentials=creds)
        return {
            "status": "success",
            "message": f"Successfully authenticated Google {params.api_name} {params.version}.",
            "data": {
                "api": params.api_name,
                "version": params.version,
                "scopes": params.scopes,
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Google Auth failed: {str(e)}"}


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [google_auth]
TOOL_CATEGORY = "authentication"
