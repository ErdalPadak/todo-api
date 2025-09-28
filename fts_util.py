import sqlite3, os
DB_PATH = os.path.join(os.path.dirname(__file__), "todo.db")

def _has_column(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        cur = conn.execute("PRAGMA compile_options")
        opts = {r[0] for r in cur.fetchall()}
        if any("FTS5" in o for o in opts):
            return True
    except Exception:
        pass
    try:
        conn.execute("DROP TABLE IF EXISTS temp.__fts_probe")
        conn.execute("CREATE VIRTUAL TABLE temp.__fts_probe USING fts5(x)")
        conn.execute("DROP TABLE temp.__fts_probe")
        return True
    except Exception:
        return False

def ensure_fts(conn: sqlite3.Connection) -> bool:
    if not has_fts5(conn):
        return False
    if not _has_column(conn, "tasks", "description"):
        conn.execute("ALTER TABLE tasks ADD COLUMN description TEXT")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts
        USING fts5(title, notes, description, content='tasks', content_rowid='id',
                   tokenize='unicode61 remove_diacritics 2');
    """)
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS tasks_ai AFTER INSERT ON tasks BEGIN
            INSERT INTO tasks_fts(rowid, title, notes, description)
            VALUES (new.id, new.title, new.notes, new.description);
        END;
        CREATE TRIGGER IF NOT EXISTS tasks_ad AFTER DELETE ON tasks BEGIN
            INSERT INTO tasks_fts(tasks_fts, rowid, title, notes, description)
            VALUES('delete', old.id, old.title, old.notes, old.description);
        END;
        CREATE TRIGGER IF NOT EXISTS tasks_au AFTER UPDATE ON tasks BEGIN
            INSERT INTO tasks_fts(tasks_fts, rowid, title, notes, description)
            VALUES('delete', old.id, old.title, old.notes, old.description);
            INSERT INTO tasks_fts(rowid, title, notes, description)
            VALUES (new.id, new.title, new.notes, new.description);
        END;
    """)
    conn.commit()
    return True

def reindex(conn: sqlite3.Connection) -> bool:
    if not ensure_fts(conn):  # FTS yoksa False dön
        return False
    conn.execute("DELETE FROM tasks_fts;")
    conn.execute("""
        INSERT INTO tasks_fts(rowid, title, notes, description)
        SELECT id, COALESCE(title,''), COALESCE(notes,''), COALESCE(description,'')
        FROM tasks;
    """)
    conn.commit()
    return True
