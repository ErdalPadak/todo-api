from fastapi import APIRouter, Response, Query
import sqlite3, os, json, csv, io
from typing import Optional, List
import fts_util

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

_MAP = str.maketrans({
    "ı":"i","İ":"I","ğ":"g","Ğ":"G","ş":"s","Ş":"S","ö":"o","Ö":"O","ü":"u","Ü":"U","ç":"c","Ç":"C",
    "â":"a","Â":"A","ä":"a","Ä":"A","à":"a","À":"A","á":"a","Á":"A","ã":"a","Ã":"A",
    "é":"e","É":"E","è":"e","È":"E","ê":"e","Ê":"E","ë":"e","Ë":"E",
    "í":"i","Í":"I","ì":"i","Ì":"I","î":"i","Î":"I","ï":"i","Ï":"I",
    "ó":"o","Ó":"O","ò":"o","Ò":"O","ô":"o","Ô":"O","õ":"o","Õ":"O","ö":"o","Ö":"O",
    "ú":"u","Ú":"U","ù":"u","Ù":"U","û":"u","Û":"U","ü":"u","Ü":"U",
    "ñ":"n","Ñ":"N","ÿ":"y","Ý":"Y"
})
def _unaccent(s: str) -> str:
    if s is None: return ""
    return s.translate(_MAP)

def _row_to_task(row: sqlite3.Row) -> dict:
    d = dict(row); d["done"] = bool(d.get("done",0))
    t = d.get("tags")
    if t:
        try: d["tags"] = json.loads(t) if isinstance(t, str) else t
        except Exception: d["tags"] = {}
    else:
        d["tags"] = {}
    return d

@router.get("/export")
def export(
    format: str = Query("json", pattern="^(json|csv)$"),
    done: Optional[bool] = None,
    q: Optional[str] = None,
    tag: Optional[List[str]] = Query(None),
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    sort: Optional[str] = Query("id"),
    order: Optional[str] = Query("desc")
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

        allowed = {"id","title","due","created_at","updated_at"}
        sort_col = sort if sort in allowed else "id"
        order_dir = "ASC" if (str(order).lower() == "asc") else "DESC"

        use_fts = False
        if q:
            try:
                use_fts = bool(fts_util.ensure_fts(conn))
            except Exception:
                use_fts = False

        if q and use_fts:
            def _fts_match_string(qs: str) -> str:
                if '"' in qs or "'" in qs: return qs
                parts = [p for p in qs.strip().split() if p]
                return " ".join(f"{p}*" for p in parts)
            ms = _fts_match_string(q)
            sql = "SELECT t.* FROM tasks t JOIN tasks_fts f ON f.rowid=t.id WHERE f.tasks_fts MATCH ?"
            p2  = [ms]
            if where: sql += " AND " + " AND ".join(where); p2 += params
            if sort_col == "due":
                sql += f" ORDER BY (t.due IS NULL OR t.due='') ASC, t.due {order_dir}"
            else:
                sql += f" ORDER BY t.{sort_col} {order_dir}"
            rows = [ _row_to_task(r) for r in conn.execute(sql, p2).fetchall() ]
        else:
            if q:
                conn.create_function("unaccent", 1, _unaccent)
                like = f"%{q}%"
                where.append("(unaccent(t.title) LIKE unaccent(?) OR unaccent(t.notes) LIKE unaccent(?) OR unaccent(t.description) LIKE unaccent(?))")
                params.extend([like, like, like])
            sql = "SELECT t.* FROM tasks t"
            if where: sql += " WHERE " + " AND ".join(where)
            if sort_col == "due":
                sql += f" ORDER BY (t.due IS NULL OR t.due='') ASC, t.due {order_dir}"
            else:
                sql += f" ORDER BY t.{sort_col} {order_dir}"

            rows = [ _row_to_task(r) for r in conn.execute(sql, params).fetchall() ]

        if tag:
            want = [t.strip() for t in tag if str(t).strip()]
            def has_all_tags(task):
                t = task.get("tags") or []
                if isinstance(t, dict):
                    vals = list(t.keys()) + list(map(str, t.values()))
                else:
                    vals = list(map(str, t))
                return all(x in vals for x in want)
            rows = [t for t in rows if has_all_tags(t)]

        if format == "json":
            body = json.dumps(rows, ensure_ascii=False, separators=(",",":"))
            return Response(content=body, media_type="application/json; charset=utf-8",
                            headers={"Content-Disposition":"attachment; filename=todos.json"})
        else:
            if rows:
                for r in rows:
                    t = r.get("tags") or []
                    r["tags"] = json.dumps(t, ensure_ascii=False, separators=(",",":"))
            buf = io.StringIO()
            cols = ["id","title","notes","description","done","due","created_at","updated_at","tags"]
            wr = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            for r in rows: wr.writerow(r)
            return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition":"attachment; filename=todos.csv"})
    finally:
        conn.close()
