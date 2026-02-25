import os
import pytest
from src.utils.secret_manager import SecretManagerFacade, EnvSecretStore, EncryptedFileSecretStore

@pytest.fixture
def secret_manager():
    # 建立一個新的 Facade 用於測試
    sm = SecretManagerFacade()
    return sm

def test_env_secret_store(monkeypatch):
    """測試環境變數是否擁有最高讀取優先權"""
    # 模擬環境變數
    monkeypatch.setenv("TESTSERVICE_ALICE_EXAMPLE_COM", "my_env_password")
    
    store = EnvSecretStore()
    # 測試正常格式
    assert store.get_secret("TESTSERVICE", "alice@example.com") == "my_env_password"
    # 確保 set_secret 對 Env 無效
    assert store.set_secret("TESTSERVICE", "bob", "new_pw") == False

def test_encrypted_file_fallback(tmp_path, monkeypatch):
    """測試加密檔案的寫入與讀取"""
    test_file = str(tmp_path / ".secrets.enc")
    
    # 強制塞入一把 master key 避免自動寫入當前目錄的 .env
    # 必須是一組 32 bit URL-safe Base64，這裡我們用 `Fernet.generate_key().decode()` 產生的範例
    monkeypatch.setenv("SECRET_MASTER_KEY", "b4A8c-i0kS0HnI2q9bJ8Z6YyXwVuT7s_RpNfM5lQ3eA=") 
    
    store = EncryptedFileSecretStore(file_path=test_file)
    assert store._available == True, "Cryptography module should be available"
    
    # 寫入
    success = store.set_secret("TEST_GITHUB", "bot", "gh_token_123")
    assert success == True
    
    # 讀取
    assert store.get_secret("TEST_GITHUB", "bot") == "gh_token_123"
    
    # 讀取不存在的
    assert store.get_secret("TEST_GITHUB", "not_exist") == None
    
    # 刪除
    assert store.delete_secret("TEST_GITHUB", "bot") == True
    assert store.get_secret("TEST_GITHUB", "bot") == None

def test_secret_manager_facade(monkeypatch, tmp_path):
    """測試 Facade 整合是否會正確 Fallback"""
    # 覆寫 EncryptedFile 的路徑
    test_file = str(tmp_path / ".secrets_facade.enc")
    monkeypatch.setenv("SECRET_MASTER_KEY", "uL4C0wS8mK9xN3jY6vF1_zP5bA2eRqH7tXyM0gWvJ3I=")
    
    sm = SecretManagerFacade()
    # 手動替換掉底下的 FileStore 路徑以避免污染
    for store in sm.stores:
        if isinstance(store, EncryptedFileSecretStore):
            store.file_path = test_file
            # 觸發重新檢查
            store._init_master_key()
            if not os.path.exists(store.file_path):
                store._save_data({})
    
    # 寫入 (可能會寫入 Keyring 或 File)
    sm.set("MOCK_SERVICE", "test_user", "super_secret")
    
    # 讀取 (從 Facade)
    assert sm.get("MOCK_SERVICE", "test_user") == "super_secret"

    # 如果 Env 存在更好的，應該要讀取 Env (最高優先)
    monkeypatch.setenv("MOCK_SERVICE_TEST_USER", "env_override_secret")
    assert sm.get("MOCK_SERVICE", "test_user") == "env_override_secret"

    # 刪除
    sm.delete("MOCK_SERVICE", "test_user")
    
    # 刪除後不該存在 (先把 env 解除以測試底層)
    monkeypatch.delenv("MOCK_SERVICE_TEST_USER", raising=False)
    assert sm.get("MOCK_SERVICE", "test_user") == None
