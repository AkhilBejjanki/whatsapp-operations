"""Reading CSV/Excel files and cleaning phone numbers."""

import io
import re

import pandas as pd
import phonenumbers


def parse_file(filename: str, content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    name = (filename or "").lower()
    try:
        if name.endswith(".csv") or name.endswith(".txt"):
            df = pd.read_csv(
                io.BytesIO(content), dtype=str, keep_default_na=False,
                sep=None, engine="python", encoding_errors="replace",
            )
        elif name.endswith(".xlsx") or name.endswith(".xlsm"):
            df = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
        else:
            raise ValueError("Please upload a .csv or .xlsx file")
    except ValueError:
        raise
    except Exception as exc:  # pandas raises many different parser errors
        raise ValueError(f"Could not read the file: {exc}") from exc

    df.columns = [str(c).strip() or f"Column {i + 1}" for i, c in enumerate(df.columns)]
    df = df.fillna("")
    df = df[~(df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1))]
    rows = [{k: str(v).strip() for k, v in row.items()} for row in df.to_dict("records")]
    return list(df.columns), rows


def suggest_columns(columns: list[str]) -> dict[str, str | None]:
    def find(*words: str) -> str | None:
        for col in columns:
            if any(w in col.lower() for w in words):
                return col
        return None

    return {
        "phone": find("phone", "mobile", "whatsapp", "number", "contact", "cell"),
        "name": find("name", "customer", "client"),
    }


_DECIMAL_SUFFIX = re.compile(r"^(\d+)\.0+$")


def normalize_phone(raw: str, default_region: str) -> tuple[str | None, str | None]:
    """Return (E.164 number, None) or (None, reason it's invalid)."""
    text = (raw or "").strip()
    if not text or text.lower() == "nan":
        return None, "Phone number is empty"

    match = _DECIMAL_SUFFIX.match(text)  # Excel can turn 919876543210 into "919876543210.0"
    if match:
        text = match.group(1)
    if re.search(r"[eE]\+?\d", text):
        return None, "Number is in scientific notation (format the Excel column as Text)"

    digits = re.sub(r"[^\d+]", "", text)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not re.sub(r"\D", "", digits):
        return None, "No digits in phone number"

    candidates = []
    try:
        if digits.startswith("+"):
            candidates.append(phonenumbers.parse(digits, None))
        else:
            candidates.append(phonenumbers.parse(digits, default_region))
            # Number may already include a country code without the "+"
            try:
                candidates.append(phonenumbers.parse("+" + digits, None))
            except phonenumbers.NumberParseException:
                pass
    except phonenumbers.NumberParseException:
        return None, "Unrecognised phone number format"

    for number in candidates:
        if phonenumbers.is_valid_number(number):
            return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164), None
    return None, "Invalid phone number"
