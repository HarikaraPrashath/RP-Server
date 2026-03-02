from __future__ import annotations

import re
from html import unescape
from typing import Iterable

ABBREVIATIONS = {
    "js": "javascript",
    "ts": "typescript",
    "ml": "machine learning",
    "nlp": "natural language processing",
    "ai": "artificial intelligence",
    "reactjs": "react",
    "nodejs": "node.js",
}

_STOPWORDS = {
    "the","a","an","and","or","to","for","of","in","on","with","at","by","from","as","is","are","be","this","that",
}


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def normalize_text(text: str) -> str:
    text = clean_html(text)
    text = text.replace("\u00a0", " ")
    text = text.lower()
    text = re.sub(r"[^\w\s\.\+\-/#]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return [tok for tok in normalize_text(text).split() if tok]


def remove_stopwords(tokens: Iterable[str]) -> list[str]:
    return [t for t in tokens if t not in _STOPWORDS]


def lemmatize(tokens: Iterable[str]) -> list[str]:
    # Lightweight lemmatization fallback to avoid heavy runtime deps.
    out: list[str] = []
    for t in tokens:
        if t.endswith("ies") and len(t) > 4:
            out.append(t[:-3] + "y")
        elif t.endswith("ing") and len(t) > 5:
            out.append(t[:-3])
        elif t.endswith("ed") and len(t) > 4:
            out.append(t[:-2])
        elif t.endswith("s") and len(t) > 3:
            out.append(t[:-1])
        else:
            out.append(t)
    return out


def expand_abbreviations(tokens: Iterable[str]) -> list[str]:
    expanded: list[str] = []
    for t in tokens:
        rep = ABBREVIATIONS.get(t, t)
        expanded.extend(rep.split())
    return expanded


def normalize_skill(skill: str) -> str:
    norm = normalize_text(skill)
    return ABBREVIATIONS.get(norm, norm)


def preprocess_text(text: str) -> str:
    tokens = tokenize(text)
    tokens = remove_stopwords(tokens)
    tokens = lemmatize(tokens)
    tokens = expand_abbreviations(tokens)
    return " ".join(tokens)
