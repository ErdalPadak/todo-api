from fastapi import APIRouter, Response
import sqlite3, os, json, traceback
import fts_util

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

@router.post("/admin/fts/reindex")
def fts_reindex():
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            if not fts_util.has_fts5(conn):
                return {"ok": False, "reason": "fts5_unavailable"}
            ok = fts_util.reindex(conn)
            return {"ok": bool(ok)}
        finally:
            conn.close()
    except Exception as e:
        return Response(content=json.dumps({"ok": False, "error": str(e)}),
                        media_type="application/json; charset=utf-8", status_code=200)
