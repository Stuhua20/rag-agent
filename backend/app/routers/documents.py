from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas.document import ChunkPage, UploadResponse
from app.services.document_pipeline import document_pipeline


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    file_name: str | None = Form(default=None),
    source_relative_path: str | None = Form(default=None),
) -> dict:
    try:
        return await document_pipeline.upload_and_parse(file, file_name, source_relative_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Upload failed: {error}") from error


@router.get("")
def list_documents(
    keyword: str | None = None,
    status: str | None = None,
) -> list[dict]:
    return document_pipeline.list_documents(keyword, status)


@router.get("/{document_id}")
def get_document(document_id: str) -> dict:
    document = document_pipeline.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/sheets")
def list_sheets(document_id: str) -> list[dict]:
    if not document_pipeline.get_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return document_pipeline.list_sheets(document_id)


@router.get("/{document_id}/chunks", response_model=ChunkPage)
def list_chunks(
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    if not document_pipeline.get_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return document_pipeline.list_chunks(document_id, page, page_size)


@router.delete("/{document_id}")
def delete_document(document_id: str) -> dict[str, bool]:
    deleted = document_pipeline.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


@router.post("/{document_id}/reindex")
def reindex_document(document_id: str) -> dict:
    if not document_pipeline.get_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return document_pipeline.reindex_document(document_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="重新索引失败，原有索引数据已保留。") from error
