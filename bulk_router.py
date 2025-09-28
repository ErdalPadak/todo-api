from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, List, Optional
import sqlite3, os, json

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

class BulkItem(BaseModel):
    id: int
    done: Optional[bool] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[Any] = None
    due: Optional[str] = None

def _has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

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

@router.patch("/tasks/bulk", tags=["tasks"])
def bulk_patch(items: List[BulkItem]):
    if not items:
        raise HTTPException(status_code=400, detail="Empty list")
    conn = sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row
    try:
        # columns guard
        cur = conn.cursor()
        if not _has_column(conn, "tasks", "description"):
            cur.execute("ALTER TABLE tasks ADD COLUMN description TEXT")
        if not _has_column(conn, "tasks", "tags"):
            cur.execute("ALTER TABLE tasks ADD COLUMN tags TEXT")
        conn.commit()

        updated = 0
        for it in items:
            cur.execute("SELECT id FROM tasks WHERE id=?", (it.id,))
            if not cur.fetchone():
                continue
            updates, params = [], []
            if it.done is not None:
                updates.append("done=?"); params.append(1 if it.done else 0)
            if it.notes is not None:
                updates.append("notes=?"); params.append(it.notes)
            if it.description is not None:
                updates.append("description=?"); params.append(it.description)
            if it.tags is not None:
                j = _tags_to_json_text(it.tags)
                if j is not None:
                    updates.append("tags=?"); params.append(j)
            if it.due is not None:
                updates.append("due=?"); params.append(it.due)

            if not updates:
                continue
            if _has_column(conn, "tasks", "updated_at"):
                updates.append("updated_at=CURRENT_TIMESTAMP")
            sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id=?"
            params.append(it.id)
            cur.execute(sql, params)
            updated += cur.rowcount

        conn.commit()
        return {"ok": True, "updated": int(updated)}
    finally:
        conn.close()
