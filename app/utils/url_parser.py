"""
Utility functions to parse and validate LinkedIn profile URLs.
Handles all common URL formats:
  - https://www.linkedin.com/in/username
  - https://linkedin.com/in/username/
  - https://www.linkedin.com/in/username?trk=...
  - http://linkedin.com/in/username
"""

import re
from urllib.parse import urlparse, urlunparse


# Regex that matches the /in/<public_id> segment of a LinkedIn URL
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:[a-z0-9\-]+\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)/?",
    re.IGNORECASE,
)


def extract_public_id(url: str) -> str | None:
    """
    Extract the LinkedIn public profile ID (username) from a URL.

    Args:
        url: Any LinkedIn profile URL string.

    Returns:
        The public_id string (e.g. "williamhgates") or None if not found.
    """
    if not url:
        return None

    match = _LINKEDIN_RE.search(url.strip())
    if match:
        return match.group(1).rstrip("/")
    return None


def normalize_url(url: str) -> str | None:
    """
    Return a clean, canonical LinkedIn profile URL.

    Args:
        url: Raw LinkedIn URL string.

    Returns:
        Canonical URL like "https://www.linkedin.com/in/username" or None.
    """
    public_id = extract_public_id(url)
    if not public_id:
        return None
    return f"https://www.linkedin.com/in/{public_id}"


def is_valid_linkedin_url(url: str) -> bool:
    """Return True if the URL looks like a valid LinkedIn profile URL."""
    return extract_public_id(url) is not None
