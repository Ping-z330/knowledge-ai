from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import get_settings

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}

# 每种格式的 magic bytes（文件头签名）
_MAGIC_BYTES: dict[str, bytes] = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
    # .md / .txt 无固定文件头，不做 magic bytes 校验
}


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
    extension = destination.suffix.lower()
    expected_magic = _MAGIC_BYTES.get(extension)

    with destination.open("wb") as output:
        first_chunk = upload_file.file.read(1024 * 1024)
        if not first_chunk:
            raise ValueError("Uploaded file is empty")

        if expected_magic and not first_chunk.startswith(expected_magic):
            raise ValueError(
                f"File content does not match extension '{extension}'. "
                f"Expected magic bytes for {extension}."
            )

        output.write(first_chunk)
        while chunk := upload_file.file.read(1024 * 1024):
            output.write(chunk)

