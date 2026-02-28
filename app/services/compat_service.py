from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.engines.nlp.preprocess import normalize_text as nlp_normalize_text
from app.engines.scraper import CrawlerPolicy, deduplicate_metadata
from app.repositories import CvRepository, StateRepository, TrendRepository
from app.services.profile_service import ProfileService
from app.workers.job_queue import queue

BASE_DIR = Path(__file__).resolve().parents[2]
CV_EXTRACTOR_DIR = BASE_DIR / "CV_extractor"
SCR_OUTPUT_DIR = BASE_DIR / "scr_output" / "topjobs_ads"
STORAGE_DIR = BASE_DIR / "storage"
CV_STORAGE_DIR = STORAGE_DIR / "cvs"
ANALYSIS_BACKEND_DIR = BASE_DIR / "analysis_pipeline"
ANALYSIS_OUTPUT_DIR = STORAGE_DIR / "analysis_output"
CV_INDEX_PATH = STORAGE_DIR / "cv_index.json"
LAST_QUERY_PATH = STORAGE_DIR / "last_query.json"
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

if str(CV_EXTRACTOR_DIR) not in sys.path:
    sys.path.append(str(CV_EXTRACTOR_DIR))
if ANALYSIS_BACKEND_DIR.exists() and str(ANALYSIS_BACKEND_DIR) not in sys.path:
    sys.path.append(str(ANALYSIS_BACKEND_DIR))


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


def _safe_filename(name: str) -> str:
    return Path(name).name


def _load_skills() -> list[str]:
    if SKILLS_PATH.exists():
        lines = SKILLS_PATH.read_text(encoding="utf-8").splitlines()
        skills = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
        if skills:
            return skills
    return ["Python", "SQL", "Machine Learning", "FastAPI", "React", "Java", "Git", "Linux"]


SKILLS = _load_skills()


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


def _normalize_term(value: str) -> str:
    return " ".join(nlp_normalize_text(value).split())


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def _build_student_profile(profile: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = defaults or {}
    basics = profile.get("basics") if isinstance(profile.get("basics"), dict) else {}
    first = str(basics.get("firstName", "")).strip()
    last = str(basics.get("lastName", "")).strip()
    name = " ".join(part for part in [first, last] if part).strip()
    if not name:
        name = str(defaults.get("name", "")).strip() or "Student"

    skills = profile.get("skills", [])
    skills_list = [str(skill).strip() for skill in skills if str(skill).strip()] if isinstance(skills, list) else []
    if not skills_list:
        fallback = defaults.get("technical_skills", [])
        if isinstance(fallback, list):
            skills_list = [str(skill).strip() for skill in fallback if str(skill).strip()]

    projects = profile.get("projects", [])
    if not isinstance(projects, list):
        projects = []

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


class CompatibilityService:
    def _load_cv_index(self, db: Session | None = None) -> list[dict[str, Any]]:
        if settings.use_db_compat_storage and db is not None:
            latest = CvRepository(db).latest()
            if latest is None:
                return []
            return [
                {
                    "id": latest.id,
                    "path": latest.storage_path,
                    "originalName": latest.original_name,
                    "size": latest.size,
                    "contentType": latest.content_type,
                    "uploadedAt": latest.uploaded_at.isoformat(),
                }
            ]
        data = _read_json(CV_INDEX_PATH, [])
        return data if isinstance(data, list) else []

    def _save_cv_entry(self, entry: dict[str, Any], db: Session | None = None, user_id: str | None = None) -> None:
        if settings.use_db_compat_storage and db is not None:
            CvRepository(db).create(
                file_id=str(entry.get("id")),
                user_id=user_id,
                original_name=str(entry.get("originalName", "cv_upload")),
                content_type=str(entry.get("contentType", "application/octet-stream")),
                size=int(entry.get("size", 0)),
                storage_path=Path(str(entry.get("path", ""))),
                uploaded_at=datetime.fromisoformat(str(entry.get("uploadedAt"))),
            )
            db.commit()
            return
        entries = self._load_cv_index()
        entries.append(entry)
        _write_json(CV_INDEX_PATH, entries)

    def _latest_cv_entry(self, db: Session | None = None, user_id: str | None = None) -> dict[str, Any] | None:
        if settings.use_db_compat_storage and db is not None:
            row = CvRepository(db).latest(user_id=user_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "path": row.storage_path,
                "originalName": row.original_name,
                "size": row.size,
                "contentType": row.content_type,
                "uploadedAt": row.uploaded_at.isoformat(),
            }
        entries = self._load_cv_index()
        if not entries:
            return None
        return sorted(entries, key=lambda item: item.get("uploadedAt", ""), reverse=True)[0]

    def _get_last_query(self, db: Session | None = None) -> dict[str, Any]:
        if settings.use_db_compat_storage and db is not None:
            value = StateRepository(db).get("last_query")
            return value if isinstance(value, dict) else {}
        info = _read_json(LAST_QUERY_PATH, {})
        return info if isinstance(info, dict) else {}

    def _set_last_query(self, value: dict[str, Any], db: Session | None = None) -> None:
        if settings.use_db_compat_storage and db is not None:
            StateRepository(db).upsert("last_query", value)
            db.commit()
            return
        _write_json(LAST_QUERY_PATH, value)

    def _load_trend_history(self, db: Session | None = None) -> list[dict[str, Any]]:
        if settings.use_db_compat_storage and db is not None:
            rows = TrendRepository(db).list_history()
            return [
                {
                    "ranAt": row.ran_at.isoformat(),
                    "keyword": row.keyword,
                    "jobCount": row.job_count,
                    "skillCounts": row.skill_counts,
                    "roleCounts": row.role_counts,
                }
                for row in rows
            ]
        data = _read_json(TREND_HISTORY_PATH, [])
        return data if isinstance(data, list) else []

    def _save_trend_history(self, entries: list[dict[str, Any]], db: Session | None = None) -> None:
        if settings.use_db_compat_storage and db is not None:
            repo = TrendRepository(db)
            normalized = []
            for item in entries:
                try:
                    ran_at = datetime.fromisoformat(str(item.get("ranAt")))
                except Exception:
                    continue
                normalized.append(
                    {
                        "ran_at": ran_at,
                        "keyword": str(item.get("keyword", "")),
                        "job_count": int(item.get("jobCount", 0)),
                        "skill_counts": item.get("skillCounts", {}) if isinstance(item.get("skillCounts", {}), dict) else {},
                        "role_counts": item.get("roleCounts", {}) if isinstance(item.get("roleCounts", {}), dict) else {},
                    }
                )
            repo.replace_history(normalized)
            db.commit()
            return
        _write_json(TREND_HISTORY_PATH, entries)

    def _should_refresh(self, keyword: str, force: bool, db: Session | None = None) -> bool:
        if force:
            return True
        if not (SCR_OUTPUT_DIR / "metadata.json").exists():
            return True
        if not (SCR_OUTPUT_DIR / "ranked_jobs.json").exists():
            return True

        info = self._get_last_query(db)
        last_keyword = str(info.get("keyword", "")).strip().lower()
        last_run_raw = info.get("ranAt")
        try:
            last_run = _as_utc(datetime.fromisoformat(str(last_run_raw)))
        except Exception:
            last_run = datetime.fromtimestamp(0, tz=timezone.utc)

        age = datetime.now(tz=timezone.utc) - last_run
        if last_keyword != keyword.strip().lower():
            return True
        if age > timedelta(hours=3):
            return True
        return False

    def _record_trend_snapshot(self, keyword: str, db: Session | None = None) -> None:
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

        history = self._load_trend_history(db)
        history.append(snapshot)
        cutoff = now - timedelta(days=TREND_HISTORY_DAYS)
        pruned = []
        for entry in history:
            try:
                ran_at = _as_utc(datetime.fromisoformat(str(entry.get("ranAt"))))
            except Exception:
                continue
            if ran_at >= cutoff:
                pruned.append(entry)
        self._save_trend_history(pruned, db)

    def _summarize_trends(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        now = datetime.now(tz=timezone.utc)
        window_cutoff = now - timedelta(days=TREND_WINDOW_DAYS)
        windowed: list[dict[str, Any]] = []
        for entry in history:
            try:
                ran_at = _as_utc(datetime.fromisoformat(str(entry.get("ranAt"))))
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
                    emerging.append({"term": term, "current": current, "baseline": 0, "changePct": None})
                    continue
                if baseline_avg > 0:
                    change_pct = (current - baseline_avg) / baseline_avg
                    entry = {"term": term, "current": current, "baseline": round(baseline_avg, 2), "changePct": round(change_pct * 100, 1)}
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
            return {"emerging": emerging[:10], "rising": rising[:10], "declining": declining[:10], "stable": stable[:10]}

        return {
            "windowDays": TREND_WINDOW_DAYS,
            "snapshotCount": len(windowed),
            "latestAt": latest["_ranAt"].isoformat(),
            "skills": build_summary("skillCounts"),
            "roles": build_summary("roleCounts"),
        }

    def _seed_trend_history(self, days: int, replace: bool, db: Session | None = None) -> list[dict[str, Any]]:
        import random
        rng = random.Random(42)
        days = max(2, min(days, 30))
        now = datetime.now(tz=timezone.utc)
        skills_pool = [s.strip() for s in SKILLS if s.strip()]
        if len(skills_pool) < 8:
            skills_pool += ["AWS", "Docker", "React", "SQL", "Python", "Java"]
        roles_pool = ["data scientist", "ml engineer", "backend engineer", "frontend engineer", "devops engineer", "data analyst", "product analyst", "ai engineer"]
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
            history.append({"ranAt": ran_at.isoformat(), "keyword": "seed", "jobCount": rng.randint(30, 80), "skillCounts": skill_counts, "roleCounts": role_counts})
        if not replace:
            history = self._load_trend_history(db) + history
        self._save_trend_history(history, db)
        return history

    async def parse_cv(self, file: UploadFile, db: Session | None = None, user_id: str | None = None) -> dict[str, Any]:
        try:
            from resume_pipeline import parse_resume  # type: ignore
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Resume parser unavailable: {exc}") from exc
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
        entry = {
            "id": cv_id,
            "path": str(stored_path),
            "originalName": file.filename,
            "size": len(contents),
            "contentType": content_type or "application/octet-stream",
            "uploadedAt": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save_cv_entry(entry, db=db, user_id=user_id)
        return {**parsed, "cvId": cv_id}

    def get_latest_cv(self, db: Session | None = None, user_id: str | None = None) -> dict[str, Any]:
        entry = self._latest_cv_entry(db=db, user_id=user_id)
        if not entry:
            return {"ok": True, "file": None}
        return {"ok": True, "file": {"id": entry.get("id"), "originalName": entry.get("originalName", "cv_upload"), "size": entry.get("size", 0), "contentType": entry.get("contentType", "application/octet-stream"), "uploadedAt": entry.get("uploadedAt"), "viewUrl": f"/cv/file?id={entry.get('id')}"}}

    def get_cv_file_response(self, file_id: str, db: Session | None = None) -> FileResponse:
        if settings.use_db_compat_storage and db is not None:
            row = CvRepository(db).get_by_id(file_id)
            if row is None:
                raise HTTPException(status_code=404, detail="File not found.")
            path = Path(row.storage_path)
            if not path.exists():
                raise HTTPException(status_code=404, detail="File not found.")
            return FileResponse(path, media_type=row.content_type, filename=row.original_name)
        entries = self._load_cv_index()
        entry = next((item for item in entries if item.get("id") == file_id), None)
        if not entry:
            raise HTTPException(status_code=404, detail="File not found.")
        path = Path(entry.get("path", ""))
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(path, media_type=entry.get("contentType", "application/octet-stream"), filename=entry.get("originalName", path.name))

    def get_jobs(self) -> dict[str, Any]:
        metadata_path = SCR_OUTPUT_DIR / "metadata.json"
        if not metadata_path.exists():
            return {"jobs": []}
        data = _read_json(metadata_path, [])
        jobs = []
        if isinstance(data, list):
            for job in data:
                files = job.get("files") if isinstance(job, dict) else []
                files = files if isinstance(files, list) else []
                text_file = next((f for f in files if str(f).lower().endswith(".txt")), None)
                image_file = next((f for f in files if str(f).lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))), None)
                snippet = ""
                if text_file:
                    try:
                        text = (SCR_OUTPUT_DIR / _safe_filename(text_file)).read_text(encoding="utf-8", errors="ignore")
                        text = " ".join(text.split())
                        snippet = text[:300] + ("..." if len(text) > 300 else "")
                    except Exception:
                        snippet = ""
                jobs.append({"ref": job.get("ref") if isinstance(job, dict) else "", "position": job.get("position") if isinstance(job, dict) else "", "employer": job.get("employer") if isinstance(job, dict) else "", "url": job.get("url") if isinstance(job, dict) else "", "type": job.get("type") if isinstance(job, dict) else None, "files": files, "textSnippet": snippet, "imageFile": image_file})
        return {"jobs": jobs}

    def get_job_file_response(self, name: str) -> FileResponse:
        safe_name = _safe_filename(name)
        file_path = SCR_OUTPUT_DIR / safe_name
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(file_path)

    def _apply_dedup_to_metadata(self) -> dict[str, Any]:
        metadata_path = SCR_OUTPUT_DIR / "metadata.json"
        rows = _read_json(metadata_path, [])
        if not isinstance(rows, list):
            return {"dedupDropped": 0, "dedupKept": 0}
        result = deduplicate_metadata(rows)
        _write_json(metadata_path, result.kept)
        return {"dedupDropped": result.dropped, "dedupKept": len(result.kept)}

    def _run_refresh_pipeline(self, keyword: str, user_skills: list[str], enable_ocr: bool, db: Session | None) -> dict[str, Any]:
        local_db = db
        created_local_db = False
        if local_db is None and settings.use_db_compat_storage:
            local_db = SessionLocal()
            created_local_db = True
        env = os.environ.copy()
        env["TOPJOBS_KEYWORD"] = keyword
        _python_run([sys.executable, str(SCRAPER_PATH)], env=env)
        dedup_stats = self._apply_dedup_to_metadata()
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
        self._set_last_query({"keyword": keyword, "ranAt": datetime.now(tz=timezone.utc).isoformat()}, local_db)
        try:
            self._record_trend_snapshot(keyword, local_db)
        except Exception:
            pass
        finally:
            if created_local_db and local_db is not None:
                local_db.close()
        return {"ok": True, "refreshed": True, **dedup_stats}

    def refresh_jobs(self, payload: dict[str, Any], profile_payload: dict[str, Any] | None, db: Session | None = None) -> dict[str, Any]:
        payload = payload or {}
        profile_payload = profile_payload or {}
        keyword = str(payload.get("keyword") or profile_payload.get("basics", {}).get("position") or "software engineer")
        user_skills = payload.get("userSkills")
        if not isinstance(user_skills, list):
            user_skills = profile_payload.get("skills", [])
        user_skills = [str(skill).strip() for skill in user_skills if str(skill).strip()]
        force = bool(payload.get("force"))
        enable_ocr = bool(payload.get("enableOcr"))
        background = bool(payload.get("background", settings.jobs_refresh_background_default))
        if not enable_ocr:
            enable_ocr = str(os.environ.get("ENABLE_JOB_OCR", "1")).lower() in ("1", "true", "yes")
        policy = CrawlerPolicy(min_interval_seconds=settings.crawler_min_interval_seconds)
        robots_check = policy.allow_by_robots("https://www.topjobs.lk", "/")
        if not robots_check.allowed:
            raise HTTPException(status_code=400, detail=f"Crawler blocked by robots policy: {robots_check.reason}")
        last_query = self._get_last_query(db)
        interval_check = policy.allow_by_interval(last_query.get("ranAt") if isinstance(last_query, dict) else None)
        if not interval_check.allowed and not force:
            return {"ok": True, "refreshed": False, "policyBlocked": True, "reason": interval_check.reason}
        try:
            if self._should_refresh(keyword, force, db):
                if background:
                    job_id = queue.submit(self._run_refresh_pipeline, keyword, user_skills, enable_ocr, None)
                    return {"ok": True, "refreshed": False, "queued": True, "jobId": job_id}
                return self._run_refresh_pipeline(keyword, user_skills, enable_ocr, db)
            return {"ok": True, "refreshed": False}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Job refresh failed: {exc}") from exc

    def refresh_status(self, job_id: str) -> dict[str, Any]:
        status = queue.status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {"ok": True, "jobId": job_id, **status}

    def get_ranked(self) -> dict[str, Any]:
        ranked_path = SCR_OUTPUT_DIR / "ranked_jobs.json"
        if not ranked_path.exists():
            return {"ranked": []}
        data = _read_json(ranked_path, [])
        return {"ranked": data if isinstance(data, list) else []}

    def get_ranked_summary(self) -> dict[str, Any]:
        ranked_path = SCR_OUTPUT_DIR / "ranked_jobs.json"
        if not ranked_path.exists():
            return {"best": None, "top": []}
        data = _read_json(ranked_path, [])
        ranked = data if isinstance(data, list) else []
        if not ranked:
            return {"best": None, "top": []}
        sorted_jobs = sorted(ranked, key=lambda j: j.get("match_percent", 0), reverse=True)
        best = sorted_jobs[0]
        top = [j for j in sorted_jobs if j.get("match_percent", 0) > 0][:5]
        return {
            "best": {"ref": best.get("ref", ""), "position": best.get("position", ""), "employer": best.get("employer", ""), "url": best.get("url", ""), "match_percent": round(best.get("match_percent", 0))},
            "top": [{"ref": job.get("ref", ""), "position": job.get("position", ""), "employer": job.get("employer", ""), "url": job.get("url", ""), "match_percent": round(job.get("match_percent", 0))} for job in top],
        }

    def get_trend_history(self, db: Session | None = None) -> dict[str, Any]:
        return {"history": self._load_trend_history(db)}

    def get_trends(self, db: Session | None = None) -> dict[str, Any]:
        return self._summarize_trends(self._load_trend_history(db))

    def seed_trends(self, payload: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
        payload = payload or {}
        try:
            days_int = int(payload.get("days", TREND_WINDOW_DAYS))
        except Exception:
            days_int = TREND_WINDOW_DAYS
        history = self._seed_trend_history(days_int, bool(payload.get("replace", True)), db)
        return {"ok": True, "summary": self._summarize_trends(history)}

    async def analyse(self, payload: dict[str, Any], profile_payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = payload or {}
        profile_payload = profile_payload or {}
        keyword = str(payload.get("keyword", "")).strip()
        try:
            from Job_Analysis_and_Skill_Gap import run_analysis, STUDENT_PROFILE  # type: ignore
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Analysis pipeline not available.") from exc
        student_profile = _build_student_profile(profile_payload, defaults=STUDENT_PROFILE)
        if not keyword:
            basics = profile_payload.get("basics") if isinstance(profile_payload, dict) else {}
            keyword = str(basics.get("position", "")).strip()
        if not keyword:
            raise HTTPException(status_code=400, detail="Keyword is required.")
        run_folder = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = ANALYSIS_OUTPUT_DIR / run_folder
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            return await asyncio.to_thread(run_analysis, keyword, student_profile, str(output_dir), False)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


def load_profile_payload(db: Session, user) -> dict[str, Any] | None:
    if user is None:
        return None
    return ProfileService(db).get_profile(user.id, user.email)
