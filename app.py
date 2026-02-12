from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import hashlib
import secrets
import random

import subprocess
from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
CV_EXTRACTOR_DIR = BASE_DIR / "CV_extractor"
SCR_OUTPUT_DIR = BASE_DIR / "scr_output" / "topjobs_ads"
STORAGE_DIR = BASE_DIR / "storage"
CV_STORAGE_DIR = STORAGE_DIR / "cvs"
PROFILES_DIR = STORAGE_DIR / "profiles"
ANALYSIS_BACKEND_DIR = BASE_DIR / "analysis_pipeline"
ANALYSIS_OUTPUT_DIR = STORAGE_DIR / "analysis_output"

PROFILE_PATH = STORAGE_DIR / "profile.json"
CV_INDEX_PATH = STORAGE_DIR / "cv_index.json"
LAST_QUERY_PATH = STORAGE_DIR / "last_query.json"
USERS_PATH = STORAGE_DIR / "users.json"
TREND_HISTORY_PATH = STORAGE_DIR / "trends_history.json"

SCRAPER_PATH = CV_EXTRACTOR_DIR / "scrapper" / "TopJobs_scraper_t2.py"
PIPELINE_PATH = CV_EXTRACTOR_DIR / "job_skill_pipeline.py"
SKILLS_PATH = CV_EXTRACTOR_DIR / "skills.txt"

MAX_FILE_SIZE = 20 * 1024 * 1024
TREND_WINDOW_DAYS = 7
TREND_HISTORY_DAYS = 30
TREND_MIN_COUNT = 2
TREND_RISE_THRESHOLD = 0.3
TREND_DECLINE_THRESHOLD = 0.3

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
CV_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

sys.path.append(str(CV_EXTRACTOR_DIR))
if ANALYSIS_BACKEND_DIR.exists():
    sys.path.append(str(ANALYSIS_BACKEND_DIR))

app = FastAPI(title="RP-Server API")

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_skills() -> list[str]:
    if SKILLS_PATH.exists():
        lines = SKILLS_PATH.read_text(encoding="utf-8").splitlines()
        skills = [
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if skills:
            return skills
    return [
        "Python",
        "SQL",
        "Machine Learning",
        "Deep Learning",
        "NLP",
        "TensorFlow",
        "PyTorch",
        "Docker",
        "Kubernetes",
        "AWS",
        "FastAPI",
        "Django",
        "Flask",
        "Git",
        "Linux",
        "React",
        "Node.js",
        "Java",
        "C++",
    ]


SKILLS = _load_skills()


def _default_profile() -> dict[str, Any]:
    return {
        "basics": {
            "firstName": "",
            "lastName": "",
            "additionalName": "",
            "headline": "",
            "position": "",
            "industry": "",
            "school": "",
            "country": "",
            "city": "",
            "contactEmail": "",
            "showCurrentCompany": True,
            "showSchool": True,
        },
        "about": "",
        "experiences": [],
        "educationItems": [],
        "skills": [],
        "projects": [],
        "certifications": [],
        "recommendations": [],
    }


def _build_student_profile(profile: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = defaults or {}
    basics = profile.get("basics") if isinstance(profile.get("basics"), dict) else {}
    first = str(basics.get("firstName", "")).strip()
    last = str(basics.get("lastName", "")).strip()
    name = " ".join(part for part in [first, last] if part).strip()
    if not name:
        name = str(defaults.get("name", "")).strip() or "Student"

    skills = profile.get("skills", [])
    skills_list = (
        [str(skill).strip() for skill in skills if str(skill).strip()]
        if isinstance(skills, list)
        else []
    )
    if not skills_list:
        fallback_skills = defaults.get("technical_skills", [])
        if isinstance(fallback_skills, list):
            skills_list = [str(skill).strip() for skill in fallback_skills if str(skill).strip()]

    projects: list[Any] = []
    raw_projects = profile.get("projects", [])
    if isinstance(raw_projects, list):
        for item in raw_projects:
            if isinstance(item, dict):
                entry: dict[str, Any] = {}
                title = item.get("title") or item.get("name")
                description = item.get("description") or item.get("summary")
                technologies = item.get("technologies") or item.get("skills")
                if title:
                    entry["title"] = str(title)
                if description:
                    entry["description"] = str(description)
                if isinstance(technologies, list):
                    entry["technologies"] = [
                        str(tech).strip() for tech in technologies if str(tech).strip()
                    ]
                if entry:
                    projects.append(entry)
            elif isinstance(item, str):
                projects.append(item)
    if not projects:
        fallback_projects = defaults.get("projects", [])
        if isinstance(fallback_projects, list):
            projects = fallback_projects

    experience = profile.get("experiences", [])
    if not isinstance(experience, list) or not experience:
        fallback_experience = defaults.get("experience", [])
        experience = fallback_experience if isinstance(fallback_experience, list) else []

    certifications = profile.get("certifications", [])
    if not isinstance(certifications, list) or not certifications:
        fallback_certs = defaults.get("certifications", [])
        certifications = fallback_certs if isinstance(fallback_certs, list) else []

    soft_skills = defaults.get("soft_skills", [])
    if isinstance(soft_skills, list):
        soft_skills = [str(skill).strip() for skill in soft_skills if str(skill).strip()]
    else:
        soft_skills = []

    return {
        "name": name,
        "technical_skills": skills_list,
        "soft_skills": soft_skills,
        "certifications": certifications if isinstance(certifications, list) else [],
        "projects": projects,
        "experience": experience if isinstance(experience, list) else [],
    }


def _coerce_profile(payload: dict[str, Any]) -> dict[str, Any]:
    base = _default_profile()
    basics = payload.get("basics") if isinstance(payload.get("basics"), dict) else {}
    base["basics"].update(
        {
            "firstName": basics.get("firstName", ""),
            "lastName": basics.get("lastName", ""),
            "additionalName": basics.get("additionalName", ""),
            "headline": basics.get("headline", ""),
            "position": basics.get("position", ""),
            "industry": basics.get("industry", ""),
            "school": basics.get("school", ""),
            "country": basics.get("country", ""),
            "city": basics.get("city", ""),
            "contactEmail": basics.get("contactEmail", ""),
            "showCurrentCompany": bool(basics.get("showCurrentCompany", True)),
            "showSchool": bool(basics.get("showSchool", True)),
        }
    )

    for key in ["about", "experiences", "educationItems", "skills", "projects", "certifications", "recommendations"]:
        value = payload.get(key, base[key])
        if isinstance(base[key], list):
            base[key] = value if isinstance(value, list) else []
        elif isinstance(base[key], str):
            base[key] = value if isinstance(value, str) else ""

    return base


def _profile_path_for_email(email: str) -> Path:
    safe_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return PROFILES_DIR / f"{safe_key}.json"


def _load_profile_for_email(email: str) -> dict[str, Any]:
    path = _profile_path_for_email(email)
    stored = _read_json(path, {})
    if not isinstance(stored, dict):
        stored = {}
    profile = _coerce_profile(stored)
    if email and not profile.get("basics", {}).get("contactEmail"):
        profile["basics"]["contactEmail"] = email
    return profile


def _save_profile_for_email(email: str, payload: dict[str, Any]) -> None:
    path = _profile_path_for_email(email)
    _write_json(path, payload)


def _load_cv_index() -> list[dict[str, Any]]:
    data = _read_json(CV_INDEX_PATH, [])
    return data if isinstance(data, list) else []


def _save_cv_index(entries: list[dict[str, Any]]) -> None:
    _write_json(CV_INDEX_PATH, entries)


def _latest_cv_entry() -> dict[str, Any] | None:
    entries = _load_cv_index()
    if not entries:
        return None
    return sorted(entries, key=lambda item: item.get("uploadedAt", ""), reverse=True)[0]


def _safe_filename(name: str) -> str:
    return Path(name).name


def _python_run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=str(CV_EXTRACTOR_DIR),
        env=env or os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Command failed")


def _should_refresh(keyword: str, force: bool) -> bool:
    if force:
        return True
    if not (SCR_OUTPUT_DIR / "metadata.json").exists():
        return True
    if not (SCR_OUTPUT_DIR / "ranked_jobs.json").exists():
        return True

    info = _read_json(LAST_QUERY_PATH, {})
    last_keyword = str(info.get("keyword", "")).strip().lower()
    last_run_raw = info.get("ranAt")
    try:
        last_run = datetime.fromisoformat(last_run_raw)
    except Exception:
        last_run = datetime.fromtimestamp(0, tz=timezone.utc)

    age = datetime.now(tz=timezone.utc) - last_run
    if last_keyword != keyword.strip().lower():
        return True
    if age > timedelta(hours=3):
        return True
    return False


def _load_users() -> list[dict[str, Any]]:
    data = _read_json(USERS_PATH, [])
    return data if isinstance(data, list) else []


def _save_users(users: list[dict[str, Any]]) -> None:
    _write_json(USERS_PATH, users)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex()


def _find_user(email: str) -> dict[str, Any] | None:
    users = _load_users()
    normalized = _normalize_email(email)
    for user in users:
        if _normalize_email(str(user.get("email", ""))) == normalized:
            return user
    return None


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _find_user_by_token(token: str) -> dict[str, Any] | None:
    users = _load_users()
    for user in users:
        if str(user.get("token", "")) == token:
            return user
    return None


def _require_user(request: Request) -> dict[str, Any]:
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    user = _find_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return user


def _normalize_term(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _load_trend_history() -> list[dict[str, Any]]:
    data = _read_json(TREND_HISTORY_PATH, [])
    return data if isinstance(data, list) else []


def _save_trend_history(entries: list[dict[str, Any]]) -> None:
    _write_json(TREND_HISTORY_PATH, entries)


def _count_skills(ranked: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in ranked:
        skills = job.get("skills_found")
        if not isinstance(skills, list):
            continue
        for skill in skills:
            key = _normalize_term(str(skill))
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def _count_roles(metadata: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in metadata:
        position = job.get("position")
        if not isinstance(position, str):
            continue
        key = _normalize_term(position)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _record_trend_snapshot(keyword: str) -> None:
    metadata_path = SCR_OUTPUT_DIR / "metadata.json"
    ranked_path = SCR_OUTPUT_DIR / "ranked_jobs.json"
    if not metadata_path.exists() or not ranked_path.exists():
        return

    metadata = _read_json(metadata_path, [])
    ranked = _read_json(ranked_path, [])
    if not isinstance(metadata, list) or not isinstance(ranked, list):
        return

    now = datetime.now(tz=timezone.utc)
    snapshot = {
        "ranAt": now.isoformat(),
        "keyword": keyword,
        "jobCount": len(metadata),
        "skillCounts": _count_skills(ranked),
        "roleCounts": _count_roles(metadata),
    }

    history = _load_trend_history()
    history.append(snapshot)

    cutoff = now - timedelta(days=TREND_HISTORY_DAYS)
    pruned = []
    for entry in history:
        try:
            ran_at = datetime.fromisoformat(str(entry.get("ranAt")))
        except Exception:
            continue
        if ran_at >= cutoff:
            pruned.append(entry)

    _save_trend_history(pruned)


def _summarize_trends(history: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    window_cutoff = now - timedelta(days=TREND_WINDOW_DAYS)
    windowed: list[dict[str, Any]] = []
    for entry in history:
        try:
            ran_at = datetime.fromisoformat(str(entry.get("ranAt")))
        except Exception:
            continue
        if ran_at >= window_cutoff:
            windowed.append({**entry, "_ranAt": ran_at})

    if not windowed:
        return {
            "windowDays": TREND_WINDOW_DAYS,
            "snapshotCount": 0,
            "latestAt": None,
            "skills": {"emerging": [], "rising": [], "declining": [], "stable": []},
            "roles": {"emerging": [], "rising": [], "declining": [], "stable": []},
        }

    latest = max(windowed, key=lambda item: item["_ranAt"])
    baseline = [entry for entry in windowed if entry is not latest]

    def build_summary(key: str) -> dict[str, list[dict[str, Any]]]:
        current_counts = latest.get(key, {})
        if not isinstance(current_counts, dict):
            current_counts = {}

        baseline_counts: dict[str, list[int]] = {}
        for entry in baseline:
            counts = entry.get(key, {})
            if not isinstance(counts, dict):
                continue
            for term, count in counts.items():
                try:
                    count_value = int(count)
                except Exception:
                    continue
                baseline_counts.setdefault(term, []).append(count_value)

        all_terms = set(current_counts.keys()) | set(baseline_counts.keys())
        emerging: list[dict[str, Any]] = []
        rising: list[dict[str, Any]] = []
        declining: list[dict[str, Any]] = []
        stable: list[dict[str, Any]] = []

        for term in all_terms:
            try:
                current = int(current_counts.get(term, 0))
            except Exception:
                current = 0
            baseline_list = baseline_counts.get(term, [])
            baseline_avg = sum(baseline_list) / len(baseline_list) if baseline_list else 0

            if current < TREND_MIN_COUNT and baseline_avg < TREND_MIN_COUNT:
                continue

            if baseline_avg == 0 and current >= TREND_MIN_COUNT:
                emerging.append(
                    {"term": term, "current": current, "baseline": 0, "changePct": None}
                )
                continue

            if baseline_avg > 0:
                change_pct = (current - baseline_avg) / baseline_avg
                entry = {
                    "term": term,
                    "current": current,
                    "baseline": round(baseline_avg, 2),
                    "changePct": round(change_pct * 100, 1),
                }
                if change_pct >= TREND_RISE_THRESHOLD:
                    rising.append(entry)
                elif change_pct <= -TREND_DECLINE_THRESHOLD:
                    declining.append(entry)
                else:
                    stable.append(entry)

        emerging.sort(key=lambda item: item["current"], reverse=True)
        rising.sort(key=lambda item: item["changePct"] or 0, reverse=True)
        declining.sort(key=lambda item: item["changePct"] or 0)
        stable.sort(key=lambda item: item["current"], reverse=True)

        return {
            "emerging": emerging[:10],
            "rising": rising[:10],
            "declining": declining[:10],
            "stable": stable[:10],
        }

    return {
        "windowDays": TREND_WINDOW_DAYS,
        "snapshotCount": len(windowed),
        "latestAt": latest["_ranAt"].isoformat(),
        "skills": build_summary("skillCounts"),
        "roles": build_summary("roleCounts"),
    }


def _seed_trend_history(days: int, replace: bool) -> list[dict[str, Any]]:
    rng = random.Random(42)
    days = max(2, min(days, 30))
    now = datetime.now(tz=timezone.utc)

    skills_pool = [s.strip() for s in SKILLS if s.strip()]
    if len(skills_pool) < 8:
        skills_pool += ["AWS", "Docker", "React", "SQL", "Python", "Java"]
    roles_pool = [
        "data scientist",
        "ml engineer",
        "backend engineer",
        "frontend engineer",
        "devops engineer",
        "data analyst",
        "product analyst",
        "ai engineer",
    ]

    tracked_skills = rng.sample(skills_pool, k=min(8, len(skills_pool)))
    tracked_roles = rng.sample(roles_pool, k=6)
    emerging_skill = rng.choice(skills_pool)
    emerging_role = rng.choice(roles_pool)

    history: list[dict[str, Any]] = []
    for i in range(days):
        ran_at = now - timedelta(days=days - 1 - i)
        drift = (i - (days / 2)) / max(1, days / 2)

        skill_counts: dict[str, int] = {}
        for skill in tracked_skills:
            base = rng.randint(2, 8)
            count = max(1, int(base + drift * rng.randint(1, 4) + rng.randint(-1, 2)))
            skill_counts[_normalize_term(skill)] = count

        role_counts: dict[str, int] = {}
        for role in tracked_roles:
            base = rng.randint(2, 9)
            count = max(1, int(base + drift * rng.randint(1, 4) + rng.randint(-2, 2)))
            role_counts[_normalize_term(role)] = count

        if i >= days // 2:
            skill_counts[_normalize_term(emerging_skill)] = rng.randint(2, 6)
            role_counts[_normalize_term(emerging_role)] = rng.randint(2, 5)

        history.append(
            {
                "ranAt": ran_at.isoformat(),
                "keyword": "seed",
                "jobCount": rng.randint(30, 80),
                "skillCounts": skill_counts,
                "roleCounts": role_counts,
            }
        )

    if replace:
        return history
    existing = _load_trend_history()
    return existing + history


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse")
async def parse_cv(file: UploadFile = File(...)) -> JSONResponse:
    try:
        from resume_pipeline import parse_resume  # type: ignore
    except ModuleNotFoundError as exc:
        if exc.name == "paddle":
            raise HTTPException(
                status_code=500,
                detail="Missing dependency: paddle. Install paddlepaddle to enable OCR.",
            ) from exc
        raise HTTPException(
            status_code=500,
            detail="Resume parser dependency missing. Check server logs.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to load resume parser.",
        ) from exc
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max size is 20 MB.")

    content_type = file.content_type or ""
    if content_type and not (content_type == "application/pdf" or content_type.startswith("image/")):
        raise HTTPException(status_code=400, detail="Unsupported file type. Use a PDF or image.")

    suffix = Path(file.filename).suffix or ""
    if not suffix and content_type == "application/pdf":
        suffix = ".pdf"
    elif not suffix and content_type.startswith("image/"):
        suffix = f".{content_type.split('/')[-1]}"

    cv_id = uuid.uuid4().hex
    stored_name = f"{cv_id}{suffix or '.bin'}"
    stored_path = CV_STORAGE_DIR / stored_name
    stored_path.write_bytes(contents)

    parsed = parse_resume(str(stored_path), skills_list=SKILLS)

    entries = _load_cv_index()
    entry = {
        "id": cv_id,
        "path": str(stored_path),
        "originalName": file.filename,
        "size": len(contents),
        "contentType": content_type or "application/octet-stream",
        "uploadedAt": datetime.now(tz=timezone.utc).isoformat(),
    }
    entries.append(entry)
    _save_cv_index(entries)

    payload = {**parsed, "cvId": cv_id}
    return JSONResponse(payload)


@app.get("/cv")
def get_latest_cv() -> JSONResponse:
    entry = _latest_cv_entry()
    if not entry:
        return JSONResponse({"ok": True, "file": None})

    return JSONResponse(
        {
            "ok": True,
            "file": {
                "id": entry.get("id"),
                "originalName": entry.get("originalName", "cv_upload"),
                "size": entry.get("size", 0),
                "contentType": entry.get("contentType", "application/octet-stream"),
                "uploadedAt": entry.get("uploadedAt"),
                "viewUrl": f"/cv/file?id={entry.get('id')}",
            },
        }
    )


@app.get("/cv/file")
def get_cv_file(id: str) -> FileResponse:
    entries = _load_cv_index()
    entry = next((item for item in entries if item.get("id") == id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found.")

    path = Path(entry.get("path", ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(
        path,
        media_type=entry.get("contentType", "application/octet-stream"),
        filename=entry.get("originalName", path.name),
    )


@app.get("/profile")
def get_profile(request: Request) -> JSONResponse:
    user = _require_user(request)
    return JSONResponse(_load_profile_for_email(str(user.get("email", ""))))


@app.put("/profile")
async def put_profile(payload: dict[str, Any], request: Request) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid profile payload.")
    user = _require_user(request)
    stored = _coerce_profile(payload)
    _save_profile_for_email(str(user.get("email", "")), stored)
    return JSONResponse({"ok": True})


@app.post("/auth/signup")
async def signup(payload: dict[str, Any]) -> JSONResponse:
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))
    confirm_password = str(payload.get("confirmPassword", ""))

    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if confirm_password and confirm_password != password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if _find_user(email):
        raise HTTPException(status_code=409, detail="Account already exists.")

    salt = secrets.token_bytes(16)
    token = secrets.token_urlsafe(32)
    user = {
        "email": _normalize_email(email),
        "passwordSalt": salt.hex(),
        "passwordHash": _hash_password(password, salt),
        "token": token,
        "createdAt": datetime.now(tz=timezone.utc).isoformat(),
    }
    users = _load_users()
    users.append(user)
    _save_users(users)

    return JSONResponse(
        {"ok": True, "user": {"email": user["email"]}, "token": token}
    )


@app.post("/auth/login")
async def login(payload: dict[str, Any]) -> JSONResponse:
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))

    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required.")

    users = _load_users()
    normalized = _normalize_email(email)
    user_index = next(
        (idx for idx, item in enumerate(users) if _normalize_email(str(item.get("email", ""))) == normalized),
        None,
    )
    if user_index is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user = users[user_index]
    salt_hex = str(user.get("passwordSalt", ""))
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        raise HTTPException(status_code=500, detail="Corrupt user record.")

    expected = str(user.get("passwordHash", ""))
    provided = _hash_password(password, salt)
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = secrets.token_urlsafe(32)
    user["token"] = token
    users[user_index] = user
    _save_users(users)

    return JSONResponse(
        {"ok": True, "user": {"email": user.get("email", "")}, "token": token}
    )


@app.post("/auth/forgot-password")
async def forgot_password(payload: dict[str, Any]) -> JSONResponse:
    email = str(payload.get("email", "")).strip()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    # Placeholder flow: do not reveal whether the email exists.
    return JSONResponse({"ok": True, "message": "Check your inbox for a reset link."})


@app.get("/jobs")
def get_jobs() -> JSONResponse:
    print("[jobs] fetch metadata")
    metadata_path = SCR_OUTPUT_DIR / "metadata.json"
    if not metadata_path.exists():
        return JSONResponse({"jobs": []})

    data = _read_json(metadata_path, [])
    jobs = []
    if isinstance(data, list):
        for job in data:
            files = job.get("files") if isinstance(job, dict) else []
            files = files if isinstance(files, list) else []
            text_file = next((f for f in files if str(f).lower().endswith(".txt")), None)
            image_file = next(
                (f for f in files if str(f).lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))),
                None,
            )
            snippet = ""
            if text_file:
                try:
                    text = (SCR_OUTPUT_DIR / _safe_filename(text_file)).read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    text = " ".join(text.split())
                    snippet = text[:300] + ("..." if len(text) > 300 else "")
                except Exception:
                    snippet = ""

            jobs.append(
                {
                    "ref": job.get("ref") if isinstance(job, dict) else "",
                    "position": job.get("position") if isinstance(job, dict) else "",
                    "employer": job.get("employer") if isinstance(job, dict) else "",
                    "url": job.get("url") if isinstance(job, dict) else "",
                    "type": job.get("type") if isinstance(job, dict) else None,
                    "files": files,
                    "textSnippet": snippet,
                    "imageFile": image_file,
                }
            )

    return JSONResponse({"jobs": jobs})


@app.get("/jobs/file")
def get_job_file(name: str) -> FileResponse:
    safe_name = _safe_filename(name)
    file_path = SCR_OUTPUT_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(file_path)


@app.post("/jobs/refresh")
async def refresh_jobs(request: Request, payload: dict[str, Any] | None = None) -> JSONResponse:
    payload = payload or {}
    profile = _default_profile()
    token = _extract_bearer_token(request)
    if token:
        user = _find_user_by_token(token)
        if user:
            profile = _load_profile_for_email(str(user.get("email", "")))
    keyword = str(
        payload.get("keyword")
        or profile.get("basics", {}).get("position")
        or "software engineer"
    )
    user_skills = payload.get("userSkills")
    if not isinstance(user_skills, list):
        user_skills = profile.get("skills", [])
    user_skills = [str(skill).strip() for skill in user_skills if str(skill).strip()]
    force = bool(payload.get("force"))
    enable_ocr = bool(payload.get("enableOcr"))
    if not enable_ocr:
        enable_ocr = str(os.environ.get("ENABLE_JOB_OCR", "1")).lower() in ("1", "true", "yes")

    try:
        print(f"[jobs/refresh] keyword='{keyword}' skills={len(user_skills)} force={force} ocr={enable_ocr}")
        if _should_refresh(keyword, force):
            print("[jobs/refresh] running scraper + pipeline")
            env = os.environ.copy()
            env["TOPJOBS_KEYWORD"] = keyword
            _python_run([sys.executable, str(SCRAPER_PATH)], env=env)
            _python_run(
                [
                    sys.executable,
                    str(PIPELINE_PATH),
                    "--scraped_folder",
                    str(SCR_OUTPUT_DIR),
                    "--user_skills",
                    ",".join(user_skills),
                    "--out_json",
                    "ranked_jobs.json",
                ]
                + (["--enable_ocr"] if enable_ocr else []),
                env=os.environ.copy(),
            )

            _write_json(
                LAST_QUERY_PATH,
                {"keyword": keyword, "ranAt": datetime.now(tz=timezone.utc).isoformat()},
            )
            try:
                _record_trend_snapshot(keyword)
            except Exception:
                pass
            print("[jobs/refresh] refresh complete")
            return JSONResponse({"ok": True, "refreshed": True})

        print("[jobs/refresh] using cached results")
        return JSONResponse({"ok": True, "refreshed": False})
    except Exception as exc:
        print(f"[jobs/refresh] failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Job refresh failed: {exc}") from exc


@app.get("/trends/history")
def get_trend_history() -> JSONResponse:
    history = _load_trend_history()
    return JSONResponse({"history": history})


@app.get("/trends")
def get_trends() -> JSONResponse:
    history = _load_trend_history()
    summary = _summarize_trends(history)
    return JSONResponse(summary)


@app.post("/trends/seed")
async def seed_trends(payload: dict[str, Any] | None = None) -> JSONResponse:
    payload = payload or {}
    days = payload.get("days", TREND_WINDOW_DAYS)
    replace = bool(payload.get("replace", True))
    try:
        days_int = int(days)
    except Exception:
        days_int = TREND_WINDOW_DAYS

    history = _seed_trend_history(days_int, replace)
    _save_trend_history(history)
    summary = _summarize_trends(history)
    return JSONResponse({"ok": True, "summary": summary})


@app.get("/ranked")
def get_ranked() -> JSONResponse:
    print("[ranked] fetch ranked list")
    ranked_path = SCR_OUTPUT_DIR / "ranked_jobs.json"
    if not ranked_path.exists():
        return JSONResponse({"ranked": []})
    data = _read_json(ranked_path, [])
    ranked = data if isinstance(data, list) else []
    return JSONResponse({"ranked": ranked})


@app.get("/ranked/summary")
def get_ranked_summary() -> JSONResponse:
    ranked_path = SCR_OUTPUT_DIR / "ranked_jobs.json"
    if not ranked_path.exists():
        return JSONResponse({"best": None, "top": []})
    data = _read_json(ranked_path, [])
    ranked = data if isinstance(data, list) else []
    if not ranked:
        return JSONResponse({"best": None, "top": []})

    sorted_jobs = sorted(ranked, key=lambda j: j.get("match_percent", 0), reverse=True)
    best = sorted_jobs[0]
    filtered = [j for j in sorted_jobs if j.get("match_percent", 0) > 0]
    top = filtered[:5]
    return JSONResponse(
        {
            "best": {
                "ref": best.get("ref", ""),
                "position": best.get("position", ""),
                "employer": best.get("employer", ""),
                "url": best.get("url", ""),
                "match_percent": round(best.get("match_percent", 0)),
            },
            "top": [
                {
                    "ref": job.get("ref", ""),
                    "position": job.get("position", ""),
                    "employer": job.get("employer", ""),
                    "url": job.get("url", ""),
                    "match_percent": round(job.get("match_percent", 0)),
                }
                for job in top
            ],
        }
    )


@app.post("/analyse")
async def analyse(request: Request, payload: dict[str, Any] | None = None) -> JSONResponse:
    payload = payload or {}
    keyword = str(payload.get("keyword", "")).strip()

    try:
        from Job_Analysis_and_Skill_Gap import run_analysis, STUDENT_PROFILE  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Analysis pipeline not available. Check server dependencies.",
        ) from exc

    student_profile: dict[str, Any] = STUDENT_PROFILE
    profile_source: dict[str, Any] | None = None
    override = payload.get("profile")
    if isinstance(override, dict):
        profile_source = override
        student_profile = _build_student_profile(profile_source, defaults=STUDENT_PROFILE)
    else:
        token = _extract_bearer_token(request)
        if token:
            user = _find_user_by_token(token)
            if user:
                profile_source = _load_profile_for_email(str(user.get("email", "")))
                student_profile = _build_student_profile(profile_source, defaults=STUDENT_PROFILE)

    if not keyword:
        basics = profile_source.get("basics") if isinstance(profile_source, dict) else {}
        keyword = str(basics.get("position", "")).strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required.")

    run_folder = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = ANALYSIS_OUTPUT_DIR / run_folder
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = await asyncio.to_thread(
            run_analysis,
            keyword,
            student_profile,
            str(output_dir),
            False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(result)
