import ast
from typing import List, Tuple

class SafetyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []
        self.has_base_tool = False
        self.has_execute = False
        
        # Blacklisted modules
        self.unsafe_modules = {
            "os", "sys", "subprocess", "shutil", 
            "multiprocessing", "socket", "ctypes", "pickle"
        }
        
        # Blacklisted functions
        self.unsafe_calls = {
            "eval", "exec", "compile", "__import__", "open"
        }

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split('.')[0] in self.unsafe_modules:
                self.errors.append(f"Importing unsafe module '{alias.name}' is prohibited.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.split('.')[0] in self.unsafe_modules:
            self.errors.append(f"Importing from unsafe module '{node.module}' is prohibited.")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in self.unsafe_calls:
                self.errors.append(f"Calling unsafe function '{node.func.id}' is prohibited.")
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Check if class inherits from BaseTool
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseTool":
                self.has_base_tool = True
                # Check for execute method
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and item.name == "execute":
                        self.has_execute = True
        self.generic_visit(node)

def validate_tool_code(code: str) -> Tuple[bool, List[str]]:
    """
    Validates the Python code for safety and structure.
    Returns (is_valid, error_messages).
    """
    errors = []
    
    # 1. Line count check
    if len(code.splitlines()) > 200:
        errors.append("Code exceeds 200 lines limit.")
        return False, errors

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        errors.append(f"Syntax Error: {e}")
        return False, errors

    visitor = SafetyVisitor()
    visitor.visit(tree)
    errors.extend(visitor.errors)

    if not visitor.has_base_tool:
        errors.append("Code must contain a class inheriting from 'BaseTool'.")
    if visitor.has_base_tool and not visitor.has_execute:
        errors.append("The tool class must implement an async 'execute' method.")

    return len(errors) == 0, errors
