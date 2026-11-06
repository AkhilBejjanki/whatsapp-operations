"""Work out which variables a WhatsApp template needs, and build the send payload."""

import re
from typing import Any

VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
MEDIA_FORMATS = {"IMAGE", "VIDEO", "DOCUMENT"}


def _ordered_vars(text: str) -> list[str]:
    names = list(dict.fromkeys(VAR_RE.findall(text or "")))
    if names and all(n.isdigit() for n in names):
        names.sort(key=int)
    return names


def template_variables(components: list[dict]) -> list[dict[str, Any]]:
    """List every variable the user must fill in.

    key format: "header:1", "body:2", "body:first_name", "button:0".
    """
    out: list[dict[str, Any]] = []
    for comp in components or []:
        ctype = (comp.get("type") or "").upper()
        if ctype == "HEADER" and (comp.get("format") or "").upper() == "TEXT":
            for name in _ordered_vars(comp.get("text", "")):
                out.append({"key": f"header:{name}", "component": "header", "name": name,
                            "label": f"Header {{{{{name}}}}}"})
        elif ctype == "BODY":
            for name in _ordered_vars(comp.get("text", "")):
                out.append({"key": f"body:{name}", "component": "body", "name": name,
                            "label": f"Body {{{{{name}}}}}"})
        elif ctype == "BUTTONS":
            for i, button in enumerate(comp.get("buttons", [])):
                if (button.get("type") or "").upper() == "URL" and VAR_RE.search(button.get("url", "")):
                    out.append({"key": f"button:{i}", "component": "button", "index": i, "name": "1",
                                "label": f"Button \"{button.get('text', '')}\" link ending"})
    return out


def header_media_format(components: list[dict]) -> str | None:
    for comp in components or []:
        if (comp.get("type") or "").upper() == "HEADER":
            fmt = (comp.get("format") or "").upper()
            return fmt if fmt in MEDIA_FORMATS else None
    return None


_WS_RE = re.compile(r"\s+")


def clean_value(value: Any) -> str:
    """WhatsApp rejects variables containing newlines, tabs or 4+ spaces in a row."""
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return _WS_RE.sub(" ", text).strip()


def resolve_variables(mapping: dict[str, dict], row: dict) -> dict[str, str]:
    """mapping: {"body:1": {"type": "column", "value": "Name"} | {"type": "static", "value": "..."}}"""
    values: dict[str, str] = {}
    for key, source in mapping.items():
        if source.get("type") == "static":
            values[key] = clean_value(source.get("value"))
        else:
            values[key] = clean_value(row.get(source.get("value", "")))
    return values


def build_send_components(
    components: list[dict],
    parameter_format: str,
    values: dict[str, str],
    header_media_url: str | None,
) -> list[dict]:
    named = (parameter_format or "").upper() == "NAMED"
    header_params: list[dict] = []
    body_params: list[dict] = []
    button_params: list[tuple[int, str]] = []

    for var in template_variables(components):
        value = values.get(var["key"], "")
        if var["component"] in ("header", "body"):
            param: dict[str, Any] = {"type": "text", "text": value}
            if named:
                param["parameter_name"] = var["name"]
            (header_params if var["component"] == "header" else body_params).append(param)
        else:
            button_params.append((var["index"], value))

    media = header_media_format(components)
    if media:
        kind = media.lower()
        header_params = [{"type": kind, kind: {"link": header_media_url}}]

    result: list[dict] = []
    if header_params:
        result.append({"type": "header", "parameters": header_params})
    if body_params:
        result.append({"type": "body", "parameters": body_params})
    for index, value in button_params:
        result.append({"type": "button", "sub_type": "url", "index": str(index),
                       "parameters": [{"type": "text", "text": value}]})
    return result
