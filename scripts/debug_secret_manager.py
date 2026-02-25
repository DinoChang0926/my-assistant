import sys
import os

# 確保可以 import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.secret_manager import SecretManager

if __name__ == "__main__":
    service = sys.argv[1] if len(sys.argv) > 1 else "DOCKER_TEST"
    username = sys.argv[2] if len(sys.argv) > 2 else "docker_user"
    password = sys.argv[3] if len(sys.argv) > 3 else "docker_password_123"
    
    # 嘗試儲存
    print(f"[{os.getenv('HOSTNAME', 'Local')}] Attempting to store {service}/{username}...")
    success = SecretManager.set(service, username, password)
    
    if success:
        print("Set operation returned True.")
    else:
        print("Set operation returned False.")
    
    # 嘗試讀回
    val = SecretManager.get(service, username)
    print(f"Read back value: {val}")
