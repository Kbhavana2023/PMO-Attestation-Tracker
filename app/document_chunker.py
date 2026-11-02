def split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into chunks of up to chunk_size characters.
    Each chunk overlaps the previous one by 'overlap' characters.
    """
    text = text.strip()

    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks