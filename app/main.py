from pathlib import Path
from typing import Literal
import csv
import io
import json
import math
import os
import shutil

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import get_connection, create_tables
from app.document_reader import extract_text
from app.document_chunker import split_text
from app.embedding_service import create_embeddings

load_dotenv()

app = FastAPI(title="PMO Attestation Automation")

UPLOAD_DIR = Path("uploaded_documents")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def startup():
    create_tables()


class Project(BaseModel):
    project_id: str
    project_name: str
    description: str = ""
    department: str = ""
    status: str = "Active"


class SearchRequest(BaseModel):
    query: str
    top_k: int = 3


class AskRequest(BaseModel):
    question: str
    top_k: int = 3


class AttestationRequest(BaseModel):
    reviewer_name: str
    decision: Literal["Approved", "Rejected"]
    comments: str = ""


def row_to_dict(cursor, row):
    if row is None:
        return None

    if hasattr(row, "keys"):
        return dict(row)

    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def cosine_similarity(vector_a, vector_b):
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def retrieve_chunks(project_id, query, top_k):
    query_embedding = create_embeddings([query])[0]

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                dc.id AS chunk_id,
                dc.document_id,
                dc.chunk_text,
                dc.embedding_json,
                d.filename
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.project_id = ?
              AND dc.embedding_json IS NOT NULL
            """,
            (project_id,),
        ).fetchall()

    results = []

    for row in rows:
        stored_embedding = json.loads(row["embedding_json"])
        score = cosine_similarity(query_embedding, stored_embedding)

        results.append({
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "filename": row["filename"],
            "text": row["chunk_text"],
            "similarity": round(score, 4),
        })

    results.sort(key=lambda item: item["similarity"], reverse=True)
    return results[:top_k]


@app.get("/")
def home():
    return {
        "message": "Welcome to PMO Attestation Automation!",
        "status": "Application is running",
    }


# -------------------------
# Project endpoints
# -------------------------

@app.post("/projects")
def create_project(project: Project):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO projects
                (project_id, project_name, description, department, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project.project_id,
                project.project_name,
                project.description,
                project.department,
                project.status,
            ),
        )
        connection.commit()

        return {
            "message": "Project created successfully",
            "project_id": project.project_id,
        }

    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

    finally:
        connection.close()


@app.get("/projects")
def get_projects():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM projects")
    rows = cursor.fetchall()
    projects = [row_to_dict(cursor, row) for row in rows]
    connection.close()
    return projects


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT * FROM projects WHERE project_id = ?",
        (project_id,),
    )
    project = row_to_dict(cursor, cursor.fetchone())
    connection.close()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


@app.put("/projects/{project_id}")
def update_project(project_id: str, project: Project):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE projects
        SET project_name = ?, description = ?, department = ?, status = ?
        WHERE project_id = ?
        """,
        (
            project.project_name,
            project.description,
            project.department,
            project.status,
            project_id,
        ),
    )

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    if updated == 0:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"message": "Project updated successfully"}


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM projects WHERE project_id = ?",
        (project_id,),
    )
    connection.commit()
    deleted = cursor.rowcount
    connection.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"message": "Project deleted successfully"}


# -------------------------
# Document upload and list
# -------------------------

@app.post("/projects/{project_id}/documents")
def upload_document(project_id: str, file: UploadFile = File(...)):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT project_id FROM projects WHERE project_id = ?",
        (project_id,),
    )

    if cursor.fetchone() is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Project not found")

    safe_filename = Path(file.filename).name
    project_folder = UPLOAD_DIR / project_id
    project_folder.mkdir(parents=True, exist_ok=True)
    file_path = project_folder / safe_filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        cursor.execute(
            """
            INSERT INTO documents (project_id, filename, file_path)
            VALUES (?, ?, ?)
            """,
            (project_id, safe_filename, str(file_path)),
        )
        connection.commit()

        return {
            "message": "Document uploaded successfully",
            "document_id": cursor.lastrowid,
            "project_id": project_id,
            "filename": safe_filename,
        }

    finally:
        connection.close()
        file.file.close()


@app.get("/projects/{project_id}/documents")
def get_project_documents(project_id: str):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT *
        FROM documents
        WHERE project_id = ?
        ORDER BY id DESC
        """,
        (project_id,),
    )
    documents = [row_to_dict(cursor, row) for row in cursor.fetchall()]
    connection.close()
    return documents


# -------------------------
# Document text extraction
# -------------------------

@app.get("/projects/{project_id}/documents/{document_id}/text")
def read_document_text(project_id: str, document_id: int):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT file_path
        FROM documents
        WHERE id = ? AND project_id = ?
        """,
        (document_id, project_id),
    )
    document = row_to_dict(cursor, cursor.fetchone())
    connection.close()

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = document["file_path"]

    if not Path(file_path).exists():
        raise HTTPException(
            status_code=404,
            detail="The uploaded file could not be found on the server",
        )

    try:
        return {
            "project_id": project_id,
            "document_id": document_id,
            "extracted_text": extract_text(file_path),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not extract document text: {error}",
        )


# -------------------------
# Document indexing
# -------------------------

@app.post("/projects/{project_id}/documents/{document_id}/index")
def index_document(project_id: str, document_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT file_path
            FROM documents
            WHERE id = ? AND project_id = ?
            """,
            (document_id, project_id),
        )
        document = row_to_dict(cursor, cursor.fetchone())

        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = document["file_path"]

        if not Path(file_path).exists():
            raise HTTPException(
                status_code=404,
                detail="The uploaded file could not be found on the server",
            )

        chunks = split_text(extract_text(file_path))

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No text was extracted from this document",
            )

        embeddings = create_embeddings(chunks)

        cursor.execute(
            """
            DELETE FROM document_chunks
            WHERE project_id = ? AND document_id = ?
            """,
            (project_id, document_id),
        )

        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            cursor.execute(
                """
                INSERT INTO document_chunks
                    (project_id, document_id, chunk_index, chunk_text, embedding_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    document_id,
                    index,
                    chunk,
                    json.dumps(embedding),
                ),
            )

        connection.commit()

        return {
            "message": "Document indexed with embeddings successfully",
            "project_id": project_id,
            "document_id": document_id,
            "chunks_created": len(chunks),
            "embeddings_created": len(embeddings),
        }

    except HTTPException:
        connection.rollback()
        raise
    except Exception as error:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not index document: {error}",
        )
    finally:
        connection.close()


# -------------------------
# Semantic search
# -------------------------

@app.post("/projects/{project_id}/search")
def search_project_documents(project_id: str, request: SearchRequest):
    query = request.query.strip()

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if request.top_k < 1:
        raise HTTPException(status_code=400, detail="top_k must be at least 1")

    with get_connection() as connection:
        project = connection.execute(
            "SELECT project_id FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    results = retrieve_chunks(project_id, query, request.top_k)

    return {
        "project_id": project_id,
        "query": query,
        "results": results,
    }


# -------------------------
# AI question answering
# -------------------------

@app.post("/projects/{project_id}/ask")
def ask_project_documents(project_id: str, request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if request.top_k < 1:
        raise HTTPException(status_code=400, detail="top_k must be at least 1")

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")

    if not api_key or not model:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY or OPENROUTER_MODEL is missing from .env",
        )

    with get_connection() as connection:
        project = connection.execute(
            "SELECT project_id FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    sources = retrieve_chunks(project_id, question, request.top_k)

    if not sources:
        raise HTTPException(
            status_code=404,
            detail="No indexed document chunks found for this project",
        )

    context = "\n\n".join(
        f"Source: {source['filename']}\n{source['text']}"
        for source in sources
    )

    prompt = f"""
Answer the question using only the document context below.
If the answer is not present, say:
"I couldn't find that information in the indexed documents."
Do not guess or add outside information.

Document context:
{context}

Question:
{question}
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer questions using only the supplied document context. "
                            "Do not invent facts."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            },
            timeout=60,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"LLM request failed: {error}",
        )
    except (KeyError, IndexError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="The LLM returned an unexpected response",
        )

    return {
        "project_id": project_id,
        "question": question,
        "answer": answer,
        "sources": sources,
    }


# -------------------------
# Attestation endpoints
# -------------------------

@app.post("/projects/{project_id}/documents/{document_id}/attestations")
def submit_attestation(
    project_id: str,
    document_id: int,
    request: AttestationRequest,
):
    reviewer_name = request.reviewer_name.strip()

    if not reviewer_name:
        raise HTTPException(status_code=400, detail="Reviewer name cannot be empty")

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT id
            FROM documents
            WHERE id = ? AND project_id = ?
            """,
            (document_id, project_id),
        )

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found for this project",
            )

        cursor.execute(
            """
            INSERT INTO attestations
                (project_id, document_id, reviewer_name, decision, comments)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                document_id,
                reviewer_name,
                request.decision,
                request.comments.strip(),
            ),
        )
        connection.commit()

        return {
            "message": "Attestation submitted successfully",
            "attestation_id": cursor.lastrowid,
            "project_id": project_id,
            "document_id": document_id,
            "reviewer_name": reviewer_name,
            "decision": request.decision,
        }

    except HTTPException:
        raise
    except Exception as error:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not submit attestation: {error}",
        )
    finally:
        connection.close()


@app.get("/projects/{project_id}/attestations")
def get_project_attestations(project_id: str):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT project_id FROM projects WHERE project_id = ?",
            (project_id,),
        )

        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Project not found")

        cursor.execute(
            """
            SELECT
                id AS attestation_id,
                project_id,
                document_id,
                reviewer_name,
                decision,
                comments,
                attested_at
            FROM attestations
            WHERE project_id = ?
            ORDER BY id DESC
            """,
            (project_id,),
        )

        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()


# -------------------------
# Project dashboard
# -------------------------

@app.get("/projects/{project_id}/dashboard")
def get_project_dashboard(project_id: str):
    with get_connection() as connection:
        project = connection.execute(
            """
            SELECT project_id, project_name, status
            FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        document_count = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM documents
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()["total"]

        attestation_summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_attestations,
                SUM(CASE WHEN decision = 'Approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN decision = 'Rejected' THEN 1 ELSE 0 END) AS rejected,
                COUNT(DISTINCT document_id) AS reviewed_documents
            FROM attestations
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

    approved = attestation_summary["approved"] or 0
    rejected = attestation_summary["rejected"] or 0
    reviewed_documents = attestation_summary["reviewed_documents"] or 0

    return {
        "project_id": project["project_id"],
        "project_name": project["project_name"],
        "project_status": project["status"],
        "document_count": document_count,
        "total_attestations": attestation_summary["total_attestations"],
        "approved_attestations": approved,
        "rejected_attestations": rejected,
        "pending_documents": max(document_count - reviewed_documents, 0),
    }


# -------------------------
# Attestation CSV export
# -------------------------

@app.get("/projects/{project_id}/attestations/export")
def export_attestations(project_id: str):
    with get_connection() as connection:
        project = connection.execute(
            "SELECT project_id FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        rows = connection.execute(
            """
            SELECT
                a.id AS attestation_id,
                a.project_id,
                a.document_id,
                d.filename,
                a.reviewer_name,
                a.decision,
                a.comments,
                a.attested_at
            FROM attestations a
            JOIN documents d ON d.id = a.document_id
            WHERE a.project_id = ?
            ORDER BY a.id DESC
            """,
            (project_id,),
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Attestation ID",
        "Project ID",
        "Document ID",
        "Filename",
        "Reviewer",
        "Decision",
        "Comments",
        "Attested At",
    ])

    for row in rows:
        writer.writerow([
            row["attestation_id"],
            row["project_id"],
            row["document_id"],
            row["filename"],
            row["reviewer_name"],
            row["decision"],
            row["comments"],
            row["attested_at"],
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="attestations_{project_id}.csv"'
        },
    )