import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="PMO Attestation", layout="wide")
st.title("PMO Attestation Automation")


def api_error_message(error):
    """Show a useful message for API and connection errors."""
    if isinstance(error, requests.HTTPError) and error.response is not None:
        try:
            detail = error.response.json().get("detail", error.response.text)
        except ValueError:
            detail = error.response.text
        return f"API error ({error.response.status_code}): {detail}"

    return str(error)


# -------------------------
# Load projects
# -------------------------

try:
    response = requests.get(f"{API_URL}/projects", timeout=10)
    response.raise_for_status()
    projects = response.json()
except requests.RequestException as error:
    st.error(
        "Could not connect to the API. Make sure Uvicorn is running.\n\n"
        f"{api_error_message(error)}"
    )
    st.stop()

if not projects:
    st.info("No projects found. Create a project using the API first.")
    st.stop()

project_options = {
    f"{project['project_name']} ({project['project_id']})": project["project_id"]
    for project in projects
}

selected_project_label = st.selectbox(
    "Select project",
    list(project_options),
)
project_id = project_options[selected_project_label]


# -------------------------
# Project dashboard
# -------------------------

st.subheader("Project dashboard")

try:
    response = requests.get(
        f"{API_URL}/projects/{project_id}/dashboard",
        timeout=10,
    )
    response.raise_for_status()
    dashboard = response.json()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documents", dashboard["document_count"])
    col2.metric("Approved", dashboard["approved_attestations"])
    col3.metric("Rejected", dashboard["rejected_attestations"])
    col4.metric("Pending documents", dashboard["pending_documents"])

except requests.RequestException as error:
    st.error(f"Could not load dashboard: {api_error_message(error)}")

st.divider()


# -------------------------
# Upload document
# -------------------------

st.subheader("Upload a document")

uploaded_file = st.file_uploader("Choose a file")

if uploaded_file and st.button("Upload document"):
    try:
        response = requests.post(
            f"{API_URL}/projects/{project_id}/documents",
            files={
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type or "application/octet-stream",
                )
            },
            timeout=60,
        )
        response.raise_for_status()

        st.success(f"Uploaded: {uploaded_file.name}")
        st.rerun()

    except requests.RequestException as error:
        st.error(f"Upload failed: {api_error_message(error)}")


# -------------------------
# List and index documents
# -------------------------

st.subheader("Project documents")

try:
    response = requests.get(
        f"{API_URL}/projects/{project_id}/documents",
        timeout=10,
    )
    response.raise_for_status()
    documents = response.json()

    if documents:
        st.dataframe(
            [
                {
                    "Document ID": document["id"],
                    "Filename": document["filename"],
                }
                for document in documents
            ],
            use_container_width=True,
        )

        document_options = {
            f"{document['filename']} (ID: {document['id']})": document["id"]
            for document in documents
        }

        selected_document_label = st.selectbox(
            "Choose a document",
            list(document_options),
        )
        document_id = document_options[selected_document_label]

        if st.button("Index selected document"):
            try:
                response = requests.post(
                    f"{API_URL}/projects/{project_id}/documents/"
                    f"{document_id}/index",
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()

                st.success(
                    "Document indexed successfully. "
                    f"Created {result['chunks_created']} chunks."
                )

            except requests.RequestException as error:
                st.error(f"Indexing failed: {api_error_message(error)}")

        # -------------------------
        # Submit an attestation
        # -------------------------

        st.subheader("Submit an attestation")

        with st.form("attestation_form"):
            reviewer_name = st.text_input("Reviewer name")
            decision = st.selectbox("Decision", ["Approved", "Rejected"])
            comments = st.text_area("Comments")

            submitted = st.form_submit_button("Submit attestation")

        if submitted:
            if not reviewer_name.strip():
                st.warning("Enter the reviewer name.")
            else:
                try:
                    response = requests.post(
                        f"{API_URL}/projects/{project_id}/documents/"
                        f"{document_id}/attestations",
                        json={
                            "reviewer_name": reviewer_name.strip(),
                            "decision": decision,
                            "comments": comments.strip(),
                        },
                        timeout=10,
                    )
                    response.raise_for_status()

                    st.success("Attestation submitted.")
                    st.rerun()

                except requests.RequestException as error:
                    st.error(
                        f"Could not submit attestation: "
                        f"{api_error_message(error)}"
                    )

    else:
        st.info("No documents uploaded to this project yet.")

except requests.RequestException as error:
    st.error(f"Could not load documents: {api_error_message(error)}")


# -------------------------
# Attestation history
# -------------------------

st.subheader("Attestation history")

try:
    response = requests.get(
        f"{API_URL}/projects/{project_id}/attestations",
        timeout=10,
    )
    response.raise_for_status()
    attestations = response.json()

    if attestations:
        st.dataframe(attestations, use_container_width=True)
    else:
        st.info("No attestations submitted for this project yet.")

except requests.RequestException as error:
    st.error(f"Could not load attestation history: {api_error_message(error)}")


# -------------------------
# Export attestation history
# -------------------------

st.subheader("Export attestation history")

try:
    response = requests.get(
        f"{API_URL}/projects/{project_id}/attestations/export",
        timeout=30,
    )
    response.raise_for_status()

    st.download_button(
        label="Download attestation history as CSV",
        data=response.content,
        file_name=f"attestations_{project_id}.csv",
        mime="text/csv",
    )

except requests.RequestException as error:
    st.error(f"Could not export attestations: {api_error_message(error)}")