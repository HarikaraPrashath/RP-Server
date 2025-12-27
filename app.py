from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import subprocess
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PRO2_DIR = ROOT_DIR / "pro 2"
CV_EXTRACTOR_DIR = PRO2_DIR / "CV_extractor"
SCR_OUTPUT_DIR = PRO2_DIR / "scr_output" / "topjobs_ads"
STORAGE_DIR = BASE_DIR / "storage"
CV_STORAGE_DIR = STORAGE_DIR / "cvs"

PROFILE_PATH = STORAGE_DIR / "profile.json"
CV_INDEX_PATH = STORAGE_DIR / "cv_index.json"
LAST_QUERY_PATH = STORAGE_DIR / "last_query.json"

SCRAPER_PATH = CV_EXTRACTOR_DIR / "scrapper" / "TopJobs_scraper_t2.py"
PIPELINE_PATH = CV_EXTRACTOR_DIR / "job_skill_pipeline.py"
SKILLS_PATH = CV_EXTRACTOR_DIR / "skills.txt"

MAX_FILE_SIZE = 20 * 1024 * 1024

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
CV_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

sys.path.append(str(CV_EXTRACTOR_DIR))
try:
    from resume_pipeline import parse_resume  # type: ignore
except Exception as exc:  # pragma: no cover - import errors should surface on startup
    raise RuntimeError(f"Unable to import resume_pipeline from {CV_EXTRACTOR_DIR}") from exc

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


def _load_profile() -> dict[str, Any]:
    stored = _read_json(PROFILE_PATH, {})
    if not isinstance(stored, dict):
        stored = {}
    return _coerce_profile(stored)


def _save_profile(payload: dict[str, Any]) -> None:
    _write_json(PROFILE_PATH, payload)


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse")
async def parse_cv(file: UploadFile = File(...)) -> JSONResponse:
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
def get_profile() -> JSONResponse:
    return JSONResponse(_load_profile())


@app.put("/profile")
async def put_profile(payload: dict[str, Any]) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid profile payload.")
    stored = _coerce_profile(payload)
    _save_profile(stored)
    return JSONResponse({"ok": True})


@app.get("/jobs")
def get_jobs() -> JSONResponse:
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
async def refresh_jobs(payload: dict[str, Any] | None = None) -> JSONResponse:
  payload = payload or {}
    profile = _load_profile()
    keyword = str(payload.get("keyword") or profile.get("basics", {}).get("position") or "software engineer")
    user_skills = payload.get("userSkills")
    if not isinstance(user_skills, list):
        user_skills = profile.get("skills", [])
    user_skills = [str(skill).strip() for skill in user_skills if str(skill).strip()]
    force = bool(payload.get("force"))

    try:
        if _should_refresh(keyword, force):
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
                ],
                env=os.environ.copy(),
            )

            _write_json(
                LAST_QUERY_PATH,
                {"keyword": keyword, "ranAt": datetime.now(tz=timezone.utc).isoformat()},
            )
            return JSONResponse({"ok": True, "refreshed": True})

        return JSONResponse({"ok": True, "refreshed": False})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Job refresh failed: {exc}") from exc


@app.get("/ranked")
def get_ranked() -> JSONResponse:
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
