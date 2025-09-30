import sys, traceback, pathlib
p = pathlib.Path(r"C:\maiq_demo\apps\todo_api")
sys.path.insert(0, str(p))
try:
    import main
    print("OK: import main; title=", getattr(main,'APP_TITLE',None))
except Exception as e:
    print("IMPORT_FAIL:", e)
    traceback.print_exc()
    raise SystemExit(1)
