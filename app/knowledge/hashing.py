import hashlib


def compute_content_hash(content) -> str:
    """SHA-256 hex digest used for change detection and integrity."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()