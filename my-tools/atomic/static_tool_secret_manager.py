import logging
from typing import Dict, Any
from src.tools.base import BaseTool
from src.utils.secret_manager import SecretManager

logger = logging.getLogger(__name__)

class SecretManagerStoreTool(BaseTool):
    name = "secret_manager_store"
    description = "安全儲存各種服務或 API 的機密資訊（如密碼、Token）。資料不論是存入作業系統管理器或本機加密檔案，都不會以明文外流。"
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "服務名稱，如 'SMTP', 'GITHUB', 'GOOGLE_CALENDAR'"
            },
            "username": {
                "type": "string",
                "description": "該服務對應的帳號或識別碼，如 'alice@example.com' 或 'bot'"
            },
            "password": {
                "type": "string",
                "description": "要儲存的密碼或 Token 值"
            }
        },
        "required": ["service", "username", "password"]
    }

    async def execute(self, **kwargs) -> str:
        service = kwargs.get("service")
        username = kwargs.get("username")
        password = kwargs.get("password")
        
        success = SecretManager.set(service, username, password)
        if success:
            logger.info(f"Store secret {service}/{username} successful.")
            return f"Secret for {service} (User: {username}) has been stored securely."
        else:
            logger.error(f"Failed to store secret for {service}/{username}")
            return "Failed to store secret securely. Check system logs."

class SecretManagerReadTool(BaseTool):
    name = "secret_manager_read"
    description = "從安全儲存庫中讀取機密資訊。讀取的憑證僅限於內部 API 呼叫使用，絕對不要用自然語言向使用者直接印出原本的密碼！"
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "服務名稱，如 'SMTP', 'GITHUB'"
            },
            "username": {
                "type": "string",
                "description": "該服務對應的帳號或識別碼"
            }
        },
        "required": ["service", "username"]
    }

    async def execute(self, **kwargs) -> str:
        service = kwargs.get("service")
        username = kwargs.get("username")
        
        val = SecretManager.get(service, username)
        if val:
            logger.info(f"Read secret {service}/{username} successful.")
            return val
        else:
            return f"Secret for {service} (User: {username}) not found."

class SecretManagerDeleteTool(BaseTool):
    name = "secret_manager_delete"
    description = "從安全儲存庫中徹底刪除某一組機密資訊。"
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "服務名稱"
            },
            "username": {
                "type": "string",
                "description": "帳號或識別碼"
            }
        },
        "required": ["service", "username"]
    }

    async def execute(self, **kwargs) -> str:
        service = kwargs.get("service")
        username = kwargs.get("username")
        
        success = SecretManager.delete(service, username)
        if success:
            return f"Secret for {service} (User: {username}) deleted successfully."
        else:
            return f"Secret for {service} (User: {username}) not found or could not be deleted."
