from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import JSONResponse
import sqlite3, os, json
from typing import Optional, List

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

# Türkçe unaccent + casefold
_MAP = str.maketrans({
    "ı":"i","İ":"I","ğ":"g","Ğ":"G","ş":"s","Ş":"S","ö":"o","Ö":"O","ü":"u","Ü":"U","ç":"c","Ç":"C",
    "â":"a","Â":"A","ä":"a","Ä":"A","à":"a","À":"A","á":"a","Á":"A","ã":"a","Ã":"A",
    "é":"e","É":"E","è":"e","È":"E","ê":"e","Ê":"E","ë":"e","Ë":"E",
    "í":"i","Í":"I","ì":"i","Ì":"I","î":"i","Î":"I","ï":"i","Ï":"I",
    "ó":"o","Ó":"O","ò":"o","Ò":"O","ô":"o","Ô":"O","õ":"o","Õ":"O",
    "ú":"u","Ú":"U","ù":"u","Ù":"U","û":"u","Û":"U",
    "ñ":"n","Ñ":"N","ÿ":"y","Ý":"Y"
})
def _norm(s: Optional[str]) -> str:
    if not s: return ""
    return s.translate(_MAP).casefold()

def _to_str(v) -> str:
    return "" if v is None else str(v)

def _tags_to_list(t) -> list:
    if t is None: return []
    if isinstance(t, (bytes, bytearray)):
        try: t = t.decode("utf-8", "ignore")
        except Exception: return []
    if isinstance(t, str):
        ts = t.strip()
        if not ts: return []
        if ts.startswith("[") or ts.startswith("{"):
            try:
                obj = json.loads(ts)
                if isinstance(obj, list): return [ _to_str(x) for x in obj ]
                if isinstance(obj, dict):
                    out=[]; 
                    for k,v in obj.items():
                        out.append(f"{k}:{v}" if v is not None else _to_str(k))
                    return out
            except Exception: pass
        return [ s.strip() for s in ts.split(",") if s.strip() ]
    if isinstance(t, list): return [ _to_str(x) for x in t ]
    if isinstance(t, dict):
        out=[]
        for k,v in t.items():
            out.append(f"{k}:{v}" if v is not None else _to_str(k))
        return out
    return [ _to_str(t) ]

def _row_to_task(row: sqlite3.Row) -> dict:
    d = dict(row)
    return {
        "id": int(d.get("id")),
        "title": _to_str(d.get("title")),
        "notes": _to_str(d.get("notes")),
        "description": _to_str(d.get("description")),
        "tags": _tags_to_list(d.get("tags")),
        "done": bool(d.get("done", 0)),
        "due": _to_str(d.get("due")),
        "created_at": _to_str(d.get("created_at")),
        "updated_at": _to_str(d.get("updated_at")),
    }

@router.get("/tasks/{task_id}", tags=["tasks"])
def get_task(task_id: int = Path(..., ge=1)):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Task not found")
        return JSONResponse(_row_to_task(row), media_type="application/json; charset=utf-8")
    finally:
        conn.close()

@router.get("/tasks", tags=["tasks"])
def list_tasks(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    done: Optional[bool] = None,
    q: Optional[str] = Query(None, description="SAFE MODE: Python-side search (unaccent+casefold)"),
    tag: Optional[List[str]] = Query(None, description="Birden çok tag"),
    due_before: Optional[str] = Query(None, description="YYYY-MM-DD[ HH:MM]"),
    due_after: Optional[str]  = Query(None, description="YYYY-MM-DD[ HH:MM]"),
    sort: Optional[str] = Query("id", description="id|title|due|created_at|updated_at"),
    order: Optional[str] = Query("desc", description="asc|desc")
):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        where, params = [], []
        if done is not None:
            where.append("t.done=?"); params.append(1 if done else 0)
        if due_before:
            where.append("(t.due IS NOT NULL AND t.due <> '' AND t.due <= ?)"); params.append(due_before)
        if due_after:
            where.append("(t.due IS NOT NULL AND t.due <> '' AND t.due >= ?)"); params.append(due_after)

        sql = "SELECT t.* FROM tasks t"
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.id DESC"

        items = [ _row_to_task(r) for r in conn.execute(sql, params).fetchall() ]

        if q:
            nq = _norm(q)
            items = [t for t in items if (nq in _norm(t["title"]) or nq in _norm(t["notes"]) or nq in _norm(t["description"]))]

        if tag:
            want = [str(x).strip() for x in tag if str(x).strip()]
            def has_all(tsk):
                vals = [str(x) for x in (tsk.get("tags") or [])]
                return all(w in vals for w in want)
            items = [t for t in items if has_all(t)]

        sc = sort if sort in {"id","title","due","created_at","updated_at"} else "id"
        asc = (str(order).lower() == "asc")
        if sc == "due":
            items.sort(key=lambda r: (r["due"] == "", r["due"]), reverse=not asc)
        else:
            items.sort(key=lambda r: r.get(sc, ""), reverse=not asc)

        payload = items[offset:offset+limit]
        return JSONResponse(payload, media_type="application/json; charset=utf-8")
    finally:
        conn.close()
