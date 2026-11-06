"""Meta error codes, with plain-language explanations for the dashboard.

Full list: https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
"""

ERROR_HINTS: dict[int, str] = {
    0: "Authentication problem: check the access token",
    4: "Too many API calls. Slow down and retry",
    100: "Invalid parameter in the request",
    190: "Access token expired or invalid: update it in Settings",
    200: "Missing permission for this WhatsApp account",
    368: "Temporarily blocked for policy violations",
    80007: "WhatsApp account rate limit reached",
    130429: "Throughput limit reached (too many messages per second)",
    131000: "Temporary error at Meta",
    131005: "Access denied: check token permissions",
    131008: "A required template variable is missing",
    131009: "A template variable value is invalid",
    131016: "WhatsApp service temporarily unavailable",
    131021: "Sender and recipient are the same number",
    131026: "Not delivered: number is probably not on WhatsApp (or the user's app is outdated)",
    131031: "WhatsApp Business account is locked or restricted",
    131042: "Payment problem: add or fix the payment method in WhatsApp Manager",
    131045: "Phone number certificate problem: re-register the number",
    131047: "More than 24 hours since the customer last messaged you",
    131048: "Spam rate limit: too many people blocked or reported your messages",
    131049: "Meta didn't deliver this marketing message to protect user experience (try later)",
    131050: "This user stopped marketing messages from your business",
    131051: "Unsupported message type",
    131052: "Media download failed",
    131053: "Media upload failed: check the header media URL",
    131056: "Too many messages to this same number in a short time",
    132000: "Number of template variables doesn't match the template",
    132001: "Template doesn't exist in this language, or isn't approved",
    132005: "Text with variables filled in is too long",
    132007: "Template content breaks WhatsApp formatting rules",
    132012: "Template variable format is wrong",
    132015: "Template paused by Meta due to low quality",
    132016: "Template disabled by Meta due to low quality",
    133010: "Phone number not registered with the Cloud API: register it in Settings",
}

# Worth retrying the same message after a short wait.
RETRYABLE_CODES = {1, 2, 4, 80007, 130429, 131000, 131016, 131056}

# These affect every message in the campaign, so pause the campaign instead of
# failing thousands of messages one by one.
CAMPAIGN_FATAL_CODES = {0, 190, 200, 368, 131005, 131031, 131042, 131045, 132000, 132001,
                        132012, 132015, 132016, 133010}

# Retrying these is pointless (number not on WhatsApp, user opted out).
NOT_WORTH_RETRYING = {131026, 131050, 131021}


def describe(code: int | None, fallback: str | None = None) -> str:
    if code is not None and code in ERROR_HINTS:
        return ERROR_HINTS[code]
    return fallback or "Unknown error"
