import logging

from copilot.tools import define_tool
from pydantic import BaseModel, Field
from src.utils.secret_manager import SecretManager

logger = logging.getLogger(__name__)


# --- secret_manager_store ---

class SecretStoreParams(BaseModel):
    service: str = Field(
        description="服務名稱，如 'SMTP', 'GITHUB', 'GOOGLE_CALENDAR'"
    )
    username: str = Field(
        description="該服務對應的帳號或識別碼，如 'alice@example.com' 或 'bot'"
    )
    password: str = Field(description="要儲存的密碼或 Token 值")


@define_tool(
    description=(
        "安全儲存各種服務或 API 的機密資訊（如密碼、Token）。"
        "資料不論是存入作業系統管理器或本機加密檔案，都不會以明文外流。"
    )
)
async def secret_manager_store(params: SecretStoreParams) -> str:
    success = SecretManager.set(params.service, params.username, params.password)
    if success:
        logger.info(f"Store secret {params.service}/{params.username} successful.")
        return f"Secret for {params.service} (User: {params.username}) has been stored securely."
    else:
        logger.error(f"Failed to store secret for {params.service}/{params.username}")
        return "Failed to store secret securely. Check system logs."


# --- secret_manager_read ---

class SecretReadParams(BaseModel):
    service: str = Field(description="服務名稱，如 'SMTP', 'GITHUB'")
    username: str = Field(description="該服務對應的帳號或識別碼")


@define_tool(
    description=(
        "從安全儲存庫中讀取機密資訊。"
        "讀取的憑證僅限於內部 API 呼叫使用，絕對不要用自然語言向使用者直接印出原本的密碼！"
    )
)
async def secret_manager_read(params: SecretReadParams) -> str:
    val = SecretManager.get(params.service, params.username)
    if val:
        logger.info(f"Read secret {params.service}/{params.username} successful.")
        return val
    else:
        return f"Secret for {params.service} (User: {params.username}) not found."


# --- secret_manager_delete ---

class SecretDeleteParams(BaseModel):
    service: str = Field(description="服務名稱")
    username: str = Field(description="帳號或識別碼")


@define_tool(description="從安全儲存庫中徹底刪除某一組機密資訊。")
async def secret_manager_delete(params: SecretDeleteParams) -> str:
    success = SecretManager.delete(params.service, params.username)
    if success:
        return f"Secret for {params.service} (User: {params.username}) deleted successfully."
    else:
        return f"Secret for {params.service} (User: {params.username}) not found or could not be deleted."


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [secret_manager_store, secret_manager_read, secret_manager_delete]
TOOL_CATEGORY = "general"
