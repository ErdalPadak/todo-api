import sqlite3, os
DB=r"C:\maiq_demo\apps\todo_api\todo.db"
con=sqlite3.connect(DB)
cur=con.cursor()
cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
cur.execute("VACUUM")
cur.execute("REINDEX")
cur.execute("ANALYZE")
con.commit(); con.close()
print("ok")
