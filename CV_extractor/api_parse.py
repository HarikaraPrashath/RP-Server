import json
import sys
import warnings
from pathlib import Path

from resume_pipeline import parse_resume

# Ensure UTF-8 output even on Windows terminals to avoid UnicodeEncodeError
try:  # pragma: no cover - best-effort
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Suppress noisy warnings that break JSON-only stdout
warnings.filterwarnings("ignore")

# Reuse the same skills list as batch parsing
SKILLS_PATH = Path(__file__).with_name("skills.txt")

_DEFAULT_FALLBACK = [
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


def load_skills() -> list[str]:
    """Load skills from `skills.txt` (ignores `#` comments); fall back to built-in list."""
    if SKILLS_PATH.exists():
        skills = [
            line.strip()
            for line in SKILLS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if skills:
            return skills
    return _DEFAULT_FALLBACK


DEFAULT_SKILLS = load_skills()


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python api_parse.py <file>"}))
        return 1

    file_path = Path(sys.argv[1]).expanduser()
    if not file_path.exists():
        print(json.dumps({"error": f"File not found: {file_path}"}))
        return 1

    try:
        result = parse_resume(str(file_path), skills_list=DEFAULT_SKILLS)
    except Exception as exc:  # keep errors visible to the caller
        print(
            json.dumps(
                {
                    "error": f"Failed to parse resume: {exc}",
                    "file": str(file_path),
                }
            )
        )
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
