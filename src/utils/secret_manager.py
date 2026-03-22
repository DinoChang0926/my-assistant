import os
import json
import logging
import base64
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseSecretStore(ABC):
    @abstractmethod
    def get_secret(self, service: str, username: str) -> Optional[str]:
        pass

    @abstractmethod
    def set_secret(self, service: str, username: str, password: str) -> bool:
        pass

    @abstractmethod
    def delete_secret(self, service: str, username: str) -> bool:
        pass

class EnvSecretStore(BaseSecretStore):
    """
    優先順序 1: 從環境變數讀取 (唯讀)
    這適用於 Docker 中從外部注入的安全變數。
    格式預設為: {SERVICE}_{USERNAME} (並全轉大寫，如: SMTP_ALICE@EXAMPLE.COM)
    """
    def get_secret(self, service: str, username: str) -> Optional[str]:
        env_key = f"{service}_{username}".upper()
        # 由於 @ 等符號在 ENV 中可能不合法，也允許底線轉換的版本
        safe_env_key = env_key.replace("@", "_").replace(".", "_")
        return os.getenv(env_key) or os.getenv(safe_env_key)

    def set_secret(self, service: str, username: str, password: str) -> bool:
        # 環境變數通常不建議在這裡動態寫入 (不會持久化)，所以總是回傳 False 讓後果處理
        return False

    def delete_secret(self, service: str, username: str) -> bool:
        return False

class KeyringSecretStore(BaseSecretStore):
    """
    優先順序 2: O.S 原生 Credential Manager
    """
    def __init__(self):
        try:
            import keyring
            self.keyring = keyring
            self._available = True
        except ImportError:
            self.keyring = None
            self._available = False
            logger.warning("Keyring module not installed. OS native secret storage disabled.")

    def get_secret(self, service: str, username: str) -> Optional[str]:
        if not self._available:
            return None
        try:
            return self.keyring.get_password(service, username)
        except Exception as e:
            logger.debug(f"Failed to get secret from keyring: {e}")
            return None

    def set_secret(self, service: str, username: str, password: str) -> bool:
        if not self._available:
            return False
        try:
            self.keyring.set_password(service, username, password)
            return True
        except Exception as e:
            logger.debug(f"Failed to set secret to keyring: {e}")
            return False

    def delete_secret(self, service: str, username: str) -> bool:
        if not self._available:
            return False
        try:
            self.keyring.delete_password(service, username)
            return True
        except Exception as e:
            # 可能本來就不存在
            return False

class EncryptedFileSecretStore(BaseSecretStore):
    """
    優先順序 3: Docker 或無 Keyring 系統的 Fallback
    存在 `storage/.secrets.enc`，並使用 `SECRET_MASTER_KEY` 進行 Fernet 對稱加密
    """
    def __init__(self, file_path: str = "storage/.secrets.enc"):
        self.file_path = file_path
        self._available = False
        try:
            from cryptography.fernet import Fernet
            self.Fernet = Fernet
            self._init_master_key()
            self.fernet = self.Fernet(self.master_key.encode())
            self._available = True
            
            # 確保檔案存在
            if not os.path.exists(self.file_path):
                # 確保目錄存在
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                self._save_data({})
        except ImportError:
            logger.warning("cryptography module not installed. Encrypted file storage disabled.")
        except Exception as e:
            logger.error(f"Encrypted file storage failed to initialize: {e}")

    def _init_master_key(self):
        key = os.getenv("SECRET_MASTER_KEY")
        if not key:
            key = self.Fernet.generate_key().decode()
            logger.warning("No SECRET_MASTER_KEY found in environment! Generated a new one.")
            logger.warning("If running in Docker, your secrets WILL BE LOST across container rebuilds")
            logger.warning("Recommend adding SECRET_MASTER_KEY to your .env file.")
            self._append_key_to_env_file(key)
        self.master_key = key

    def _append_key_to_env_file(self, key: str):
        try:
            # Check if SECRET_MASTER_KEY already exists to prevent duplicates
            env_path = ".env"
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("SECRET_MASTER_KEY="):
                            return
            with open(env_path, "a") as f:
                f.write(f"\n# Auto-generated. Keep this safe to retain your stored secrets.\nSECRET_MASTER_KEY={key}\n")
        except Exception as e:
            logger.error(f"Failed to auto-save SECRET_MASTER_KEY to .env: {e}")

    def _load_data(self) -> dict:
        try:
            with open(self.file_path, "rb") as f:
                encrypted_data = f.read()
            if not encrypted_data:
                return {}
            decrypted_data = self.fernet.decrypt(encrypted_data).decode()
            return json.loads(decrypted_data)
        except Exception as e:
            logger.error(f"Failed to load encrypted secret file: {e}")
            return {}

    def _save_data(self, data: dict):
        try:
            json_str = json.dumps(data)
            encrypted_data = self.fernet.encrypt(json_str.encode())
            with open(self.file_path, "wb") as f:
                f.write(encrypted_data)
        except Exception as e:
            logger.error(f"Failed to save encrypted secret file: {e}")

    def get_secret(self, service: str, username: str) -> Optional[str]:
        if not self._available:
            return None
        data = self._load_data()
        return data.get(service, {}).get(username)

    def set_secret(self, service: str, username: str, password: str) -> bool:
        if not self._available:
            return False
        data = self._load_data()
        if service not in data:
            data[service] = {}
        data[service][username] = password
        self._save_data(data)
        return True

    def delete_secret(self, service: str, username: str) -> bool:
        if not self._available:
            return False
        data = self._load_data()
        if service in data and username in data[service]:
            del data[service][username]
            if not data[service]:
                del data[service]
            self._save_data(data)
            return True
        return False

class SecretManagerFacade:
    def __init__(self):
        self.stores = [
            EnvSecretStore(),
            KeyringSecretStore(),
            EncryptedFileSecretStore()
        ]

    def get(self, service: str, username: str) -> Optional[str]:
        for store in self.stores:
            val = store.get_secret(service, username)
            if val is not None:
                return val
        return None

    def set(self, service: str, username: str, password: str) -> bool:
        # 從優先級高的開始嘗試 Set (Env跳過，因為那不是持久化儲存)，通常是 Keyring
        # 如果 Keyring 失敗，則 fallback 到 File
        for store in self.stores[1:]:
            if store.set_secret(service, username, password):
                logger.info(f"Successfully stored secret for {service}/{username} using {store.__class__.__name__}")
                return True
        return False

    def delete(self, service: str, username: str) -> bool:
        # 刪除時嘗試所有的 Store 免得有殘留
        success = False
        for store in self.stores[1:]:
            if store.delete_secret(service, username):
                success = True
        return success

# Global instance
SecretManager = SecretManagerFacade()
