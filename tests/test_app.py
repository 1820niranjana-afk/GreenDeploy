import app


def test_home_page():
    client = app.app.test_client()
    response = client.get("/")
    assert response.status_code == 200


def test_module1_page():
    client = app.app.test_client()
    response = client.get("/module1")
    assert response.status_code == 200


def test_module2_page():
    client = app.app.test_client()
    response = client.get("/module2")
    assert response.status_code == 200


def test_health_api():
    client = app.app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json["status"] == "Running"