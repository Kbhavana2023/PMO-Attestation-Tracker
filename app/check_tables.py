from app.database import get_connection

connection = get_connection()
tables = connection.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()

print([row["name"] for row in tables])
connection.close()