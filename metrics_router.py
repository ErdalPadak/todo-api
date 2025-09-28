from fastapi import APIRouter, Response
import sqlite3, os, time, json

DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")
router = APIRouter()

def _has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def _counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) FROM tasks")
    row = cur.fetchone() or (0,0)
    total = int(row[0] or 0); done = int(row[1] or 0)
    open_ = total - done; ratio = (done/total) if total else 0.0
    return total, done, open_, ratio

def _recent_done_24h(conn):
    col = "updated_at" if _has_column(conn, "tasks", "updated_at") else "created_at"
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM tasks WHERE done=1 AND {col} >= datetime('now','-1 day')")
        return int(cur.fetchone()[0] or 0)
    except Exception:
        return 0

def _tags_counts(conn, only_open=False):
    if not _has_column(conn, "tasks", "tags"): return {}
    sql = "SELECT tags FROM tasks"
    if only_open: sql += " WHERE done=0"
    cur = conn.execute(sql)
    agg = {}
    for (t,) in cur.fetchall():
        if not t: continue
        try: obj = json.loads(t)
        except Exception: continue
        vals=[]
        if isinstance(obj, list): vals = [str(x) for x in obj]
        elif isinstance(obj, dict):
            for k,v in obj.items():
                vals.append(str(k)); vals.append(f"{k}:{v}")
        else: vals=[str(obj)]
        for tag in vals:
            tag = tag.strip()
            if not tag: continue
            agg[tag] = agg.get(tag,0)+1
    return agg

@router.get("/metrics")
def metrics():
    conn = sqlite3.connect(DB_PATH)
    try:
        total, done, open_, ratio = _counts(conn)
        recent24 = _recent_done_24h(conn)
        by_tag_all  = _tags_counts(conn, only_open=False)
        by_tag_open = _tags_counts(conn, only_open=True)

        now = int(time.time())
        def esc(s:str)->str: return s.replace("\\", "\\\\").replace('"','\\"')

        lines=[]
        lines.append("# HELP todo_tasks_total_current Current number of tasks.")
        lines.append("# TYPE todo_tasks_total_current gauge")
        lines.append(f"todo_tasks_total_current {total} {now}")
        lines.append("# HELP todo_tasks_done_current Current number of done tasks.")
        lines.append("# TYPE todo_tasks_done_current gauge")
        lines.append(f"todo_tasks_done_current {done} {now}")
        lines.append("# HELP todo_tasks_open_current Current number of open tasks.")
        lines.append("# TYPE todo_tasks_open_current gauge")
        lines.append(f"todo_tasks_open_current {open_} {now}")
        lines.append("# HELP todo_tasks_done_ratio Ratio of done to total tasks.")
        lines.append("# TYPE todo_tasks_done_ratio gauge")
        lines.append(f"todo_tasks_done_ratio {ratio:.6f} {now}")

        lines.append("# HELP todo_tasks_recent_done_24h Count of tasks marked done in the last 24 hours.")
        lines.append("# TYPE todo_tasks_recent_done_24h gauge")
        lines.append(f"todo_tasks_recent_done_24h {recent24} {now}")

        lines.append("# HELP todo_tasks_by_tag_current Current number of tasks per tag.")
        lines.append("# TYPE todo_tasks_by_tag_current gauge")
        for tag in sorted(by_tag_all):
            lines.append(f'todo_tasks_by_tag_current{{tag="{esc(tag)}"}} {by_tag_all[tag]} {now}')

        lines.append("# HELP todo_tasks_open_by_tag_current Current number of OPEN tasks per tag.")
        lines.append("# TYPE todo_tasks_open_by_tag_current gauge")
        for tag in sorted(by_tag_open):
            lines.append(f'todo_tasks_open_by_tag_current{{tag="{esc(tag)}"}} {by_tag_open[tag]} {now}')

        body = "\n".join(lines) + "\n"
        return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
    finally:
        conn.close()
