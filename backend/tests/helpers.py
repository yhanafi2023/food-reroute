"""Shared test helpers: sign in with the demo code, build clients."""
from app.seed import DEMO_CODE


def signin(client, email: str) -> dict:
    r = client.post("/auth/verify", json={"email": email, "code": DEMO_CODE})
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
