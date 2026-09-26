"""Shared test helpers: sign in with a password (the demo password by default), build clients."""
from app.seed import DEMO_PASSWORD


def signin(client, email: str, password: str = DEMO_PASSWORD) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


EMAILS = {
    "restaurant_staff": "staff@casa-demo.example.com",
    "restaurant_manager": "manager@casa-demo.example.com",
    "volunteer": "marcus@volunteer-demo.example.com",
    "org_staff": "staff@shelter-demo.example.com",
    "org_manager": "manager@shelter-demo.example.com",
    "admin": "admin@foodflow-demo.example.com",
}
