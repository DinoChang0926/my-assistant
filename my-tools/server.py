import os
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# 初始化 FastMCP
mcp = FastMCP("my-tools")

# 設定基礎目錄以便 import atomic 工具與 src
BASE_DIR = Path(__file__).parent.absolute()
ROOT_DIR = BASE_DIR.parent.absolute()

for p in [str(BASE_DIR), str(ROOT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# 匯入所有已改寫的原子工具函式
from atomic.static_tool_web_search import web_search
from atomic.static_tool_url_fetcher import url_fetcher
from atomic.static_tool_local_memory import local_memory
from atomic.static_tool_secret_manager import (
    secret_manager_store,
    secret_manager_read,
    secret_manager_delete
)
from atomic.static_tool_google_auth import google_auth
from atomic.static_tool_google_calendar import google_calendar
from atomic.static_tool_schedule_reminder import schedule_reminder
from atomic.static_tool_log_reader import log_reader

# 註冊工具
for fn in [
    web_search, url_fetcher, local_memory,
    secret_manager_store, secret_manager_read, secret_manager_delete,
    google_auth, google_calendar, schedule_reminder,
    log_reader
]:
    mcp.tool()(fn)

if __name__ == "__main__":
    # 支援透過環境變數注入 STORAGE_PATH
    storage_path = os.environ.get("STORAGE_PATH", "storage")
    os.environ["STORAGE_PATH"] = storage_path
    
    mcp.run()
