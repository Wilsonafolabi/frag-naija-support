"""Document text cleaning.

Preserves section headings while normalizing whitespace and stripping obvious
extraction artifacts (page numbers, repeated footers, copyright lines).
"""
import re
import unicodedata


_ARTIFACT_PATTERNS = [
    re.compile(r"^\s*Page\s+\d+\s*(?:of\s+\d+)?\s*$", re.IGNORECASE),  # "Page 3 of 12"
    re.compile(r"^\s*\d{1,4}\s*$"),                                    # standalone page numbers
    re.compile(r"^\s*Confidential\s*$", re.IGNORECASE),
    re.compile(r"^\s*©\s*\d{4}\s*.*$"),                                # copyright lines
]


def normalize_whitespace(text: str) -> str:
    """Normalize unicode (NFKC) and collapse non-newline whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")      # no-break space
    text = text.replace("\t", " ")
    text = re.sub(r"[^\S\n]+", " ", text)   # collapse spaces but not newlines
    return "\n".join(line.rstrip() for line in text.split("\n"))


def remove_artifacts(text: str) -> str:
    """Drop lines that are obvious extraction artifacts."""
    kept = []
    for line in text.split("\n"):
        if any(p.match(line) for p in _ARTIFACT_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept)


def collapse_blank_lines(text: str) -> str:
    """More than two consecutive blank lines -> two."""
    return re.sub(r"\n{3,}", "\n\n", text)


def clean_text(text: str) -> str:
    """Full cleaning pipeline. Headings and paragraphs are preserved."""
    text = normalize_whitespace(text)
    text = remove_artifacts(text)
    text = collapse_blank_lines(text)
    return text.strip()