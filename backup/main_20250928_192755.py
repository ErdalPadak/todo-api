logger = logging.getLogger(__name__)
import logging
from __future__ import annotations
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional, List
import sqlite3, os, datetime as dt

APP_TITLE = "Todo API"
DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")

app = FastAPI(
    title="Todo API",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)
logger = logging.getLogger(__name__)


def _conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def _ensure_schema():
    con = _conn(); c = con.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            notes TEXT DEFAULT '',
            tags  TEXT DEFAULT '',
            done  INTEGER DEFAULT 0,
            due   TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    con.commit(); con.close()

_ensure_schema()

def _tags_to_str(tags: List[str] | None) -> str:
    if not tags: return ""
    # normalize: trim, drop empties, dedup keep order
    seen, out = set(), []
    for t in tags:
        t = (t or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    return " ".join(out)

def _str_to_tags(s: str | None) -> List[str]:
    s = (s or "").strip()
    return [t for t in s.split() if t]

def _row_to_task(r: sqlite3.Row):
    return {
        "id": r["id"],
        "title": r["title"],
        "notes": r["notes"],
        "tags": _str_to_tags(r["tags"]),
        "done": bool(r["done"]),
        "due": r["due"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }

class TaskCreate(BaseModel):
    title: str
    notes: str = ""
    tags: List[str] = []
    due: Optional[str] = None  # ISO-8601 string

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str):
        if not v or not v.strip():
            raise ValueError("title required")
        return v.strip()

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    done: Optional[bool] = None
    due: Optional[str] = None  # ISO-8601 string

class TaskOut(BaseModel):
    id: int
    title: str
    notes: str
    tags: List[str]
    done: bool
    due: Optional[str]
    created_at: str
    updated_at: str

@app.get("/where")
def where():
    return {"__file__": __file__, "cwd": os.getcwd()}

@app.get("/routes")
def routes():
    return sorted([r.path for r in app.routes])

@app.post("/tasks", response_model=TaskOut)
def create_task(task: TaskCreate):
    tags_str = _tags_to_str(task.tags)
    con = _conn(); c = con.cursor()
    c.execute("""
        INSERT INTO tasks(title, notes, tags, done, due, created_at, updated_at)
        VALUES(?,?,?,?,?, datetime('now'), datetime('now'))
    """, (task.title.strip(), task.notes or "", tags_str, 0, task.due))
    tid = c.lastrowid
    con.commit()
    r = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    con.close()
    return _row_to_task(r)

@app.get("/tasks", response_model=List[TaskOut])
def list_tasks(
    q: Optional[str] = None,
    done: Optional[bool] = None,
    tag: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    clauses, args = [], []
    if q:
        clauses.append("(title LIKE ? OR notes LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like])
    if done is not None:
        clauses.append("done = ?")
        args.append(1 if done else 0)
    if tag:
        # tags stored as space-separated; match token boundary
        clauses.append("((' ' || tags || ' ') LIKE ?)")
        args.append(f"% {tag} %")
    # due filters
    def _valid_iso(s: str) -> bool:
        try:
            dt.datetime.fromisoformat(s)
            return True
        except Exception:
            return False
    if due_before:
        if not _valid_iso(due_before): raise HTTPException(422, detail="invalid due_before")
        clauses.append("(due IS NOT NULL AND due < ?)")
        args.append(due_before)
    if due_after:
        if not _valid_iso(due_after): raise HTTPException(422, detail="invalid due_after")
        clauses.append("(due IS NOT NULL AND due > ?)")
        args.append(due_after)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM tasks {where} ORDER BY id DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])

    con = _conn(); c = con.cursor()
    rows = c.execute(sql, tuple(args)).fetchall()
    con.close()

    items = []
    skipped_ids = []
    for row in rows:
        try:
            items.append(_row_to_task(row))
        except Exception as exc:
            task_id = None
            if isinstance(row, sqlite3.Row):
                try:
                    task_id = row["id"]
                except Exception:
                    pass
            skipped_ids.append(task_id)
            logger.warning("list_tasks: skipping task id=%s due to invalid data: %s", task_id, exc)
    if skipped_ids:
        logger.warning("list_tasks: skipped %d task(s) due to invalid data. ids=%s", len(skipped_ids), skipped_ids)
    return items


@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int):
    con = _conn(); c = con.cursor()
    r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    if not r: raise HTTPException(404, "not found")
    return _row_to_task(r)

@app.patch("/tasks/{task_id}")
def patch_task(task_id: int, patch: TaskUpdate):
    con = _conn(); c = con.cursor()
    r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not r:
        con.close(); raise HTTPException(404, "not found")

    title = patch.title if patch.title is not None else r["title"]
    notes = patch.notes if patch.notes is not None else r["notes"]
    tags_str = _tags_to_str(patch.tags) if patch.tags is not None else r["tags"]
    done = (1 if patch.done else 0) if patch.done is not None else r["done"]
    due = patch.due if patch.due is not None else r["due"]

    c.execute("""
        UPDATE tasks SET title=?, notes=?, tags=?, done=?, due=?, updated_at=datetime('now')
        WHERE id=?
    """, (title, notes, tags_str, done, due, task_id))
    con.commit()
    con.close()
    return {"ok": True}

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    con = _conn(); c = con.cursor()
    c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    con.commit(); con.close()
    return {"ok": True}

@app.get("/metrics")
def metrics():
    con = _conn(); c = con.cursor()
    total = c.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]
    done = c.execute("SELECT COUNT(*) AS n FROM tasks WHERE done=1").fetchone()["n"]
    open_ = total - done
    now_iso = dt.datetime.now().isoformat()
    overdue = c.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE done=0 AND due IS NOT NULL AND due < ?",
        (now_iso,)
    ).fetchone()["n"]
    con.close()
    return {"count": total, "done": done, "open": open_, "overdue": overdue}
# --- MAIQ PATCH START: health+where+routes+dbinit ---
try:
    from pathlib import Path
    import os, sqlite3, json
    APP_DIR = Path(__file__).resolve().parent
    DB_PATH = APP_DIR / "todo.db"

    def __maiq_init_db():
        con = sqlite3.connect(DB_PATH)
        c = con.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          description TEXT DEFAULT '',
          done INTEGER DEFAULT 0,
          tags TEXT DEFAULT '[]',
          due TEXT,
          created_at TEXT DEFAULT (datetime('now'))
        )""")
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "completed" in cols and "done" in cols:
            c.execute("UPDATE tasks SET done=COALESCE(done,0) OR COALESCE(completed,0)")
        con.commit(); con.close()

    if 'app' in globals():
        @app.on_event("startup")
        def __maiq_startup():
            __maiq_init_db()

        @app.get("/health")
        def __maiq_health():
            return {"status": "healthy"}

        @app.get("/where")
        def __maiq_where():
            return {"__file__": str(Path(__file__).resolve()), "cwd": os.getcwd()}

        @app.get("/routes")
        def __maiq_routes():
            return [r.path for r in app.router.routes]
except Exception as __maiq_e:
    # non-fatal
    pass
# --- MAIQ PATCH END ---

# === BEGIN: notes/description patch (safe add) ===
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException
import sqlite3, json, os

class TaskPartialUpdate(BaseModel):
    done: Optional[bool] = None
    notes: Optional[str] = None
    description: Optional[str] = None

def _db_path():
    here = os.path.dirname(__file__)
    for cand in ("todo.db", os.path.join("data","todo.db")):
        p = os.path.join(here, cand)
        if os.path.exists(p):
            return p
    return os.path.join(here, "todo.db")

@app.patch("/tasks/{task_id}/fields")
def patch_task_fields(task_id: int, body: TaskPartialUpdate):
    db = _db_path()
    con = sqlite3.connect(db)
    cur = con.cursor()

    set_parts = []
    params = []

    if body.done is not None:
        set_parts.append("done=?")
        params.append(1 if body.done else 0)

    note_text = body.notes or body.description
    if note_text is not None:
        set_parts.append("notes=?")
        params.append(note_text)

    if not set_parts:
        con.close()
        raise HTTPException(status_code=400, detail="No supported fields in body")

    params.append(task_id)
    cur.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id=?", params)
    con.commit()

    row = cur.execute("SELECT id,title,notes,tags,done,due,created_at,updated_at FROM tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    try:
        tags = json.loads(row[3]) if row[3] else []
    except Exception:
        tags = []

    return {
        "id": row[0],
        "title": row[1],
        "notes": row[2],
        "tags": tags,
        "done": bool(row[4]),
        "due": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }
# === END: notes/description patch ===
# === BEGIN: notes/description patch (safe add) ===
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException
import sqlite3, json, os

class TaskPartialUpdate(BaseModel):
    done: Optional[bool] = None
    notes: Optional[str] = None
    description: Optional[str] = None

def _db_path():
    here = os.path.dirname(__file__)
    for cand in ("todo.db", os.path.join("data","todo.db")):
        p = os.path.join(here, cand)
        if os.path.exists(p):
            return p
    return os.path.join(here, "todo.db")

@app.patch("/tasks/{task_id}/fields")
def patch_task_fields(task_id: int, body: TaskPartialUpdate):
    db = _db_path()
    con = sqlite3.connect(db)
    cur = con.cursor()

    set_parts = []
    params = []

    if body.done is not None:
        set_parts.append("done=?")
        params.append(1 if body.done else 0)

    note_text = body.notes or body.description
    if note_text is not None:
        set_parts.append("notes=?")
        params.append(note_text)

    if not set_parts:
        con.close()
        raise HTTPException(status_code=400, detail="No supported fields in body")

    params.append(task_id)
    cur.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id=?", params)
    con.commit()

    row = cur.execute("SELECT id,title,notes,tags,done,due,created_at,updated_at FROM tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    try:
        tags = json.loads(row[3]) if row[3] else []
    except Exception:
        tags = []

    return {
        "id": row[0],
        "title": row[1],
        "notes": row[2],
        "tags": tags,
        "done": bool(row[4]),
        "due": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }
# === END: notes/description patch ===

# --- UTF-8 charset fix (auto-injected) ---
try:
    import utf8_patch
    utf8_patch.apply(app)
except Exception:
    pass
# --- end utf-8 fix ---

# --- include fields_router (auto-injected) ---
try:
    from fields_router import router as _fields_router
    app.include_router(_fields_router)
except Exception:
    pass
# --- end include fields_router ---
# --- include fields_router (auto-injected, with reload) ---
try:
    import importlib, fields_router as _fields_router_mod
    _fields_router_mod = importlib.reload(_fields_router_mod)
    app.include_router(_fields_router_mod.router)
except Exception as _e:
    # silently ignore (startup should not crash)
    pass
# --- end include fields_router ---

# --- route fix: remove conflicting routes & include latest routers ---
try:
    import route_fix
    route_fix.apply(app)
except Exception as _e:
    pass
# --- end route fix ---
