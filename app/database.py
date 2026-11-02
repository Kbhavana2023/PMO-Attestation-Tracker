import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent.parent / "pmo_database.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables():
    connection = get_connection()
    cursor = connection.cursor()

    # Projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT UNIQUE NOT NULL,
            project_name TEXT NOT NULL,
            description TEXT,
            department TEXT,
            status TEXT DEFAULT 'Active'
        )
    """)

    # Uploaded documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Text chunks and their embeddings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(project_id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)

    # Add embedding_json to an existing database without deleting its data
    columns = {
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(document_chunks)"
        ).fetchall()
    }

    if "embedding_json" not in columns:
        cursor.execute(
            "ALTER TABLE document_chunks ADD COLUMN embedding_json TEXT"
        )

    # Attestation review records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attestations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            reviewer_name TEXT NOT NULL,
            decision TEXT NOT NULL
                CHECK (decision IN ('Approved', 'Rejected')),
            comments TEXT DEFAULT '',
            attested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)

    connection.commit()
    connection.close()