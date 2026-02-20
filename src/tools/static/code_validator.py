import ast

# 定義允許的模組白名單 (標準庫 + requirements.txt)
ALLOWED_MODULES = {
    'src', 'src.tools.base', 'src.brain.prompts',
    'asyncio', 'json', 'datetime', 'time', 're', 'math', 'random', 'pathlib',
    'pandas', 'yfinance', 'requests', 'beautifulsoup4', 'bs4', 'duckduckgo_search',
    'googleapiclient', 'google', 'ta', 'matplotlib', 'mplfinance', 'numpy', 'pydantic'
}

# 定義禁止的危險操作
BANNED_FUNCTIONS = {'os.system', 'subprocess.run', 'subprocess.Popen', 'subprocess.call', 'eval', 'exec'}

def validate_tool_code(code: str) -> tuple[bool, list[str]]:
    """
    驗證 Python 代碼是否符合 Tool 規範：
    1. 必須包含 Class 定義
    2. Class 必須繼承 BaseTool
    3. 嚴格檢查 Import 白名單
    4. 禁止危險操作 (os.system, subprocess, eval 等)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax Error: {e}"]

    errors = []
    has_class = False
    inherits_base_tool = False
    
    for node in ast.walk(tree):
        # 1. 檢查 Class 定義
        if isinstance(node, ast.ClassDef):
            has_class = True
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == 'BaseTool':
                    inherits_base_tool = True
                elif isinstance(base, ast.Attribute) and base.attr == 'BaseTool':
                    inherits_base_tool = True

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

    if not has_class:
        errors.append("Code must define a Python Class.")
    if not inherits_base_tool:
        errors.append("The Class must inherit from 'BaseTool' (or 'src.tools.base.BaseTool').")

    return len(errors) == 0, errors
