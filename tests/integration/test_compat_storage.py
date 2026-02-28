from __future__ import annotations


def _signup(client, email="compat@example.com"):
    return client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "StrongPass123",
            "confirmPassword": "StrongPass123",
            "role": "student",
        },
    )


def test_compat_cv_empty(client):
    res = client.get("/cv")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "file" in body


def test_compat_trend_seed_and_read(client):
    signup = _signup(client)
    assert signup.status_code == 200
    token = signup.json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    seed = client.post("/trends/seed", headers=headers, json={"days": 5, "replace": True})
    assert seed.status_code == 200, seed.text
    assert seed.json()["ok"] is True

    history = client.get("/trends/history")
    assert history.status_code == 200
    rows = history.json().get("history", [])
    assert isinstance(rows, list)
    assert len(rows) >= 2

    trends = client.get("/trends")
    assert trends.status_code == 200
    summary = trends.json()
    assert "skills" in summary
    assert "roles" in summary
