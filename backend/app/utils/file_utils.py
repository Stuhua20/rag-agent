from pathlib import Path, PureWindowsPath


SUPPORTED_EXTENSIONS = {".xlsx", ".csv", ".docx", ".pdf"}


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def ensure_supported_file(filename: str) -> str:
    extension = get_file_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{extension}'. Supported types: {supported}")
    return extension.lstrip(".")


def validate_source_relative_path(value: str | None) -> str | None:
    """Validate display metadata only; never use this path for file storage."""
    if not value:
        return None
    normalized = value.replace("\\", "/")
    if (
        len(normalized) > 1024
        or normalized.startswith("/")
        or PureWindowsPath(value).drive
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise ValueError("Source path must be a relative path without empty, dot or parent segments.")
    return normalized
