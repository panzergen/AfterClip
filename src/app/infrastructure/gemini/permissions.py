"""Cloud upload policy for Gemini (T18b/T18c).

Only explicitly allowed payload types may leave the machine: transcript text,
audio chunks the user consented to, and single frames. Video files can never
be uploaded - the policy rejects them before any request is built.
"""
import base64
from pathlib import Path

from app.domain.constants import VIDEO_SUFFIXES

ALLOWED_INLINE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "audio/wav", "audio/x-wav"})


class CloudPolicyViolation(RuntimeError):
    """Raised when a cloud payload would violate the upload policy."""


def assert_upload_allowed(mime_type: str) -> None:
    if mime_type.startswith("video/") or mime_type not in ALLOWED_INLINE_MIME_TYPES:
        raise CloudPolicyViolation(
            f"Cloud uploads are restricted to text, images, and consented audio; '{mime_type}' is not permitted."
        )


def assert_not_video_file(path: Path) -> None:
    if Path(path).suffix.lower() in VIDEO_SUFFIXES:
        raise CloudPolicyViolation(
            f"Video files are never sent to the cloud; refused '{Path(path).name}'."
        )


def inline_data_part(mime_type: str, data: bytes) -> dict:
    assert_upload_allowed(mime_type)
    return {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}}
