from unittest.mock import AsyncMock, patch

UPLOAD_URL = "/api/v1/upload"

VALID_FORM = {
    "board": "CBSE",
    "standard": "Class 10",
    "subject": "Mathematics",
}

VALID_FILE = ("file", ("test.pdf", b"PDF content here", "application/pdf"))


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestUploadAuthentication:
    def test_no_auth_header_returns_4xx(self, client):
        response = client.post(UPLOAD_URL, data=VALID_FORM, files=[VALID_FILE])
        # FastAPI's HTTPBearer raises 401 or 403 depending on version when the
        # Authorization header is absent; either is a valid auth rejection.
        assert response.status_code in (401, 403)

    def test_expired_token_returns_401(self, client, expired_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {expired_token}"},
            data=VALID_FORM,
            files=[VALID_FILE],
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_invalid_token_returns_401(self, client, invalid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {invalid_token}"},
            data=VALID_FORM,
            files=[VALID_FILE],
        )
        assert response.status_code == 401

    def test_malformed_bearer_returns_401(self, client):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": "Bearer "},
            data=VALID_FORM,
            files=[VALID_FILE],
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Successful uploads — state resolution logic
# ---------------------------------------------------------------------------

class TestUploadStateResolution:
    def test_cbse_resolves_state_to_central(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data=VALID_FORM,
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        assert response.json()["state"] == "Central"

    def test_icse_ignores_provided_state(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data={
                    "board": "ICSE",
                    "standard": "Class 10",
                    "subject": "Mathematics",
                    "state": "Maharashtra",
                },
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        assert response.json()["state"] == "Central"

    def test_igcse_resolves_state_to_central(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data={"board": "IGCSE", "standard": "Class 10", "subject": "Mathematics"},
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        assert response.json()["state"] == "Central"

    def test_ib_resolves_state_to_central(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data={"board": "IB", "standard": "Class 12", "subject": "Physics"},
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        assert response.json()["state"] == "Central"

    def test_state_board_with_state_uses_provided_state(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data={
                    "board": "State Board",
                    "standard": "Class 10",
                    "subject": "Mathematics",
                    "state": "Maharashtra",
                },
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        assert response.json()["state"] == "Maharashtra"

    def test_state_board_without_state_resolves_to_unspecified(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data={
                    "board": "State Board",
                    "standard": "Class 10",
                    "subject": "Mathematics",
                },
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        assert response.json()["state"] == "Unspecified"


# ---------------------------------------------------------------------------
# Successful upload — response shape
# ---------------------------------------------------------------------------

class TestUploadResponseShape:
    def test_response_contains_all_expected_fields(self, client, valid_token):
        expected_url = "https://test-bucket.s3.us-east-1.amazonaws.com/uploads/abc.pdf"
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = expected_url
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data=VALID_FORM,
                files=[VALID_FILE],
            )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == expected_url
        assert data["filename"] == "test.pdf"
        assert data["content_type"] == "application/pdf"
        assert data["board"] == "CBSE"
        assert data["standard"] == "Class 10"
        assert data["subject"] == "Mathematics"
        assert data["uploaded_by"] == "user123"

    def test_uploaded_by_reflects_jwt_sub(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://example.com/file.pdf"
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data=VALID_FORM,
                files=[VALID_FILE],
            )

        assert response.json()["uploaded_by"] == "user123"

    def test_s3_service_called_with_resolved_state(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.return_value = "https://example.com/file.pdf"
            client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data=VALID_FORM,
                files=[VALID_FILE],
            )

        # state argument (3rd positional) must be "Central" for CBSE
        _, call_args, _ = mock_s3.mock_calls[0]
        assert call_args[2] == "Central"


# ---------------------------------------------------------------------------
# Form validation (422)
# ---------------------------------------------------------------------------

class TestUploadFormValidation:
    def test_invalid_board_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={"board": "UNKNOWN", "standard": "Class 10", "subject": "Mathematics"},
            files=[VALID_FILE],
        )
        assert response.status_code == 422

    def test_invalid_standard_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={"board": "CBSE", "standard": "Class 13", "subject": "Mathematics"},
            files=[VALID_FILE],
        )
        assert response.status_code == 422

    def test_invalid_subject_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={"board": "CBSE", "standard": "Class 10", "subject": "Art"},
            files=[VALID_FILE],
        )
        assert response.status_code == 422

    def test_missing_board_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={"standard": "Class 10", "subject": "Mathematics"},
            files=[VALID_FILE],
        )
        assert response.status_code == 422

    def test_missing_standard_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={"board": "CBSE", "subject": "Mathematics"},
            files=[VALID_FILE],
        )
        assert response.status_code == 422

    def test_missing_subject_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={"board": "CBSE", "standard": "Class 10"},
            files=[VALID_FILE],
        )
        assert response.status_code == 422

    def test_missing_file_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data=VALID_FORM,
        )
        assert response.status_code == 422

    def test_invalid_state_for_state_board_returns_422(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data={
                "board": "State Board",
                "standard": "Class 10",
                "subject": "Mathematics",
                "state": "NotARealState",
            },
            files=[VALID_FILE],
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# File / S3 errors surfaced through the route
# ---------------------------------------------------------------------------

class TestUploadFileErrors:
    def test_unsupported_content_type_returns_415(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data=VALID_FORM,
            files=[("file", ("malware.exe", b"binary", "application/octet-stream"))],
        )
        assert response.status_code == 415

    def test_empty_file_returns_400(self, client, valid_token):
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data=VALID_FORM,
            files=[("file", ("empty.pdf", b"", "application/pdf"))],
        )
        assert response.status_code == 400

    def test_file_exceeding_size_limit_returns_413(self, client, valid_token):
        oversized = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
        response = client.post(
            UPLOAD_URL,
            headers={"Authorization": f"Bearer {valid_token}"},
            data=VALID_FORM,
            files=[("file", ("big.pdf", oversized, "application/pdf"))],
        )
        assert response.status_code == 413

    def test_s3_no_credentials_returns_500(self, client, valid_token):
        from botocore.exceptions import NoCredentialsError

        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.side_effect = __import__("fastapi").HTTPException(
                status_code=500, detail="AWS credentials are misconfigured."
            )
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data=VALID_FORM,
                files=[VALID_FILE],
            )

        assert response.status_code == 500
        assert "credentials" in response.json()["detail"].lower()

    def test_s3_client_error_returns_500(self, client, valid_token):
        with patch(
            "app.api.v1.routes.upload.upload_file_to_s3", new_callable=AsyncMock
        ) as mock_s3:
            mock_s3.side_effect = __import__("fastapi").HTTPException(
                status_code=500, detail="S3 upload failed: bucket not found"
            )
            response = client.post(
                UPLOAD_URL,
                headers={"Authorization": f"Bearer {valid_token}"},
                data=VALID_FORM,
                files=[VALID_FILE],
            )

        assert response.status_code == 500
