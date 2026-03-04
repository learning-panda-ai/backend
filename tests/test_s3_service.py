from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import HTTPException

from app.schemas.upload import Board, Standard, Subject
from app.services.s3 import ALLOWED_CONTENT_TYPES, _build_object_key, upload_file_to_s3


def make_upload_file(content: bytes, content_type: str, filename: str = "test.pdf"):
    """Return a minimal UploadFile-like mock."""
    mock = MagicMock()
    mock.content_type = content_type
    mock.filename = filename
    mock.read = AsyncMock(return_value=content)
    return mock


# ---------------------------------------------------------------------------
# _build_object_key
# ---------------------------------------------------------------------------

class TestBuildObjectKey:
    def test_key_starts_with_s3_prefix(self):
        key = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert key.startswith("uploads/")

    def test_key_contains_board(self):
        key = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "CBSE" in key

    def test_key_contains_state(self):
        key = _build_object_key("doc.pdf", Board.STATE_BOARD, "Maharashtra", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "Maharashtra" in key

    def test_key_contains_standard(self):
        key = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "Class 10" in key

    def test_key_contains_subject(self):
        key = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "Mathematics" in key

    def test_key_preserves_pdf_extension(self):
        key = _build_object_key("document.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert key.endswith(".pdf")

    def test_key_preserves_jpg_extension(self):
        key = _build_object_key("image.jpg", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert key.endswith(".jpg")

    def test_key_lowercases_extension(self):
        key = _build_object_key("doc.PDF", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert key.endswith(".pdf")

    def test_key_without_extension_has_no_trailing_dot(self):
        key = _build_object_key("noextension", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        filename_part = key.split("/")[-1]
        assert not filename_part.endswith(".")

    def test_two_calls_produce_unique_keys(self):
        key1 = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        key2 = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert key1 != key2

    def test_key_layout_order(self):
        key = _build_object_key("doc.pdf", Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        # Expected: uploads/CBSE/Central/Class 10/Mathematics/<uuid>.pdf
        parts = key.split("/")
        assert parts[0] == "uploads"
        assert parts[1] == "CBSE"
        assert parts[2] == "Central"
        assert parts[3] == "Class 10"
        assert parts[4] == "Mathematics"

    def test_state_board_key_layout(self):
        key = _build_object_key("doc.pdf", Board.STATE_BOARD, "Kerala", Standard.CLASS_12, Subject.PHYSICS)
        parts = key.split("/")
        assert parts[1] == "State Board"
        assert parts[2] == "Kerala"


# ---------------------------------------------------------------------------
# upload_file_to_s3 — validation errors
# ---------------------------------------------------------------------------

class TestUploadFileToS3Validation:
    @pytest.mark.asyncio
    async def test_unsupported_mime_raises_415(self):
        mock_file = make_upload_file(b"binary", "application/octet-stream")
        with pytest.raises(HTTPException) as exc_info:
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_unsupported_mime_detail_lists_allowed_types(self):
        mock_file = make_upload_file(b"binary", "application/zip")
        with pytest.raises(HTTPException) as exc_info:
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "application/zip" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_empty_file_raises_400(self):
        mock_file = make_upload_file(b"", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_file_detail_mentions_empty(self):
        mock_file = make_upload_file(b"", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "empty" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_oversized_file_raises_413(self):
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        mock_file = make_upload_file(oversized, "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_file_at_exact_size_limit_is_accepted(self):
        exact = b"x" * (10 * 1024 * 1024)
        mock_file = make_upload_file(exact, "application/pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_client_fn.return_value = MagicMock()
            url = await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# upload_file_to_s3 — S3 interaction
# ---------------------------------------------------------------------------

class TestUploadFileToS3S3Interaction:
    @pytest.mark.asyncio
    async def test_success_returns_https_url(self):
        mock_file = make_upload_file(b"valid pdf content", "application/pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_client_fn.return_value = MagicMock()
            url = await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert url.startswith("https://")

    @pytest.mark.asyncio
    async def test_success_url_contains_bucket_name(self):
        mock_file = make_upload_file(b"valid pdf content", "application/pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_client_fn.return_value = MagicMock()
            url = await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "test-bucket" in url

    @pytest.mark.asyncio
    async def test_success_url_contains_region(self):
        mock_file = make_upload_file(b"valid pdf content", "application/pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_client_fn.return_value = MagicMock()
            url = await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert "us-east-1" in url

    @pytest.mark.asyncio
    async def test_put_object_called_once(self):
        mock_file = make_upload_file(b"pdf content", "application/pdf", "doc.pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_s3 = MagicMock()
            mock_client_fn.return_value = mock_s3
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        mock_s3.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_put_object_receives_correct_bucket(self):
        mock_file = make_upload_file(b"pdf content", "application/pdf", "doc.pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_s3 = MagicMock()
            mock_client_fn.return_value = mock_s3
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        kwargs = mock_s3.put_object.call_args.kwargs
        assert kwargs["Bucket"] == "test-bucket"

    @pytest.mark.asyncio
    async def test_put_object_receives_correct_content_type(self):
        mock_file = make_upload_file(b"pdf content", "application/pdf", "doc.pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_s3 = MagicMock()
            mock_client_fn.return_value = mock_s3
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        kwargs = mock_s3.put_object.call_args.kwargs
        assert kwargs["ContentType"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_put_object_receives_correct_body(self):
        mock_file = make_upload_file(b"exact content", "application/pdf", "doc.pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_s3 = MagicMock()
            mock_client_fn.return_value = mock_s3
            await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        kwargs = mock_s3.put_object.call_args.kwargs
        assert kwargs["Body"] == b"exact content"

    @pytest.mark.asyncio
    async def test_no_credentials_error_raises_500(self):
        mock_file = make_upload_file(b"valid content", "application/pdf")
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_s3 = MagicMock()
            mock_s3.put_object.side_effect = NoCredentialsError()
            mock_client_fn.return_value = mock_s3
            with pytest.raises(HTTPException) as exc_info:
                await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert exc_info.value.status_code == 500
        assert "credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_client_error_raises_500(self):
        mock_file = make_upload_file(b"valid content", "application/pdf")
        client_error = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}},
            "PutObject",
        )
        with patch("app.services.s3._s3_client") as mock_client_fn:
            mock_s3 = MagicMock()
            mock_s3.put_object.side_effect = client_error
            mock_client_fn.return_value = mock_s3
            with pytest.raises(HTTPException) as exc_info:
                await upload_file_to_s3(mock_file, Board.CBSE, "Central", Standard.CLASS_10, Subject.MATHEMATICS)
        assert exc_info.value.status_code == 500
        assert "The specified bucket does not exist" in exc_info.value.detail


# ---------------------------------------------------------------------------
# ALLOWED_CONTENT_TYPES allowlist
# ---------------------------------------------------------------------------

class TestAllowedContentTypes:
    def test_pdf_allowed(self):
        assert "application/pdf" in ALLOWED_CONTENT_TYPES

    def test_jpeg_allowed(self):
        assert "image/jpeg" in ALLOWED_CONTENT_TYPES

    def test_png_allowed(self):
        assert "image/png" in ALLOWED_CONTENT_TYPES

    def test_gif_allowed(self):
        assert "image/gif" in ALLOWED_CONTENT_TYPES

    def test_webp_allowed(self):
        assert "image/webp" in ALLOWED_CONTENT_TYPES

    def test_svg_allowed(self):
        assert "image/svg+xml" in ALLOWED_CONTENT_TYPES

    def test_mp4_allowed(self):
        assert "video/mp4" in ALLOWED_CONTENT_TYPES

    def test_webm_allowed(self):
        assert "video/webm" in ALLOWED_CONTENT_TYPES

    def test_mp3_allowed(self):
        assert "audio/mpeg" in ALLOWED_CONTENT_TYPES

    def test_wav_allowed(self):
        assert "audio/wav" in ALLOWED_CONTENT_TYPES

    def test_ogg_allowed(self):
        assert "audio/ogg" in ALLOWED_CONTENT_TYPES

    def test_octet_stream_not_allowed(self):
        assert "application/octet-stream" not in ALLOWED_CONTENT_TYPES

    def test_zip_not_allowed(self):
        assert "application/zip" not in ALLOWED_CONTENT_TYPES

    def test_text_plain_not_allowed(self):
        assert "text/plain" not in ALLOWED_CONTENT_TYPES

    def test_html_not_allowed(self):
        assert "text/html" not in ALLOWED_CONTENT_TYPES
