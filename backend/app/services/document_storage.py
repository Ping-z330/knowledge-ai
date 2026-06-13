from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import get_settings

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".md", ".txt"}


def validate_upload_filename(filename: str) -> str:
    clean_name = Path(filename).name.strip()
    if not clean_name:
        raise ValueError("Filename is required")

    extension = Path(clean_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported file type. Allowed extensions: {allowed}")

    return clean_name


def build_storage_path(knowledge_base_id: str, filename: str) -> Path:
    extension = Path(filename).suffix.lower()
    storage_dir = get_settings().storage_dir / knowledge_base_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir / f"{uuid4()}{extension}"


def save_upload_file(upload_file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as output:
        while chunk := upload_file.file.read(1024 * 1024):
            output.write(chunk)

