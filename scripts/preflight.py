import os, sys, importlib.util
WD = os.getcwd()
p = os.path.join(WD, "main.py")
if not os.path.exists(p):
    print("ERR: main.py yok:", p); sys.exit(2)
spec = importlib.util.spec_from_file_location("main", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
if not getattr(m, "app", None):
    print("ERR: main.app yok"); sys.exit(3)
print("OK: import via path; title=", getattr(m, "APP_TITLE", None))
sys.exit(0)
