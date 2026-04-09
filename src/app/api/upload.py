"""POST /upload/{id} — file upload endpoint."""

import mimetypes
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..models import UploadResponse
from ..storage import UploadStorage

router = APIRouter(prefix="/upload", tags=["upload"])

_storage: UploadStorage | None = None


def _get_storage() -> UploadStorage:
    global _storage
    if _storage is None:
        _storage = UploadStorage()
    return _storage


@router.post("/{upload_id}", response_model=UploadResponse)
async def upload_file(upload_id: str, file: UploadFile = File(...)) -> UploadResponse:
    """Upload a file to an existing upload session.

    The file will be associated with the given `upload_id` (created by a prior
    POST /upload call). Subsequent uploads with the same upload_id are accumulated.

    Use the returned `upload_id` in POST /run to attach these files to an agent run.
    """
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {e}")

    storage = _get_storage()

    # Append to existing upload_id directory, or create new one if it doesn't exist
    existing = storage.get(upload_id)
    if existing:
        # Append to existing upload dir
        upload_dir = storage.base_dir / upload_id
        safe_name = file.filename or "file"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
        file_path = upload_dir / safe_name
        file_path.write_bytes(content)
    else:
        # Create new upload with this upload_id
        upload_dir = storage.base_dir / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = file.filename or "file"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
        file_path = upload_dir / safe_name
        file_path.write_bytes(content)
        metadata = {
            "upload_id": upload_id,
            "filename": safe_name,
            "size_bytes": len(content),
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        (upload_dir / "_meta.json").write_text(__import__("json").dumps(metadata))

    return UploadResponse(
        upload_id=upload_id,
        filename=safe_name,
        size_bytes=len(content),
        content_type=file.content_type or mimetypes.guess_type(safe_name)[0],
    )


@router.post("/", response_model=UploadResponse, status_code=201)
async def create_upload(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a file and receive a new upload_id.

    Call POST /upload/{upload_id} to add more files to the same session.
    """
    import uuid

    upload_id = uuid.uuid4().hex
    return await upload_file(upload_id, file)
