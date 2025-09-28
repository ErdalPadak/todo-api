import sqlite3, sys, json, datetime
DB = r"C:\maiq_demo\apps\todo_api\todo.db"

def to_iso(v):
    if v is None: return None
    if isinstance(v, (int, float)):
        return datetime.datetime.fromtimestamp(v).isoformat(timespec="seconds")
    if isinstance(v, (bytes, bytearray)):
        try: v = v.decode("utf-8", "replace")
        except: v = v.decode("latin-1", "replace")
    s = str(v).strip()
    # yaygın formatlar
    for f in ("%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S","%Y/%m/%d %H:%M:%S"):
        try: return datetime.datetime.strptime(s, f).isoformat(timespec="seconds")
        except: pass
    try:
        return datetime.datetime.fromisoformat(s.replace("Z","")).isoformat(timespec="seconds")
    except:
        return None

def clean_text(x):
    if x is None: return ""
    if isinstance(x, (bytes, bytearray)):
        x = x.decode("utf-8","replace")
    else:
        x = str(x)
    x = x.replace("\x00","")
    # surrogate aralığını temizle
    x = "".join(ch if not ("\ud800" <= ch <= "\udfff") else "?" for ch in x)
    # encode edilebilir mi?
    x.encode("utf-8","strict")
    return x

def to_bool01(x):
    if isinstance(x, (int, bool)): return int(bool(x))
    if isinstance(x, (bytes, bytearray)): x = x.decode("utf-8","ignore")
    s = str(x).strip().lower()
    if s in ("1","true","t","yes","y","on"): return 1
    if s in ("0","false","f","no","n","off"): return 0
    return 0

def main(apply=False):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    bad = []
    rows = list(cur.execute("SELECT id, title, done, created_at, notes FROM tasks ORDER BY id ASC"))
    for row in rows:
        rid = row["id"]
        issues = []
        title = clean_text(row["title"]) if row["title"] else f"untitled-{rid}"
        try:
            title.encode("utf-8")
        except Exception as e:
            issues.append(f"title-utf8:{e}")
            title = title.encode("utf-8","replace").decode("utf-8")
        notes = clean_text(row["notes"])
        created = to_iso(row["created_at"])
        if created is None:
            issues.append("created_at-invalid")
            created = datetime.datetime.now().isoformat(timespec="seconds")
        done = to_bool01(row["done"])

        changes = {}
        if title != (row["title"] or ""): changes["title"] = title
        if notes != (row["notes"] or ""): changes["notes"] = notes
        # created_at'ı metin olarak normalize et
        raw_created = row["created_at"]
        raw_created_str = None if raw_created is None else str(raw_created)
        if created != raw_created_str: changes["created_at"] = created
        # done'ı 0/1'e indir
        raw_done01 = 1 if row["done"] in (1, True, "1", "true", "True") else 0
        if done != raw_done01: changes["done"] = done

        if issues or changes:
            bad.append((rid, issues, changes))
            if apply and changes:
                sets = ", ".join(f"{k} = ?" for k in changes.keys())
                params = list(changes.values()) + [rid]
                cur.execute(f"UPDATE tasks SET {sets} WHERE id = ?", params)

    if apply:
        con.commit()

    total = cur.execute("SELECT COUNT(1) FROM tasks").fetchone()[0]
    for rid, issues, changes in bad:
        print(json.dumps({"id": rid, "issues": issues, "changes": changes}, ensure_ascii=False))
    print(json.dumps({"summary": {"total_rows": total, "affected": len(bad), "applied": apply}}, ensure_ascii=False))
    con.close()

if __name__ == "__main__":
    main(apply=("--apply" in sys.argv or "-a" in sys.argv))
