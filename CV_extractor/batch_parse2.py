import json
from pathlib import Path

from resume_pipeline import parse_resume

SKILLS_PATH = Path(__file__).with_name("skills.txt")
DEFAULT_SKILLS = ["Pythons", "SQL", "Machine Learning", "AWS", "Docker", "React"]

def load_skills() -> list[str]:
    """Load skills from skills.txt (one per line). Falls back to a small default list."""
    if SKILLS_PATH.exists():
        skills = [
            line.strip()
            for line in SKILLS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if skills:
            return skills
    return DEFAULT_SKILLS

SKILLS = load_skills()

INPUT_DIR = Path("CV")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

SUPPORTED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp"}


def main():
    if not INPUT_DIR.exists():
        print(f"[!] Folder not found: {INPUT_DIR.resolve()}")
        return

    files = [p for p in INPUT_DIR.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXT]

    if not files:
        print(f"[!] No supported files found in: {INPUT_DIR.resolve()}")
        return

    print(f"[OK] Found {len(files)} file(s) in {INPUT_DIR.resolve()}")
    print("Processing...")
    print()

    all_results = []

    for f in files:
        try:
            result = parse_resume(str(f), skills_list=SKILLS)

            out_path = OUTPUT_DIR / f"{f.stem}.json"
            with out_path.open("w", encoding="utf-8") as w:
                json.dump(result, w, ensure_ascii=False, indent=2)

            all_results.append({
                "file": str(f),
                "output": str(out_path),
                "method": result["meta"]["method"],
                "char_count": result["meta"]["quality"]["char_count"],
            })

            print(f"[OK] {f.name} -> {out_path.name}  [{result['meta']['method']}]")
        except Exception as e:
            print(f"[x] Failed: {f.name} | Error: {e}")

    # Optional: also write a combined summary file
    summary_path = OUTPUT_DIR / "_summary.json"
    with summary_path.open("w", encoding="utf-8") as w:
        json.dump(all_results, w, ensure_ascii=False, indent=2)

    print()
    print(f"Done. Summary: {summary_path}")


if __name__ == "__main__":
    main()
