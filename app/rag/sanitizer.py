import re

# Regex patterns for common secrets and internal credentials
SECRET_PATTERNS = [
    (re.compile(r'postgresql(?:\+psycopg)?://[^\s]+', re.IGNORECASE), '[REDACTED_DB_URI]'),
    (re.compile(r'mongodb(?:\+srv)?://[^\s]+', re.IGNORECASE), '[REDACTED_DB_URI]'),
    (re.compile(r'(?:sk-|gsk_|pk-|api_key=|token=)[a-zA-Z0-9_\-]{20,}', re.IGNORECASE), '[REDACTED_SECRET]'),
    (re.compile(r'-----BEGIN[A-Z ]+PRIVATE KEY-----[\s\S]+?-----END[A-Z ]+PRIVATE KEY-----', re.IGNORECASE), '[REDACTED_KEY]'),
]

def sanitize_content(text: str) -> str:
    """
    Scans text for internal credentials, database URIs, and API keys,
    replacing them with redaction tokens.
    """
    if not text:
        return text
        
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
        
    return text