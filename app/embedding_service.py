from sentence_transformers import SentenceTransformer

# This model runs locally. The first use may download the model files.
model = SentenceTransformer("all-MiniLM-L6-v2")


def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Convert a list of text chunks into embedding vectors."""
    if not texts:
        return []

    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()