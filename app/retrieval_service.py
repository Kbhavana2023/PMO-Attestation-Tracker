import json
import math
import sqlite3

from app.embedding_service import create_embeddings
from app.database import DB_PATH


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def search_chunks(project_id: str, query: str, top_k: int = 3) -> list[dict]:
    query_embedding = create_embeddings([query])[0]

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT dc.id, dc.document_id, dc.chunk_text, dc.embedding_json,
                   d.filename
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.project_id = ?
              AND dc.embedding_json IS NOT NULL
            """,
            (project_id,),
        ).fetchall()
    finally:
        connection.close()

    results = []

    for row in rows:
        stored_embedding = json.loads(row["embedding_json"])
        score = cosine_similarity(query_embedding, stored_embedding)

        results.append(
            {
                "chunk_id": row["id"],
                "document_id": row["document_id"],
                "filename": row["filename"],
                "text": row["chunk_text"],
                "similarity": round(score, 4),
            }
        )

    results.sort(key=lambda item: item["similarity"], reverse=True)
    return results[:top_k]