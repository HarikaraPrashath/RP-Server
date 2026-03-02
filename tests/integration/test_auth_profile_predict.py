from __future__ import annotations


def _signup(client, email="student@example.com", role="student"):
    return client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "StrongPass123",
            "confirmPassword": "StrongPass123",
            "role": role,
        },
    )


def test_auth_profile_predict_flow(client):
    signup = _signup(client)
    assert signup.status_code == 200, signup.text
    signup_body = signup.json()
    assert "accessToken" in signup_body
    assert "refreshToken" in signup_body

    login = client.post("/auth/login", json={"email": "student@example.com", "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    login_body = login.json()

    refresh = client.post("/auth/refresh", json={"refreshToken": login_body["refreshToken"]})
    assert refresh.status_code == 200, refresh.text
    refresh_body = refresh.json()

    headers = {"Authorization": f"Bearer {refresh_body['accessToken']}"}

    profile_put = client.put(
        "/profile",
        headers=headers,
        json={
            "basics": {"firstName": "Test", "lastName": "User", "position": "software engineer"},
            "about": "About me",
            "skills": ["Python", "FastAPI"],
            "experiences": [],
            "educationItems": [],
            "projects": [],
            "certifications": [],
            "recommendations": [],
        },
    )
    assert profile_put.status_code == 200, profile_put.text

    profile_get = client.get("/profile", headers=headers)
    assert profile_get.status_code == 200, profile_get.text
    profile_body = profile_get.json()
    assert profile_body["basics"]["firstName"] == "Test"

    predict = client.post("/predict", headers=headers, json={"keyword": "software", "topK": 3})
    assert predict.status_code == 200, predict.text
    predict_body = predict.json()
    assert "recommendedRoles" in predict_body
    assert "generatedAt" in predict_body

    forgot = client.post("/auth/forgot-password", json={"email": "student@example.com"})
    assert forgot.status_code == 200, forgot.text
    forgot_body = forgot.json()
    assert forgot_body["ok"] is True
    assert "resetToken" in forgot_body

    reset = client.post(
        "/auth/reset-password",
        json={
            "token": forgot_body["resetToken"],
            "newPassword": "NewStrongPass123",
            "confirmPassword": "NewStrongPass123",
        },
    )
    assert reset.status_code == 200, reset.text

    relogin = client.post("/auth/login", json={"email": "student@example.com", "password": "NewStrongPass123"})
    assert relogin.status_code == 200, relogin.text


def test_logout_revokes_refresh_token(client):
    signup = _signup(client, email="revoke@example.com")
    body = signup.json()
    headers = {"Authorization": f"Bearer {body['accessToken']}"}

    logout = client.post("/auth/logout", headers=headers, json={"refreshToken": body["refreshToken"]})
    assert logout.status_code == 200, logout.text
    assert logout.json()["ok"] is True

    refresh = client.post("/auth/refresh", json={"refreshToken": body["refreshToken"]})
    assert refresh.status_code == 401
