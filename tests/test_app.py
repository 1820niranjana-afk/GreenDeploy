
from app import app

def test_dashboard():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200

def test_module1():
    client = app.test_client()
    response = client.get("/module1")
    assert response.status_code == 200

def test_metrics_api():
    client = app.test_client()
    response = client.get("/api/metrics")

    assert response.status_code == 200

    data = response.get_json()

    assert "cpu" in data
    assert "ram" in data
    assert "ram_used" in data
    assert "ram_total" in data
