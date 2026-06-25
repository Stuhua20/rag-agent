from pathlib import Path


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def ensure_supported_file(filename: str) -> str:
    extension = get_file_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{extension}'. Supported types: {supported}")
    return extension.lstrip(".")

