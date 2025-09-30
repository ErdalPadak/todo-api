from __future__ import annotations



from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from typing import Optional, List
import logging
import sqlite3, os, datetime as dt
logger = logging.getLogger(__name__)

APP_TITLE = "Todo API"
DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")

app = FastAPI(
    title="Todo API",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


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
from fastapi import HTTPException, Request
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
from fastapi import HTTPException, Request
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

# --- /export (csv|jsonl) ---
from fastapi.responses import PlainTextResponse
import json, csv, io

def _plain_task(t):
    return {
        "id": t["id"],
        "title": t["title"],
        "notes": t["notes"],
        "tags": " ".join(t["tags"]) if isinstance(t["tags"], list) else (t["tags"] or ""),
        "done": bool(t["done"]),
        "due": t["due"],
        "created_at": t["created_at"],
        "updated_at": t["updated_at"],
    }

@app.get("/export", response_class=PlainTextResponse)
def export_tasks(
    format: str = Query("csv", pattern="^(csv|jsonl)$"),
    q: Optional[str] = None,
    done: Optional[bool] = None,
    tag: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    items = list_tasks(q=q, done=done, tag=tag,
                       due_before=due_before, due_after=due_after,
                       limit=limit, offset=offset)
    if format == "jsonl":
        return "\n".join(json.dumps(_plain_task(t), ensure_ascii=False) for t in items)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","title","notes","tags","done","due","created_at","updated_at"])
    for t in items:
        p = _plain_task(t)
        w.writerow([p["id"], p["title"], p["notes"], p["tags"], int(p["done"]), p["due"], p["created_at"], p["updated_at"]])
    return buf.getvalue()
from fastapi import Body, Request
from fastapi import Query as _Q  # mevcutla çakışmasın diye alias, Request

@app.post("/import")
async def import_tasks(format: str = Query("csv", pattern="^(csv|jsonl)$"), dry_run: bool = Query(True), request: Request = None):
    import csv, json
    from fastapi import Request
    body = (await request.body()).decode("utf-8","strict")

    if format == "csv":
        # Kat? kurallar: exact header, tam 5 s?tun, done sadece {1,0,true,false,yes,no,''}
        lines = [ln for ln in body.splitlines() if ln.strip() != ""]
        if not lines:
            return {"dry_run": dry_run, "will_insert": 0, "skipped": 0, "errors": [{"line": 1, "err": "empty"}]}
        reader = csv.reader(lines)
        header = next(reader, [])
        if [c.strip() for c in header] != ["title","notes","tags","done","due"]:
            return {"dry_run": dry_run, "will_insert": 0, "skipped": 0, "errors": [{"line": 1, "err": "bad header (expected: title,notes,tags,done,due)"}]}

        to_ins, errs, ln = [], [], 1
        for row in reader:
            ln += 1
            if len(row) != 5:
                errs.append({"line": ln, "err": "wrong column count"}); continue
            title, notes, tags_str, done_raw, due = [x.strip() for x in row]
            if not title:
                errs.append({"line": ln, "err": "missing title"}); continue
            m = str(done_raw).strip().lower()
            if m in ("1","true","yes","y"):
                done = 1
            elif m in ("0","false","no","n",""):
                done = 0
            else:
                errs.append({"line": ln, "err": "bad done"}); continue
            to_ins.append((title, notes, tags_str, done, due or None))

        if dry_run:
            return {"dry_run": True, "will_insert": len(to_ins), "skipped": len(errs), "errors": errs}
        con = _conn(); c = con.cursor()
        c.executemany("INSERT INTO tasks(title,notes,tags,done,due,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))", to_ins)
        con.commit(); con.close()
        return {"dry_run": False, "inserted": len(to_ins), "skipped": len(errs), "errors": errs}

    else:  # JSONL
        to_ins, errs = [], []
        for i, ln in enumerate(body.splitlines(), start=1):
            if not ln.strip(): continue
            try:
                obj = json.loads(ln)
            except Exception:
                errs.append({"line": i, "err": "bad json"}); continue
            title = (obj.get("title") or "").strip()
            if not title:
                errs.append({"line": i, "err": "missing title"}); continue
            notes = obj.get("notes") or ""
            tags  = obj.get("tags")  or ""
            tags_str = " ".join(str(t).strip() for t in tags) if isinstance(tags, list) else str(tags)
            m = str(obj.get("done","")).strip().lower()
            done = 1 if m in ("1","true","yes","y") else 0
            due  = obj.get("due") or None
            to_ins.append((title, notes, tags_str, done, due))

        if dry_run:
            return {"dry_run": True, "will_insert": len(to_ins), "skipped": len(errs), "errors": errs}
        con = _conn(); c = con.cursor()
        c.executemany("INSERT INTO tasks(title,notes,tags,done,due,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))", to_ins)
        con.commit(); con.close()
        return {"dry_run": False, "inserted": len(to_ins), "skipped": len(errs), "errors": errs}
# --- BATCH OPS (atomic transaction) ---
from typing import Dict
from pydantic import BaseModel

class BatchOp(BaseModel):
    op: str                 # "patch" | "delete"
    id: Optional[int] = None
    set: Optional[Dict] = None

class BatchRequest(BaseModel):
    ops: List[BatchOp]
    atomic: bool = True

@app.post("/batch")
def batch_ops(req: BatchRequest):
    con = _conn(); c = con.cursor()
    results = []; errors = []
    try:
        c.execute("BEGIN")
        for idx,op in enumerate(req.ops):
            try:
                if op.op == "patch":
                    if op.id is None or op.set is None:
                        raise ValueError("patch requires id and set")
                    r = c.execute("SELECT * FROM tasks WHERE id=?", (op.id,)).fetchone()
                    if not r:
                        raise ValueError("not found")

                    # mevcut değerler + gelen set
                    title = op.set.get("title", r["title"])
                    notes = op.set.get("notes", r["notes"])
                    tags_in = op.set.get("tags", None)
                    tags_str = _tags_to_str(tags_in) if tags_in is not None else r["tags"]

                    # done normalizasyonu (bool/str/int)
                    raw_done = op.set.get("done", r["done"])
                    s = (str(raw_done).strip().lower() if raw_done is not None else "")
                    if raw_done is True or s in ("1","true","t","yes","y","on"):
                        done = 1
                    elif raw_done is False or s in ("0","false","f","no","n","off"):
                        done = 0
                    else:
                        done = r["done"]

                    due = op.set.get("due", r["due"])

                    c.execute("""
                        UPDATE tasks
                        SET title=?, notes=?, tags=?, done=?, due=?, updated_at=datetime('now')
                        WHERE id=?""", (title, notes, tags_str, done, due, op.id))
                    results.append({"idx": idx, "op":"patch", "id": op.id, "ok": True})

                elif op.op == "delete":
                    if op.id is None:
                        raise ValueError("delete requires id")
                    c.execute("DELETE FROM tasks WHERE id=?", (op.id,))
                    results.append({"idx": idx, "op":"delete", "id": op.id, "ok": True})

                else:
                    raise ValueError("unsupported op")
            except Exception as e:
                errors.append({"idx": idx, "op": getattr(op, "op", None), "id": getattr(op, "id", None), "error": str(e)})
                if req.atomic:
                    raise

        if errors and req.atomic:
            con.rollback(); con.close()
            raise HTTPException(status_code=400, detail={"ok": False, "atomic": True, "errors": errors})

        con.commit(); con.close()
        return {"ok": True, "atomic": req.atomic, "results": results, "errors": errors}

    except HTTPException:
        raise
    except Exception as e:
        con.rollback(); con.close()
        raise HTTPException(status_code=500, detail=str(e))
# --- END BATCH OPS ---

# --- BATCH_HOTFIX START ---
# Mevcut /batch route'larını kaldır ve tek, transaction'lı bir sürüm kur.
from pydantic import BaseModel
from fastapi import Query
from starlette.responses import JSONResponse

# Eski /batch handler varsa kaldır
try:
    app.router.routes[:] = [
        r for r in app.router.routes
        if not (getattr(r, "path", None) == "/batch" and "POST" in getattr(r, "methods", []))
    ]
except Exception:
    pass

class BatchOp(BaseModel):
    op: str
    id: int | None = None
    set: dict | None = None

class BatchRequest(BaseModel):
    ops: list[BatchOp]

def __apply_op(cur, op: BatchOp):
    if op.op == "patch":
        if op.id is None or not op.set:
            raise ValueError("patch requires id and set")
        fields, vals = [], []
        for k, v in op.set.items():
            if k not in {"title","notes","tags","done","due"}:
                continue
            if k == "tags":
                if isinstance(v, list):
                    v = _tags_to_str(v)
                else:
                    v = str(v)
            if k == "done":
                sv = str(v).strip().lower()
                v = 1 if (sv in ("1","true","t","yes","y","on")) else 0
            fields.append(f"{k}=?"); vals.append(v)
        if not fields:
            raise ValueError("patch set has no valid fields")
        vals.append(op.id)
        cur.execute(f"UPDATE tasks SET {', '.join(fields)}, updated_at=datetime('now') WHERE id=?", vals)
        if cur.rowcount == 0:
            raise LookupError("not found")
        return {"op":"patch","id":op.id,"ok":True}

    elif op.op == "delete":
        if op.id is None:
            raise ValueError("delete requires id")
        cur.execute("DELETE FROM tasks WHERE id=?", (op.id,))
        if cur.rowcount == 0:
            raise LookupError("not found")
        return {"op":"delete","id":op.id,"ok":True}

    else:
        raise ValueError("unsupported op")

@app.post("/batch")
def __batch_endpoint(req: BatchRequest, atomic: bool = Query(False)):
    con = _conn(); cur = con.cursor()
    results, errors = [], []
    try:
        if atomic:
            cur.execute("BEGIN")
        for idx, op in enumerate(req.ops):
            try:
                r = __apply_op(cur, op)
                r["idx"] = idx
                results.append(r)
            except Exception as e:
                errors.append({"idx":idx, "op":getattr(op,"op",None), "id":getattr(op,"id",None), "error":str(e)})
                if atomic:
                    raise
        con.commit()
        ok = (len(errors) == 0)
        return {"ok": ok, "atomic": atomic, "results": results, "errors": errors}
    except Exception as e:
        if atomic:
            con.rollback()
        # atomic ise 400 + rolled_back bilgisi; değilse 200 ama ok=false
        if atomic:
            return JSONResponse({"ok": False, "atomic": True, "rolled_back": True,
                                 "results": results, "errors": errors or [{"error": str(e)}]}, status_code=400)
        else:
            return {"ok": False, "atomic": False, "results": results, "errors": errors or [{"error": str(e)}]}
    finally:
        con.close()
# --- BATCH_HOTFIX END ---
