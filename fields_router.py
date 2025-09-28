from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel
from typing import Optional, Any
import sqlite3, os, json

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

class FieldsPatch(BaseModel):
    notes: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[Any] = None   # list | dict | json-string | csv-string
    due: Optional[str] = None    # ISO-string (TEXT saklıyoruz)

def _has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def _ensure_columns(conn):
    cur = conn.cursor()
    if not _has_column(conn, "tasks", "description"):
        cur.execute("ALTER TABLE tasks ADD COLUMN description TEXT")
    if not _has_column(conn, "tasks", "tags"):
        cur.execute("ALTER TABLE tasks ADD COLUMN tags TEXT")
    # 'due' zaten var; yoksa eklemek için yorum satırını aç
    # if not _has_column(conn, "tasks", "due"):
    #     cur.execute("ALTER TABLE tasks ADD COLUMN due TEXT")
    conn.commit()

def _tags_to_json_text(val: Any):
    if val is None: return None
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False, separators=(",",":"))
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("{") or s.startswith("["):
            try: return json.dumps(json.loads(s), ensure_ascii=False, separators=(",",":"))
            except Exception: pass
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return json.dumps(parts, ensure_ascii=False, separators=(",",":"))
    try: return json.dumps(val, ensure_ascii=False, separators=(",",":"))
    except Exception: return None

def _row_to_task(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["done"] = bool(d.get("done", 0))
    t = d.get("tags")
    if isinstance(t, (bytes, bytearray)):
        try: t = t.decode("utf-8", "ignore")
        except Exception: t = None
    if isinstance(t, str) and t.strip():
        try: d["tags"] = json.loads(t)
        except Exception: d["tags"] = {}
    else:
        d["tags"] = {}
    return d

@router.patch("/tasks/{task_id}/fields", tags=["tasks"])
async def patch_task_fields(request: Request, task_id: int = Path(..., ge=1), body: FieldsPatch | None = None):
    # Model + ham JSON birlikte (hangisinde varsa onu al)
    try:
        raw = await request.json()
        if not isinstance(raw, dict): raw = {}
    except Exception:
        raw = {}

    def pick(key, model_val):
        if model_val is not None: return model_val
        return raw.get(key, None)

    notes       = pick("notes",       body.notes if body else None)
    description = pick("description", body.description if body else None)
    tags_in     = pick("tags",        body.tags if body else None)
    due         = pick("due",         body.due if body else None)

    tags_txt = _tags_to_json_text(tags_in)

    if notes is None and description is None and tags_txt is None and due is None:
        raise HTTPException(status_code=400, detail="No supported fields in body")

    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        _ensure_columns(conn)
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        updates, params = [], []
        if notes is not None:       updates.append("notes=?");        params.append(notes)
        if description is not None: updates.append("description=?");  params.append(description)
        if tags_txt is not None:    updates.append("tags=?");         params.append(tags_txt)
        if due is not None:         updates.append("due=?");          params.append(due)

        if not updates:
            return {"ok": True, "task": _row_to_task(row)}
        if _has_column(conn, "tasks", "updated_at"):
            updates.append("updated_at=CURRENT_TIMESTAMP")

        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id=?"
        params.append(task_id)
        cur.execute(sql, params); conn.commit()

        cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        return {"ok": True, "task": _row_to_task(cur.fetchone())}
    finally:
        conn.close()
