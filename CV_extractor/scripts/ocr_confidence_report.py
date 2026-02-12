from pathlib import Path
import statistics as stats
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from resume_pipeline import render_pdf_to_images, ocr_image, SUPPORTED_IMAGE_EXT


def collect_confs(path: Path):
    confs = []
    if path.suffix.lower() == ".pdf":
        images = render_pdf_to_images(str(path))
        for img in images:
            confs.extend([ln.conf for ln in ocr_image(img)])
    elif path.suffix.lower() in SUPPORTED_IMAGE_EXT:
        from PIL import Image

        img = Image.open(path)
        confs.extend([ln.conf for ln in ocr_image(img)])
    return confs


def report(confs):
    if not confs:
        return "No OCR lines detected."
    confs_sorted = sorted(confs)
    mean = sum(confs) / len(confs)
    median = stats.median(confs_sorted)
    p90 = confs_sorted[int(0.9 * (len(confs_sorted) - 1))]
    high = sum(1 for c in confs if c >= 0.80) / len(confs) * 100
    return (
        f"lines={len(confs)}\n"
        f"mean={mean:.3f}\n"
        f"median={median:.3f}\n"
        f"p90={p90:.3f}\n"
        f"min={min(confs):.3f}\n"
        f"max={max(confs):.3f}\n"
        f"pct>=0.80={high:.1f}%"
    )


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ocr_confidence_report.py <file.pdf|image>")
        return 1

    path = Path(sys.argv[1]).expanduser()
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    confs = collect_confs(path)
    print(report(confs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
