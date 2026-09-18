import os
import secrets
from fastapi import UploadFile, HTTPException, status

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024 # 5 MB limit


def _detect_image_type(contents: bytes) -> str | None:
    if contents.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if contents.startswith(b"RIFF") and contents[8:12] == b"WEBP":
        return "webp"
    return None

async def save_profile_photo(file: UploadFile, subfolder: str = "avatars") -> str:
    """Save a profile image using the shared CMS image uploader."""
    return await save_cms_image(file, subfolder, "avatar")


async def save_cms_image(file: UploadFile, subfolder: str, filename_prefix: str) -> str:
    """Validate and save a CMS image using the shared upload rules."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Please select a cover image.")

    contents = await file.read(MAX_FILE_SIZE + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="The selected image is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Image must be 5 MB or smaller.")

    ext = _detect_image_type(contents)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only JPG, JPEG, PNG and WebP images are allowed.")
    expected_mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
    if file.content_type and file.content_type.lower() != expected_mime:
        raise HTTPException(status_code=400, detail="The uploaded file type does not match its image content.")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(base_dir, "static", "uploads", subfolder)
    os.makedirs(target_dir, exist_ok=True)
    unique_filename = f"{filename_prefix}_{secrets.token_hex(12)}.{ext}"
    filepath = os.path.join(target_dir, unique_filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    return f"/static/uploads/{subfolder}/{unique_filename}"


async def save_story_cover_image(file: UploadFile) -> str:
    """Save a Web Story image using the shared CMS image uploader."""
    return await save_cms_image(file, "stories", "story")


async def save_article_image(file: UploadFile) -> str:
    """Save an article featured image using the shared CMS image uploader."""
    return await save_cms_image(file, "articles", "article")


async def save_web_story_image(file: UploadFile) -> str:
    """Alias used by the Web Stories builder for every page image."""
    return await save_story_cover_image(file)
