import sqlite3, datetime as dt, json

DB = r"C:\maiq_demo\apps\todo_api\todo.db"
con = sqlite3.connect(DB)
cur = con.cursor()

rows = cur.execute("SELECT id, due FROM tasks").fetchall()

def try_parse_any(s):
    s = s.strip()
    fmts = ("%Y-%m-%d","%Y-%m-%d %H:%M","%Y/%m/%d","%d.%m.%Y","%d.%m.%Y %H:%M")
    for f in fmts:
        try:
            d = dt.datetime.strptime(s, f)
            return d.strftime("%Y-%m-%d %H:%M") if " " in f else d.strftime("%Y-%m-%d")
        except:
            pass
    try:
        dt.datetime.fromisoformat(s)  # ISO ise bırak
        return s
    except:
        return None

fixed = {"nullified":0, "normalized":0}
for id_, due in rows:
    if due is None:
        continue
    s = str(due).strip()
    if s == "":
        cur.execute("UPDATE tasks SET due=NULL WHERE id=?", (id_,)); fixed["nullified"] += 1; continue
    low = s.lower()
    if low in ("yes","y","1","true","t","on","no","n","0","false","f","off"):
        cur.execute("UPDATE tasks SET due=NULL WHERE id=?", (id_,)); fixed["nullified"] += 1; continue
    normalized = try_parse_any(s)
    if normalized is None:
        cur.execute("UPDATE tasks SET due=NULL WHERE id=?", (id_,)); fixed["nullified"] += 1
    elif normalized != s:
        cur.execute("UPDATE tasks SET due=? WHERE id=?", (normalized, id_)); fixed["normalized"] += 1

con.commit()
con.execute("VACUUM")
con.execute("ANALYZE")
con.close()
print(json.dumps({"ok": True, "fixed": fixed}))
