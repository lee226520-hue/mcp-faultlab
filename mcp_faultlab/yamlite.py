"""Tiny YAML reader for the scenario subset used by mcp-faultlab.

It intentionally supports mappings, lists, comments, quoted strings, inline
JSON-style lists/maps and scalar values. JSON is accepted as a strict subset.
For complex YAML, install PyYAML and the loader will use it automatically.
"""

import ast
import json
import re


def _split_top_level(text, delimiter=","):
    parts = []
    start = 0
    depth = 0
    quote = None
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if char in "'\"":
            quote = None if quote == char else (char if quote is None else quote)
        elif quote is None and char in "[{(":
            depth += 1
        elif quote is None and char in "]})":
            depth = max(0, depth - 1)
        elif quote is None and char == delimiter and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _scalar(value):
    value = value.strip()
    if not value:
        return None
    if value in ("null", "Null", "NULL", "~"):
        return None
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return json.loads(value)
    except Exception:
        pass
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        result = {}
        for part in _split_top_level(inner):
            if ":" in part:
                key, val = part.split(":", 1)
                result[key.strip().strip("'\"")] = _scalar(val)
            else:
                return value
        return result
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except Exception:
            return [_scalar(part) for part in _split_top_level(value[1:-1]) if part.strip()]
    if (len(value) >= 2 and value[0] == value[-1] and value[0] in "'\""):
        return value[1:-1]
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _strip_comment(line):
    quoted = None
    for i, char in enumerate(line):
        if char in "'\"":
            quoted = None if quoted == char else (char if quoted is None else quoted)
        elif char == "#" and quoted is None and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip()
    return line.rstrip()


def loads(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        pass

    lines = []
    for raw in text.splitlines():
        cleaned = _strip_comment(raw)
        if cleaned.strip():
            indent = len(cleaned) - len(cleaned.lstrip(" "))
            lines.append((indent, cleaned.strip()))
    if not lines:
        return {}

    def parse_block(index, indent):
        is_list = lines[index][1].startswith("-")
        result = [] if is_list else {}
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError("invalid indentation near: %s" % content)
            if is_list:
                if not content.startswith("-"):
                    break
                item = content[1:].strip()
                if not item:
                    if index + 1 < len(lines) and lines[index + 1][0] > indent:
                        value, index = parse_block(index + 1, lines[index + 1][0])
                    else:
                        value, index = None, index + 1
                    result.append(value)
                    continue
                if ":" in item and not item.startswith(("http:", "https:")):
                    key, raw_value = item.split(":", 1)
                    obj = {key.strip(): _scalar(raw_value)} if raw_value.strip() else {key.strip(): None}
                    index += 1
                    if index < len(lines) and lines[index][0] > indent:
                        nested, index = parse_block(index, lines[index][0])
                        if obj[key.strip()] is None and not isinstance(nested, dict):
                            obj[key.strip()] = nested
                        elif isinstance(nested, dict):
                            obj.update(nested)
                    result.append(obj)
                else:
                    result.append(_scalar(item))
                    index += 1
            else:
                if ":" not in content:
                    raise ValueError("expected key: value near: %s" % content)
                key, raw_value = content.split(":", 1)
                key = key.strip()
                raw_value = raw_value.strip()
                index += 1
                if raw_value:
                    result[key] = _scalar(raw_value)
                elif index < len(lines) and lines[index][0] > indent:
                    result[key], index = parse_block(index, lines[index][0])
                else:
                    result[key] = None
        return result, index

    value, _ = parse_block(0, lines[0][0])
    return value


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return loads(handle.read())
