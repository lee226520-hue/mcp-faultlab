import re


_KEY_PATTERN = re.compile(r"((?:[\"']?)(?:api[_-]?key|database[_-]?url|password|secret|token|authorization)(?:[\"']?)\s*[:=]\s*)([\"']?)([^\"'\s,;}]*)\2", re.I)
_BEARER_PATTERN = re.compile(r"(bearer\s+)[A-Za-z0-9._~+/=-]+", re.I)


def redact(value):
    """Return a JSON-safe copy with common credential values removed."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if re.search(r"(api[_-]?key|database[_-]?url|password|secret|token|authorization)", str(key), re.I):
                result[key] = "<redacted>"
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER_PATTERN.sub(r"\1<redacted>", _KEY_PATTERN.sub(r"\1\2<redacted>\2", value))
    return value
