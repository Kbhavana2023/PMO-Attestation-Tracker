from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from docx import Document
from openpyxl import load_workbook


# Tesseract executable installed on Windows
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".pdf":
        with fitz.open(path) as pdf:
            # First try extracting selectable PDF text
            text = "\n".join(page.get_text() for page in pdf).strip()

            if text:
                return text

            # If the PDF is scanned, use OCR on each page
            ocr_text = []

            for page in pdf:
                pixmap = page.get_pixmap(dpi=200)
                image = Image.frombytes(
                    "RGB",
                    [pixmap.width, pixmap.height],
                    pixmap.samples,
                )
                ocr_text.append(pytesseract.image_to_string(image))

            return "\n".join(ocr_text).strip()

    if extension == ".docx":
        document = Document(path)
        return "\n".join(
            paragraph.text for paragraph in document.paragraphs
        ).strip()

    if extension == ".xlsx":
        workbook = load_workbook(path, data_only=True)
        text = []

        for sheet in workbook.worksheets:
            text.append(f"Sheet: {sheet.title}")

            for row in sheet.iter_rows(values_only=True):
                values = [str(value) for value in row if value is not None]
                if values:
                    text.append(" | ".join(values))

        return "\n".join(text).strip()

    raise ValueError(f"Unsupported file type: {extension}")