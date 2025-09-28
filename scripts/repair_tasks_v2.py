import sqlite3, json, time
from datetime import datetime

DB = r"C:\maiq_demo\apps\todo_api\todo.db"

def utf8_clean(s, fallback):
    if s is None or s == "": return fallback
    try:
        (s if isinstance(s,str) else s.decode("utf-8","strict")).encode("utf-8","strict")
        return s if isinstance(s,str) else s.decode("utf-8","replace")
    except:
        return (s if isinstance(s,str) else s.decode("utf-8","replace"))

def main(apply=False):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    types = {r[1].lower(): (r[2] or "").upper() for r in cur.execute("PRAGMA table_info(tasks)")}
    created_kind = types.get("created_at","")
    rows = list(cur.execute("SELECT id,title,notes,done,created_at FROM tasks ORDER BY id ASC"))
    changed=[]
    for r in rows:
        rid=r["id"]; ch={}
        title = utf8_clean(r["title"], f"untitled-{rid}")
        if title != (r["title"] or ""): ch["title"]=title
        notes = utf8_clean(r["notes"] or "", "")
        if notes != (r["notes"] or ""): ch["notes"]=notes
        rawd = r["done"]; sval = str(rawd).strip().lower()
        done = 1 if sval in ("1","true","t","yes","y","on") or rawd is True else 0
        if sval not in ("0","1") and rawd not in (0,1,True,False): ch["done"]=done
        ca = r["created_at"]
        if ca is None or (isinstance(ca,str) and ca.strip()==""):
            ch["created_at"] = int(time.time()) if ("INT" in created_kind or "NUM" in created_kind) else \
                               datetime.now().isoformat(timespec="seconds")
        if ch:
            changed.append({"id":rid,"changes":ch})
            if apply:
                sets = ", ".join(f"{k}=?" for k in ch.keys())
                cur.execute(f"UPDATE tasks SET {sets} WHERE id=?", list(ch.values())+[rid])
    if apply: con.commit()
    for item in changed: print(json.dumps(item, ensure_ascii=False))
    print(json.dumps({"summary":{"affected":len(changed),"applied":apply}}, ensure_ascii=False))

if __name__=="__main__":
    import sys
    main(apply=("--apply" in sys.argv or "-a" in sys.argv))
