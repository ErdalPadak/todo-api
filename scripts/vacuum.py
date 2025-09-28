import sqlite3
con=sqlite3.connect(r"C:\maiq_demo\apps\todo_api\todo.db")
con.execute("VACUUM"); con.execute("ANALYZE"); con.close()
