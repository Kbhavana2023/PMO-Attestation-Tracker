import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="PMO Attestation", layout="wide")
st.title("PMO Attestation Automation")

def api_get(path):
    response = requests.get(f"{API_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()

def api_post(path, **kwargs):
    response = requests.post(f"{API_URL}{path}", timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()

# Projects
try:
    projects = api_get("/projects")
except requests.RequestException:
    st.error("Could not connect to the API. Make sure Uvicorn is running.")
    st.stop()

if not projects:
    st.info("Create a project first using POST /projects in Swagger.")
    st.stop()

project_options = {
    f"{p['project_name']} ({p['project_id']})": p["project_id"]
    for p in projects
}
project_label = st.selectbox("Select project", list(project_options))
project_id = project_options[project_label]

# Dashboard summary
st.subheader("Project summary")
try:
    dashboard = api_get(f"/projects/{project_id}/dashboard")
    cols = st.columns(4)
    cols[0].metric("Documents", dashboard["document_count"])
    cols[1].metric("Approved", dashboard["approved_attestations"])
    cols[2].metric("Rejected", dashboard["rejected_attestations"])
    cols[3].metric("Pending", dashboard["pending_documents"])
except requests.RequestException as error:
    st.error(f"Could not load project summary: {error}")

st.divider()

# Upload
st.subheader("Upload document")
file = st.file_uploader("Choose a document")

if file and st.button("Upload"):
    try:
        result = api_post(
            f"/projects/{project_id}/documents",
            files={"file": (file.name, file.getvalue(), file.type or "application/octet-stream")},
        )
        st.success(f"Uploaded successfully. Document ID: {result['document_id']}")
        st.rerun()
    except requests.RequestException as error:
        st.error(f"Upload failed: {error}")

# Documents and indexing
st.subheader("Documents")
try:
    documents = api_get(f"/projects/{project_id}/documents")

    if documents:
        st.dataframe(
            [{"ID": d["id"], "Filename": d["filename"]} for d in documents],
            use_container_width=True,
        )

        doc_options = {
            f"{d['filename']} (ID {d['id']})": d["id"] for d in documents
        }
        selected_doc_label = st.selectbox("Choose document", list(doc_options))
        document_id = doc_options[selected_doc_label]

        if st.button("Index selected document"):
            try:
                result = api_post(
                    f"/projects/{project_id}/documents/{document_id}/index"
                )
                st.success(
                    f"Indexed successfully. Chunks created: {result['chunks_created']}"
                )
            except requests.RequestException as error:
                st.error(f"Indexing failed: {error}")
    else:
        st.info("Upload a document to get started.")
except requests.RequestException as error:
    st.error(f"Could not load documents: {error}")

st.divider()

# Semantic search
st.subheader("Search documents")
search_query = st.text_input("Enter a search query")

if st.button("Search"):
    if not search_query.strip():
        st.warning("Enter a search query first.")
    else:
        try:
            result = api_post(
                f"/projects/{project_id}/search",
                json={"query": search_query, "top_k": 3},
            )
            if result["results"]:
                for item in result["results"]:
                    st.markdown(f"**{item['filename']}** · Similarity: {item['similarity']}")
                    st.write(item["text"])
                    st.caption(f"Document ID: {item['document_id']}")
            else:
                st.info("No indexed matching text found. Index a document first.")
        except requests.RequestException as error:
            st.error(f"Search failed: {error}")

# AI question answering
st.subheader("Ask a question about project documents")
question = st.text_area("Question")

if st.button("Ask AI"):
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        try:
            result = api_post(
                f"/projects/{project_id}/ask",
                json={"question": question, "top_k": 3},
            )
            st.markdown("**Answer**")
            st.write(result["answer"])

            st.markdown("**Sources**")
            for source in result["sources"]:
                st.caption(
                    f"{source['filename']} · Similarity: {source['similarity']}"
                )
                st.write(source["text"])
        except requests.RequestException as error:
            st.error(f"AI question failed: {error}")

st.divider()

# Attestations
st.subheader("Submit an attestation")
try:
    documents = api_get(f"/projects/{project_id}/documents")

    if documents:
        doc_options = {
            f"{d['filename']} (ID {d['id']})": d["id"] for d in documents
        }
        selected_label = st.selectbox("Document to attest", list(doc_options))
        attestation_doc_id = doc_options[selected_label]

        with st.form("attestation_form"):
            reviewer = st.text_input("Reviewer name")
            decision = st.selectbox("Decision", ["Approved", "Rejected"])
            comments = st.text_area("Comments")
            submit = st.form_submit_button("Submit attestation")

        if submit:
            if not reviewer.strip():
                st.warning("Enter the reviewer name.")
            else:
                try:
                    api_post(
                        f"/projects/{project_id}/documents/"
                        f"{attestation_doc_id}/attestations",
                        json={
                            "reviewer_name": reviewer,
                            "decision": decision,
                            "comments": comments,
                        },
                    )
                    st.success("Attestation submitted.")
                    st.rerun()
                except requests.RequestException as error:
                    st.error(f"Attestation failed: {error}")
except requests.RequestException as error:
    st.error(f"Could not load documents for attestation: {error}")

st.subheader("Attestation history")
try:
    attestations = api_get(f"/projects/{project_id}/attestations")
    if attestations:
        st.dataframe(attestations, use_container_width=True)
    else:
        st.info("No attestations recorded yet.")
except requests.RequestException as error:
    st.error(f"Could not load attestation history: {error}")