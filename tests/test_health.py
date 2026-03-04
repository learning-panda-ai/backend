class TestHealthEndpoints:
    def test_root_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_api_v1_health_returns_ok(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_content_type_is_json(self, client):
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]
