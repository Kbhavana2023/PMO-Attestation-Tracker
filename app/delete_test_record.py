from app.database import get_connection

connection = get_connection()
cursor = connection.cursor()

cursor.execute("""
    DELETE FROM projects
    WHERE project_id = 'string'
    AND project_name = 'string'
""")

connection.commit()

print("Deleted records:", cursor.rowcount)

connection.close()