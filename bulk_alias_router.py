from fastapi import APIRouter, Body
from typing import List, Any, Dict
import sqlite3, os, json

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

def _tags_json(v):
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    s = str(v).strip()
    # zaten JSON ise bırak, değilse tek değerli liste yap
    if s.startswith('[') or s.startswith('{'):
        return s
    return json.dumps([s], ensure_ascii=False)

@router.patch("/bulk", tags=["tasks"])
def bulk_patch(items: List[Dict[str, Any]] = Body(...)):
    if not items:
        return {"ok": True, "updated": 0}
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        updated = 0
        for it in items:
            tid = int(it.get("id"))
            # done alanı
            if "done" in it:
                cur.execute(
                    "UPDATE tasks SET done=?, updated_at=strftime('%Y-%m-%d %H:%M:%S','now') WHERE id=?",
                    (1 if it["done"] else 0, tid)
                )
                updated += cur.rowcount
            # diğer alanlar
            fields = {}
            for k in ("notes","description","due"):
                if it.get(k) is not None:
                    fields[k] = str(it[k])
            if "tags" in it and it["tags"] is not None:
                fields["tags"] = _tags_json(it["tags"])
            if fields:
                sets = ", ".join(f"{k}=?" for k in fields.keys())
                vals = list(fields.values()) + [tid]
                cur.execute(
                    f"UPDATE tasks SET {sets}, updated_at=strftime('%Y-%m-%d %H:%M:%S','now') WHERE id=?",
                    vals
                )
                updated += cur.rowcount
        con.commit()
        return {"ok": True, "updated": updated}
    finally:
        con.close()
