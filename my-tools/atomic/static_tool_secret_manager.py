import logging
from src.utils.secret_manager import SecretManager

logger = logging.getLogger(__name__)

async def secret_manager_store(service: str, username: str, password: str) -> str:
    """
    安全儲存各種服務或 API 的機密資訊（如密碼、Token）。
    資料不論是存入作業系統管理器或本機加密檔案，都不會以明文外流。

    :param service: 服務名稱，如 'SMTP', 'GITHUB', 'GOOGLE_CALENDAR'
    :param username: 該服務對應的帳號或識別碼，如 'alice@example.com' 或 'bot'
    :param password: 要儲存的密碼或 Token 值
    """
    success = SecretManager.set(service, username, password)
    if success:
        logger.info(f"Store secret {service}/{username} successful.")
        return f"Secret for {service} (User: {username}) has been stored securely."
    else:
        logger.error(f"Failed to store secret for {service}/{username}")
        return "Failed to store secret securely. Check system logs."


async def secret_manager_read(service: str, username: str) -> str:
    """
    從安全儲存庫中讀取機密資訊。
    讀取的憑證僅限於內部 API 呼叫使用，絕對不要用自然語言向使用者直接印出原本的密碼！

    :param service: 服務名稱，如 'SMTP', 'GITHUB'
    :param username: 該服務對應的帳號或識別碼
    """
    val = SecretManager.get(service, username)
    if val:
        logger.info(f"Read secret {service}/{username} successful.")
        return val
    else:
        return f"Secret for {service} (User: {username}) not found."


async def secret_manager_delete(service: str, username: str) -> str:
    """從安全儲存庫中徹底刪除某一組機密資訊。"""
    success = SecretManager.delete(service, username)
    if success:
        return f"Secret for {service} (User: {username}) deleted successfully."
    else:
        return f"Secret for {service} (User: {username}) not found or could not be deleted."
