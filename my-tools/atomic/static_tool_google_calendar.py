import os
import pickle
from typing import Optional

# Constants
CREDS_PATH = "storage/google_credentials.json"
TOKEN_PATH = "storage/google_calendar_token.pickle"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_credentials():
    """從本機讀取或更新憑證。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)

    return creds if creds and creds.valid else None


async def google_calendar(
    action: str,
    auth_code: str = "",
    calendar_id: str = "",
    summary: str = "",
    description: str = "",
    start_time: str = "",
    end_time: str = "",
) -> dict:
    """
    管理 Google Calendar 的工具。支援操作(action)：
    - 'get_auth_url': 取得授權連結 (若尚未驗證)。
    - 'complete_auth': 接受 'auth_code' 完成授權。
    - 'list_calendars': 列出所有行事曆。
    - 'create_calendar': 建立新行事曆 (需要 'summary')。
    - 'create_event': 在指定行事曆新增事件 (需要 'calendar_id', 'summary', 'start_time', 'end_time')。
    """
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow

    if action == "get_auth_url":
        if not os.path.exists(CREDS_PATH):
            return {
                "status": "error",
                "message": f"找不到憑證檔案 '{CREDS_PATH}'。請先上傳 client_secret.json 並重新命名。",
            }
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDS_PATH, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
        )
        auth_url, _ = flow.authorization_url(prompt="consent")
        return {
            "status": "success",
            "message": "請點擊以下連結進行授權，並將取得的授權碼回傳給我：",
            "auth_url": auth_url,
            "hint": "回傳格式請使用：呼叫 google_calendar (action='complete_auth', auth_code='...') ",
        }

    if action == "complete_auth":
        if not auth_code:
            return {"status": "error", "message": "缺少 'auth_code' 參數。"}
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDS_PATH, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
            )
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            with open(TOKEN_PATH, "wb") as token:
                pickle.dump(creds, token)
            return {
                "status": "success",
                "message": "Google Calendar 授權成功！現在你可以要求我建立事件或查看行事曆了。",
            }
        except Exception as e:
            return {"status": "error", "message": f"授權碼兌換失敗: {str(e)}"}

    # Actions requiring API service
    creds = _get_credentials()
    if not creds:
        return {
            "status": "unauthorized",
            "message": "尚未授權 Google Calendar 或授權已過期。",
            "next_step": "請先呼叫 google_calendar (action='get_auth_url') 取得授權連結。",
        }

    service = build("calendar", "v3", credentials=creds)

    try:
        if action == "list_calendars":
            calendar_list = service.calendarList().list().execute()
            calendars = []
            for entry in calendar_list.get("items", []):
                calendars.append({
                    "id": entry.get("id"),
                    "summary": entry.get("summary"),
                    "primary": entry.get("primary", False),
                })
            return {"status": "success", "calendars": calendars}

        elif action == "create_calendar":
            if not summary:
                return {
                    "status": "error",
                    "message": "建立行事曆需要 'summary' 參數。",
                }
            calendar_body = {"summary": summary, "timeZone": "Asia/Taipei"}
            created_calendar = service.calendars().insert(body=calendar_body).execute()
            return {
                "status": "success",
                "id": created_calendar.get("id"),
                "summary": summary,
            }

        elif action == "create_event":
            target_calendar_id = calendar_id or "primary"
            if not summary or not start_time or not end_time:
                return {
                    "status": "error",
                    "message": "建立事件需要 'summary', 'start_time', 'end_time'。",
                }
            event_body = {
                "summary": summary,
                "description": description or "",
                "start": {
                    "dateTime": start_time,
                    "timeZone": "Asia/Taipei",
                },
                "end": {"dateTime": end_time, "timeZone": "Asia/Taipei"},
            }
            event = (
                service.events()
                .insert(calendarId=target_calendar_id, body=event_body)
                .execute()
            )
            return {
                "status": "success",
                "event_id": event.get("id"),
                "htmlLink": event.get("htmlLink"),
                "message": f"已成功在 {target_calendar_id} 建立事件：{summary}",
            }

        else:
            return {"status": "error", "message": f"未知的 action: {action}"}

    except Exception as e:
        return {
            "status": "error",
            "message": f"Google Calendar API 呼叫失敗: {str(e)}",
        }
