import sys; import traceback; import importlib.util
f='my-tools/atomic/static_tool_web_search.py'
spec=importlib.util.spec_from_file_location('test', f)
m=importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(m)
    print('Loaded')
except Exception as e:
    traceback.print_exc()
