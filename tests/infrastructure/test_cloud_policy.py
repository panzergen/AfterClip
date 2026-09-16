from pathlib import Path

import pytest

from app.infrastructure.cloud_policy import (
    CloudPolicyViolation,
    assert_not_video_file,
    assert_upload_allowed,
    inline_data_part,
)


def test_video_mime_is_rejected():
    with pytest.raises(CloudPolicyViolation):
        inline_data_part("video/mp4", b"video-bytes")


def test_unknown_mime_is_rejected():
    with pytest.raises(CloudPolicyViolation):
        inline_data_part("application/octet-stream", b"x")


def test_png_and_audio_are_allowed():
    part = inline_data_part("image/png", b"png-bytes")
    assert part["inline_data"]["mime_type"] == "image/png"
    assert_upload_allowed("image/jpeg")
    assert_upload_allowed("audio/wav")
    assert_upload_allowed("audio/x-wav")


def test_video_file_is_rejected():
    with pytest.raises(CloudPolicyViolation, match="never sent"):
        assert_not_video_file(Path("clip.mp4"))
    assert_not_video_file(Path("frame.png"))  # non-video is fine
