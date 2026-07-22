"""Tiny stdlib HTTP client. Never raises on network/parse failure — returns None so a
single dead feed degrades to a gap instead of crashing the run (HANDOFF §7)."""

import json
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 30
USER_AGENT = "fishfinder/0.1 (https://github.com/; offshore fishing recs; $0 project)"


def get_text(url: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """GET a URL, return the body text, or None on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def get_json(url: str, timeout: float = DEFAULT_TIMEOUT):
    """GET a URL and parse JSON, or None on any network/parse error."""
    body = get_text(url, timeout=timeout)
    if body is None:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
