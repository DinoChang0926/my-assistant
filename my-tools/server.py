import os
import sys
import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

# 初始化 FastMCP
mcp = FastMCP("my-tools")

# 設定基礎目錄
BASE_DIR = Path(__file__).parent.absolute()
ROOT_DIR = BASE_DIR.parent.absolute()
ATOMIC_DIR = BASE_DIR / "atomic"

def load_tools():
    """動態掃描並載入 atomic 目錄下符合 Phase 3a 規範的工具。"""
    if not ATOMIC_DIR.exists():
        print(f"Directory not found: {ATOMIC_DIR}", file=sys.stderr)
        return

    # 加入路徑以便 import
    # 這裡必須包含專案根目錄，否則工具內的 import src.* 會失敗
    paths_to_add = [str(ROOT_DIR), str(BASE_DIR)]
    for p in paths_to_add:
        if p not in sys.path:
            sys.path.insert(0, p)
            print(f"Added to sys.path: {p}", file=sys.stderr)

    for f in ATOMIC_DIR.glob("static_tool_*.py"):
        if f.name.startswith("__"):
            continue
        
        module_name = f"atomic.{f.stem}"
        try:
            # 強制重新載入
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            module = importlib.import_module(module_name)
            
            # 檢查是否有 EXPORTED_TOOLS
            exported_tools = getattr(module, 'EXPORTED_TOOLS', [])
            
            # 如果是空列表，嘗試檢查是否導出了單個工具例項 (Phase 2 legacy support)
            if not exported_tools:
                for name, obj in inspect.getmembers(module):
                    # 檢查是否為 BaseTool 子類別的例項
                    if hasattr(obj, "__class__") and obj.__class__.__name__ == "SendTelegramButtonsTool":
                         # 特例處理或通用檢查
                         exported_tools = [obj]
                         break

            for tool_obj in exported_tools:
                # 判斷是原始函式還是 Copilot Tool 物件
                is_sdk_tool = hasattr(tool_obj, "handler") and hasattr(tool_obj, "name")
                # 判斷是否為類別型工具 (Phase 2 legacy)
                is_class_tool = hasattr(tool_obj, "execute") and hasattr(tool_obj, "parameters")
                
                name = ""
                description = ""
                handler_func = None

                if is_sdk_tool:
                    name = tool_obj.name
                    description = tool_obj.description
                    handler_func = tool_obj.handler
                elif is_class_tool:
                    name = tool_obj.name
                    description = tool_obj.description
                    # MCP tool 必須是 async function
                    async def class_handler(**kwargs):
                        return await tool_obj.execute(**kwargs)
                    handler_func = class_handler
                else:
                    name = tool_obj.__name__
                    description = tool_obj.__doc__ or "No description"
                    handler_func = tool_obj

                if name in ["send_telegram_buttons", "activate_tools"]:
                    print(f"Skipping {name} (not MCP compatible/needed yet)", file=sys.stderr)
                    continue

                # 使用 FastMCP 註冊
                mcp.add_tool(handler_func, name=name, description=description)
                print(f"Registered MCP Tool: {name}", file=sys.stderr)

        except Exception as e:
            import traceback
            print(f"Failed to load module {module_name}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

# 執行載入
load_tools()

if __name__ == "__main__":
    # 支援透過環境變數注入 STORAGE_PATH
    storage_path = os.environ.get("STORAGE_PATH", "storage")
    os.environ["STORAGE_PATH"] = storage_path # 確保子程序或工具能讀到
    
    # 啟動 Server (預設使用 stdio)
    mcp.run()
