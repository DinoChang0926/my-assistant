import os
import pickle
from typing import List

async def google_auth(api_name: str, scopes: List[str], version: str = "v1") -> dict:
    """
    處理 Google API 認證。支援從環境變數或檔案載入憑證，並回傳指定的 API service。
    
    :param api_name: API 名稱 (e.g., 'gmail', 'calendar', 'drive')
    :param scopes: 需要的權限範圍 (Scopes)
    :param version: API 版本 (e.g., 'v1')
    """
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
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    try:
        service = build(api_name, version, credentials=creds)
        return {
            "status": "success",
            "message": f"Successfully authenticated Google {api_name} {version}.",
            "data": {
                "api": api_name,
                "version": version,
                "scopes": scopes,
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Google Auth failed: {str(e)}"}
