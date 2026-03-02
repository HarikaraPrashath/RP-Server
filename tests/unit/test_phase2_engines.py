from __future__ import annotations

from app.engines.nlp.preprocess import normalize_skill, preprocess_text
from app.engines.scraper.dedup import deduplicate_metadata


def test_preprocess_text_expands_common_abbreviations():
    text = "We build ML and AI products with JS and ReactJS."
    out = preprocess_text(text)
    assert "machine" in out and "learning" in out
    assert "artificial" in out and "intelligence" in out
    assert "javascript" in out
    assert "react" in out


def test_normalize_skill_aliases():
    assert normalize_skill("JS") == "javascript"
    assert normalize_skill("ReactJS") == "react"


def test_deduplicate_metadata_drops_duplicates():
    rows = [
        {"ref": "1", "url": "https://a", "position": "Software Engineer", "employer": "X", "files": ["a.txt"]},
        {"ref": "1", "url": "https://a", "position": "Software Engineer", "employer": "X", "files": ["a.txt"]},
        {"ref": "2", "url": "https://b", "position": "Data Engineer", "employer": "Y", "files": ["b.txt"]},
    ]
    result = deduplicate_metadata(rows)
    assert result.dropped == 1
    assert len(result.kept) == 2
