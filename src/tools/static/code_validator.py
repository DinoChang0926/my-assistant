import ast
from pathlib import Path

# pip 套件名 → Python import 名對應（僅處理名稱不一致的情況）
_PIP_TO_IMPORT: dict = {
    'beautifulsoup4': 'bs4',
    'python-telegram-bot': 'telegram',
    'google-api-python-client': 'googleapiclient',
    'google-auth-httplib2': 'google',
    'google-auth-oauthlib': 'google',
    'duckduckgo-search': 'duckduckgo_search',
    'pydantic-settings': 'pydantic_settings',
    'python-dotenv': 'dotenv',
    'github-copilot-sdk': 'copilot',
    'PyGithub': 'github',
    'mplfinance': 'mplfinance',
}

# 永遠允許的核心模組（Python 標準庫 + 內部模組）
_CORE_MODULES: set = {
    'src', 'src.tools.base', 'src.brain.prompts',
    'sys', 'os', 'asyncio', 'json', 'datetime', 'time', 're', 'math',
    'random', 'pathlib', 'traceback', 'smtplib', 'ssl', 'email',
    'email.mime.text', 'email.mime.multipart', 'email.message',
    'collections', 'itertools', 'functools', 'typing', 'abc',
    'hashlib', 'base64', 'urllib', 'http', 'io', 'copy', 'uuid',
}


def _load_allowed_from_requirements() -> set:
    """從 requirements.txt 動態解析允許的第三方套件 import 名稱。"""
    # code_validator.py → static → tools → src → project_root → requirements.txt
    req_file = Path(__file__).resolve().parents[3] / "requirements.txt"
    modules: set = set()
    if not req_file.exists():
        return modules
    for line in req_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # 去除版本限定、extras 與 URL（e.g. requests>=2.0, uvicorn[standard]）
        pkg = line.split('>')[0].split('<')[0].split('=')[0].split('[')[0].strip()
        if not pkg:
            continue
        import_name = _PIP_TO_IMPORT.get(pkg, pkg.replace('-', '_'))
        modules.add(import_name)
    return modules


# 模組啟動時建立一次，後續皆引用此 set
ALLOWED_MODULES: set = _CORE_MODULES | _load_allowed_from_requirements()

# 定義禁止的危險操作
BANNED_FUNCTIONS = {'os.system', 'subprocess.run', 'subprocess.Popen', 'subprocess.call', 'eval', 'exec'}

def validate_tool_code(code: str) -> tuple[bool, list[str]]:
    """
    驗證 Python 代碼是否符合 Tool 規範：
    1. 嚴格檢查 Import 白名單
    2. 禁止危險操作 (os.system, subprocess, eval 等)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax Error: {e}"]

    errors = []
    
    for node in ast.walk(tree):

        # 2. 檢查 Import 白名單
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name not in ALLOWED_MODULES and alias.name not in ALLOWED_MODULES:
                        errors.append(f"Security Error: Import of '{alias.name}' is not allowed.")
            else: # ImportFrom
                if node.module:
                    module_base = node.module.split('.')[0]
                    if module_base not in ALLOWED_MODULES and node.module not in ALLOWED_MODULES:
                        errors.append(f"Security Error: Import from '{node.module}' is not allowed.")

        # 3. 檢查危險函數
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # 處理 os.system 這種情況
                if isinstance(node.func.value, ast.Name):
                    func_name = f"{node.func.value.id}.{node.func.attr}"
                
            if func_name in BANNED_FUNCTIONS:
                errors.append(f"Security Error: Call to banned function '{func_name}' is forbidden.")

    return len(errors) == 0, errors
