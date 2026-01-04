# Parse TopJobs-scraped ads (text + image OCR optional), extract skills, and compute skill match + gaps.

from __future__ import annotations
import os
import re
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

from skill_config import EXTRA_SIGNALS, SECTION_HEADERS, SKILL_LEXICON

# ---------------------------
# Config: Skill dictionary
# ---------------------------

# Loaded from skill_config.py

# ---------------------------
# Optional OCR (only if you want)
# ---------------------------

def ocr_image_to_text(image_path: str) -> Optional[str]:
    """
    Optional: OCR image-based ads to text using pytesseract.
    If pytesseract isn't installed/configured, return None.
    """
    try:
        from PIL import Image
        import pytesseract  # pip install pytesseract
    except Exception:
        return None

    try:
        tess_cmd = os.environ.get("TESSERACT_CMD")
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd
        else:
            default_tess = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(default_tess):
                pytesseract.pytesseract.tesseract_cmd = default_tess
        img = Image.open(image_path)
        # You can tweak config for better results:
        return pytesseract.image_to_string(img, lang="eng")
    except Exception:
        return None


# ---------------------------
# Helpers
# ---------------------------

def normalize_text(s: str) -> str:
    s = s.lower()
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[^\w\s\.\+\-/]", " ", s)  # keep . + - /
    s = re.sub(r"\s+", " ", s).strip()
    return s

def find_skills(text: str) -> List[str]:
    t = normalize_text(text)
    found = set()

    # Exact-ish phrase matching for aliases
    for skill, aliases in SKILL_LEXICON.items():
        for a in aliases:
            a_norm = normalize_text(a)
            # word boundary-ish check
            if re.search(rf"(^|[\s/,-]){re.escape(a_norm)}([\s/,-]|$)", t):
                found.add(skill)
                break

    return sorted(found)

def find_signals(text: str) -> List[str]:
    t = normalize_text(text)
    found = set()
    for signal, aliases in EXTRA_SIGNALS.items():
        for a in aliases:
            a_norm = normalize_text(a)
            if a_norm in t:
                found.add(signal)
                break
    return sorted(found)

def split_sections(raw: str) -> Dict[str, str]:
    """
    Very lightweight section splitter using common headings.
    Returns dict like {"responsibilities": "...", "requirements": "..."} when possible.
    """
    t = raw.replace("\r", "\n")
    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    joined = "\n".join(lines)

    # Build pattern that finds headings (case-insensitive)
    hdrs = sorted(set(SECTION_HEADERS), key=len, reverse=True)
    pattern = r"(?i)\b(" + "|".join(re.escape(h) for h in hdrs) + r")\b"
    matches = list(re.finditer(pattern, joined))

    if not matches:
        return {"full_text": joined}

    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(joined)
        title = m.group(1).lower().strip()
        body = joined[m.end():end].strip(" :\n\t-")
        sections[title] = body

    # Always keep full text too
    sections["full_text"] = joined
    return sections


# ---------------------------
# Data model
# ---------------------------

@dataclass
class JobParsed:
    ref: str
    position: str
    employer: str
    url: str
    ad_type: str
    files: List[str]
    raw_text: str
    sections: Dict[str, str]
    skills: List[str]
    signals: List[str]


# ---------------------------
# Load + Parse scraped output
# ---------------------------

def load_topjobs_metadata(folder: str) -> List[dict]:
    meta_path = os.path.join(folder, "metadata.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)

def read_text_if_exists(folder: str, files: List[str]) -> str:
    # Prefer *_content.txt if present
    for fn in files:
        if fn.lower().endswith("_content.txt") or fn.lower().endswith(".txt"):
            p = os.path.join(folder, fn)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
    return ""

def read_image_ocr_if_exists(folder: str, files: List[str]) -> Optional[str]:
    # Try OCR on first image we see
    for fn in files:
        if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            p = os.path.join(folder, fn)
            if os.path.exists(p):
                return ocr_image_to_text(p)
    return None

def parse_jobs(scraped_folder: str, enable_ocr: bool = False) -> List[JobParsed]:
    meta = load_topjobs_metadata(scraped_folder)
    parsed: List[JobParsed] = []

    for j in meta:
        raw = read_text_if_exists(scraped_folder, j.get("files", []))

        # If no text file exists, fall back to OCR automatically (flag keeps manual control for existing text).
        if not raw:
            ocr_text = read_image_ocr_if_exists(scraped_folder, j.get("files", []))
            if ocr_text:
                raw = ocr_text
        elif enable_ocr:
            # When explicitly requested, try to enrich text with OCR even if a text blob already exists.
            ocr_text = read_image_ocr_if_exists(scraped_folder, j.get("files", []))
            if ocr_text and ocr_text.strip():
                raw = f"{raw}\n\n{ocr_text}"

        if not raw:
            raw = ""  # keep empty; still produce record

        # Include title/company to rescue skills when body text is unavailable.
        match_text = " ".join([
            raw,
            j.get("position", ""),
            j.get("employer", ""),
        ]).strip()

        sections = split_sections(match_text or raw)
        skills = find_skills(match_text)
        signals = find_signals(match_text)

        parsed.append(
            JobParsed(
                ref=j.get("ref", ""),
                position=j.get("position", ""),
                employer=j.get("employer", ""),
                url=j.get("url", ""),
                ad_type=j.get("type", ""),
                files=j.get("files", []),
                raw_text=raw,
                sections=sections,
                skills=skills,
                signals=signals,
            )
        )

    return parsed


# ---------------------------
# Skill match / gap scoring
# ---------------------------

def normalize_skill_list(skills: List[str]) -> List[str]:
    return sorted({normalize_text(s) for s in skills if s and s.strip()})

def excerpt_text(text: str, limit: int = 700) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."

def full_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split())

def score_job(job_skills: List[str], user_skills: List[str]) -> Dict[str, object]:
    js = set(normalize_skill_list(job_skills))
    us = set(normalize_skill_list(user_skills))

    overlap = sorted(js & us)
    missing = sorted(js - us)

    # Simple percentage: how many required skills you already have
    pct = 0.0
    if js:
        pct = (len(overlap) / len(js)) * 100.0

    return {
        "match_percent": round(pct, 2),
        "overlap": overlap,
        "missing": missing,
        "job_skill_count": len(js),
        "user_skill_count": len(us),
    }

def rank_jobs(jobs: List[JobParsed], user_skills: List[str]) -> List[Dict[str, object]]:
    ranked = []
    for job in jobs:
        s = score_job(job.skills, user_skills)
        ranked.append({
            "ref": job.ref,
            "position": job.position,
            "employer": job.employer,
            "url": job.url,
            "text_excerpt": excerpt_text(job.raw_text),
            "text_full": full_text(job.raw_text),
            "skills_found": job.skills,
            **s,
        })
    ranked.sort(key=lambda x: x["match_percent"], reverse=True)
    return ranked


# ---------------------------
# CLI entry
# ---------------------------

def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--scraped_folder", required=True, help="Path to folder containing metadata.json + downloaded files")
    ap.add_argument("--user_skills", default="", help="Comma-separated skills. Example: 'react,javascript,html,css,rest api'")
    ap.add_argument("--user_skills_json", default="", help="Optional path to JSON containing skills list under key 'skills'")
    ap.add_argument("--enable_ocr", action="store_true", help="Try OCR for image ads (requires pytesseract installed)")
    ap.add_argument("--out_json", default="job_ranked.json", help="Output JSON file name")
    args = ap.parse_args()

    user_skills: List[str] = []
    if args.user_skills.strip():
        user_skills = [s.strip() for s in args.user_skills.split(",") if s.strip()]

    if args.user_skills_json.strip():
        with open(args.user_skills_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("skills"), list):
            user_skills.extend([str(x) for x in data["skills"]])

    user_skills = normalize_skill_list(user_skills)

    jobs = parse_jobs(args.scraped_folder, enable_ocr=args.enable_ocr)
    ranked = rank_jobs(jobs, user_skills)

    out_path = os.path.join(args.scraped_folder, args.out_json)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ranked, f, indent=2, ensure_ascii=False)

    # Print top 10
    print("\nTop matches:")
    for i, r in enumerate(ranked[:10], 1):
        print(f"{i:2d}. {r['match_percent']:6.2f}% | {r['position']} - {r['employer']} ({r['ref']})")
        skills_preview = ", ".join(r.get("skills_found", [])[:15])
        print(f"    skills: {skills_preview or '(none found)'}")
        if r["missing"]:
            print("    missing:", ", ".join(r["missing"][:10]) + (" ..." if len(r["missing"]) > 10 else ""))

    print(f"\nSaved: {out_path}")

if __name__ == "__main__":
    main()


