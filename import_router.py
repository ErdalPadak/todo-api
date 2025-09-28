from fastapi import APIRouter, Request, UploadFile, File, Query, HTTPException
import sqlite3, os, json, csv, io
from typing import Any, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

def _coerce_bool(v):
    if v is None: return None
    if isinstance(v, bool): return v
    s = str(v).strip().lower()
    if s in ("1","true","t","yes","y","on"): return True
    if s in ("0","false","f","no","n","off"): return False
    return None

def _tags_to_json_text(val: Any):
    if val is None: return None
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False, separators=(",",":"))
    if isinstance(val, str):
        s = val.strip()
        if not s: return None
        if s.startswith("{") or s.startswith("["):
            try: return json.dumps(json.loads(s), ensure_ascii=False, separators=(",",":"))
            except Exception: pass
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return json.dumps(parts, ensure_ascii=False, separators=(",",":"))
    try:
        return json.dumps(val, ensure_ascii=False, separators=(",",":"))
    except Exception:
        return None

def _load_json_text(text: str) -> List[dict]:
    text = (text or "").strip()
    if not text: return []
    try:
        obj = json.loads(text)
        if isinstance(obj, list): return obj
        return [obj]
    except json.JSONDecodeError:
        # NDJSON fallback
        rows = []
        for line in text.splitlines():
            line=line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

def _load_csv_text(text: str) -> List[dict]:
    buf = io.StringIO(text)
    rdr = csv.DictReader(buf)
    rows = []
    for r in rdr:
        rows.append({k:(v if v != "" else None) for k,v in r.items()})
    return rows

def _apply_one(cur: sqlite3.Cursor, row: dict, mode: str) -> str:
    """
    mode: insert | update | replace | upsert
    returns: 'inserted' | 'updated' | 'replaced' | 'ignored'
    """
    rid   = row.get("id")
    title = row.get("title")
    notes = row.get("notes")
    desc  = row.get("description")
    tags  = _tags_to_json_text(row.get("tags"))
    doneB = _coerce_bool(row.get("done"))
    due   = row.get("due")
    ca    = row.get("created_at")
    ua    = row.get("updated_at")

    if not title and not rid:
        raise HTTPException(status_code=400, detail="Row missing 'title' (or an existing 'id')")

    # mevcut mu?
    exists = False
    if rid is not None:
        cur.execute("SELECT 1 FROM tasks WHERE id=?", (rid,))
        exists = cur.fetchone() is not None

    if mode == "insert":
        # sadece insert, çakışırsa ignore
        cur.execute("""
            INSERT OR IGNORE INTO tasks (id,title,notes,description,tags,done,due,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            rid, title, notes, desc, tags,
            (1 if doneB else 0) if doneB is not None else 0,
            due, ca, ua
        ))
        return 'inserted' if cur.rowcount else 'ignored'

    if mode == "replace":
        cur.execute("""
            INSERT OR REPLACE INTO tasks (id,title,notes,description,tags,done,due,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            rid, title, notes, desc, tags,
            (1 if doneB else 0) if doneB is not None else 0,
            due, ca, ua
        ))
        return 'replaced'

    if mode in ("update","upsert"):
        if not exists:
            if mode == "update":
                return 'ignored'
            # upsert -> yeni ekle (id yoksa autoinc)
            cur.execute("""
                INSERT INTO tasks (id,title,notes,description,tags,done,due,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                rid, title, notes, desc, tags,
                (1 if doneB else 0) if doneB is not None else 0,
                due, ca, ua
            ))
            return 'inserted'
        # exists -> update
        sets, params = [], []
        if title is not None: sets.append("title=?"); params.append(title)
        if notes is not None: sets.append("notes=?"); params.append(notes)
        if desc  is not None: sets.append("description=?"); params.append(desc)
        if tags  is not None: sets.append("tags=?"); params.append(tags)
        if doneB is not None: sets.append("done=?"); params.append(1 if doneB else 0)
        if due   is not None: sets.append("due=?"); params.append(due)
        # updated_at varsa güncelle
        sets.append("updated_at=CURRENT_TIMESTAMP")
        params.append(rid)
        cur.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", params)
        return 'updated' if cur.rowcount else 'ignored'

    raise HTTPException(status_code=400, detail=f"Unsupported mode: {mode}")

@router.post("/import", tags=["tasks"])
async def import_tasks(request: Request,
                       mode: str = Query("upsert", pattern="^(insert|update|replace|upsert)$")):
    ct = (request.headers.get("content-type") or "").lower()
    records: List[dict] = []
    text: Optional[str] = None

    if "application/json" in ct or "text/json" in ct:
        text = (await request.body()).decode("utf-8-sig", "ignore")
        records = _load_json_text(text)
    elif "text/csv" in ct:
        text = (await request.body()).decode("utf-8-sig", "ignore")
        records = _load_csv_text(text)
    elif "multipart/form-data" in ct:
        form = await request.form()
        f: UploadFile = form.get("file")  # name=file
        if not f:
            raise HTTPException(status_code=400, detail="No file part 'file'")
        content = (await f.read()).decode("utf-8-sig", "ignore")
        if (f.filename or "").lower().endswith(".csv"):
            records = _load_csv_text(content)
        else:
            records = _load_json_text(content)
    else:
        # ham gövdeyi JSON dene
        text = (await request.body()).decode("utf-8-sig", "ignore")
        records = _load_json_text(text)

    if not isinstance(records, list) or not records:
        return {"ok": True, "processed": 0, "inserted": 0, "updated": 0, "replaced": 0, "ignored": 0}

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # tablo garanti
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY,
          title TEXT NOT NULL,
          notes TEXT,
          description TEXT,
          tags TEXT,
          done INTEGER DEFAULT 0,
          due TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        inserted=updated=replaced=ignored=0
        for r in records:
            res = _apply_one(cur, r, mode)
            if   res == 'inserted':  inserted += 1
            elif res == 'updated':   updated  += 1
            elif res == 'replaced':  replaced += 1
            else:                    ignored  += 1
        conn.commit()
        return {"ok": True, "processed": len(records),
                "inserted": inserted, "updated": updated,
                "replaced": replaced, "ignored": ignored}
    finally:
        conn.close()
