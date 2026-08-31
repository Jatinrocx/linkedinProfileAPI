"""
LinkedIn Voyager API scraper — Layer 1 (primary).

The Voyager API is LinkedIn's own internal REST API that powers
their web frontend. It returns structured JSON directly, which is
far more reliable than HTML parsing.

Authentication uses two cookies from an active LinkedIn session:
  - li_at      : Primary session token
  - JSESSIONID : Used to derive the csrf-token header

Both are read from environment variables set in .env (never committed).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from ..models.profile import (
    Certification,
    DateRange,
    Education,
    Experience,
    HonorAward,
    Language,
    Location,
    ProfileData,
    Project,
    Publication,
    VolunteerWork,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE = "https://www.linkedin.com"
_VOYAGER = f"{_BASE}/voyager/api"

_DEFAULT_HEADERS = {
    "accept": "application/vnd.linkedin.normalized+json+2.1",
    "accept-language": "en-US,en;q=0.9",
    "x-restli-protocol-version": "2.0.0",
    "x-li-lang": "en_US",
    "x-li-track": json.dumps(
        {
            "clientVersion": "1.13.6731",
            "mpVersion": "1.13.6731",
            "osName": "web",
            "timezoneOffset": 5.5,
            "timezone": "Asia/Kolkata",
            "deviceFormFactor": "DESKTOP",
            "mpName": "voyager-web",
            "displayDensity": 1,
            "displayWidth": 1920,
            "displayHeight": 1080,
        }
    ),
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "referer": "https://www.linkedin.com/feed/",
}


# ---------------------------------------------------------------------------
# Helper: build authenticated httpx client
# ---------------------------------------------------------------------------


from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def _build_client() -> httpx.AsyncClient:
    """Create an httpx AsyncClient pre-loaded with LinkedIn session cookies."""
    if _ENV_PATH.exists():
        load_dotenv(dotenv_path=_ENV_PATH, override=True)
    else:
        load_dotenv()
    li_at = os.environ.get("LI_AT", "")
    jsessionid = os.environ.get("JSESSIONID", "")

    if not li_at or not jsessionid:
        raise EnvironmentError(
            "LI_AT and JSESSIONID environment variables must be set. "
            "See .env.example for instructions."
        )

    # JSESSIONID value is typically wrapped in quotes like: "ajax:123456789"
    # The csrf-token must be the raw value WITHOUT the surrounding quotes.
    csrf_token = jsessionid.strip('"')

    cookies = httpx.Cookies()
    cookies.set("li_at", li_at, domain=".linkedin.com")
    cookies.set("JSESSIONID", jsessionid, domain=".linkedin.com")

    headers = {**_DEFAULT_HEADERS, "csrf-token": csrf_token}

    return httpx.AsyncClient(
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
        timeout=30.0,
    )


# ---------------------------------------------------------------------------
# Helper: safe deep-get
# ---------------------------------------------------------------------------


def _get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts/lists."""
    for key in keys:
        if obj is None:
            return default
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int):
            try:
                obj = obj[key]
            except IndexError:
                return default
        else:
            return default
    return obj if obj is not None else default


# ---------------------------------------------------------------------------
# Helper: resolve entity URNs from the normalised response
# ---------------------------------------------------------------------------


def _resolve(data: dict, urn: str | None) -> dict:
    """Look up an entity in the normalised Voyager response by its URN."""
    if not urn or not data:
        return {}
    included = data.get("included", [])
    for item in included:
        if item.get("entityUrn") == urn or item.get("$id") == urn:
            return item
    return {}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_date(raw: dict | None) -> DateRange | None:
    if not raw:
        return None
    month = raw.get("month")
    year = raw.get("year")
    if not month and not year:
        return None
    return DateRange(month=month, year=year)


def _img_url(raw: Any) -> str | None:
    """Extract the best-quality image URL from a Voyager picture object."""
    if not raw:
        return None
    root = _get(raw, "rootUrl", default="")
    artifacts = _get(raw, "artifacts", default=[])
    if artifacts and isinstance(artifacts, list):
        valid_artifacts = [a for a in artifacts if isinstance(a, dict)]
        if valid_artifacts:
            # Pick the largest image safely
            best = max(valid_artifacts, key=lambda a: a.get("width") or 0)
            segment = best.get("fileIdentifyingUrlPathSegment", "")
            if root and segment:
                return root + segment
    # Fallback: displayImageReference
    display = _get(raw, "displayImageReference")
    if display and display != raw and isinstance(display, dict):
        return _img_url(display)
    return None


def _parse_experience(items: list[dict], included: list[dict]) -> list[Experience]:
    results: list[Experience] = []
    for item in items:
        entity_urn = item.get("entityUrn", "")
        # Company info lives in companyResolutionResult or company sub-key
        company_info = item.get("companyResolutionResult") or {}
        company = (
            _get(item, "companyName")
            or _get(company_info, "name")
        )
        company_logo_raw = (
            _get(company_info, "logo", "image", "com.linkedin.common.VectorImage")
            or _get(company_info, "logo")
        )
        date_range = item.get("dateRange") or {}
        time_period = item.get("timePeriod") or {}
        start_date = date_range.get("start") or time_period.get("startDate")
        end_date = date_range.get("end") or time_period.get("endDate")
        
        is_current = bool(start_date) and end_date is None

        results.append(
            Experience(
                company=company,
                company_linkedin_url=(
                    f"https://www.linkedin.com/company/{company_info.get('universalName')}"
                    if company_info.get("universalName")
                    else None
                ),
                company_logo_url=_img_url(company_logo_raw),
                title=item.get("title"),
                location=item.get("locationName"),
                started_at=_parse_date(start_date),
                ended_at=_parse_date(end_date),
                is_current=is_current,
                description=item.get("description"),
            )
        )
    return results


def _parse_education(items: list[dict]) -> list[Education]:
    results: list[Education] = []
    for item in items:
        school_info = item.get("schoolResolutionResult") or {}
        logo_raw = (
            _get(school_info, "logo", "image", "com.linkedin.common.VectorImage")
            or _get(school_info, "logo")
        )
        date_range = item.get("dateRange") or {}
        results.append(
            Education(
                school=item.get("schoolName") or school_info.get("name"),
                school_linkedin_url=(
                    f"https://www.linkedin.com/school/{school_info.get('universalName')}"
                    if school_info.get("universalName")
                    else None
                ),
                school_logo_url=_img_url(logo_raw),
                degree=item.get("degreeName"),
                field_of_study=item.get("fieldOfStudy"),
                started_at=_parse_date(date_range.get("start")),
                ended_at=_parse_date(date_range.get("end")),
                description=item.get("description"),
                activities=item.get("activities"),
            )
        )
    return results


def _parse_skills(items: list[dict]) -> list[str]:
    return [
        item.get("name") or _get(item, "skill", "name")
        for item in items
        if item.get("name") or _get(item, "skill", "name")
    ]


def _parse_certifications(items: list[dict]) -> list[Certification]:
    results: list[Certification] = []
    for item in items:
        company_info = item.get("companyResolutionResult") or {}
        logo_raw = (
            _get(company_info, "logo", "image", "com.linkedin.common.VectorImage")
            or _get(company_info, "logo")
        )
        results.append(
            Certification(
                name=item.get("name"),
                issuing_organization=item.get("authority") or company_info.get("name"),
                issuing_org_logo_url=_img_url(logo_raw),
                issued_at=_parse_date(item.get("timePeriod", {}).get("startDate")),
                expires_at=_parse_date(item.get("timePeriod", {}).get("endDate")),
                credential_id=item.get("licenseNumber"),
                credential_url=item.get("url"),
            )
        )
    return results


def _parse_languages(items: list[dict]) -> list[Language]:
    return [
        Language(name=item.get("name"), proficiency=item.get("proficiency"))
        for item in items
        if item.get("name")
    ]


def _parse_honors(items: list[dict]) -> list[HonorAward]:
    results: list[HonorAward] = []
    for item in items:
        results.append(
            HonorAward(
                title=item.get("title"),
                issuer=item.get("issuer"),
                issued_at=_parse_date(item.get("issueDate")),
                description=item.get("description"),
            )
        )
    return results


def _parse_publications(items: list[dict]) -> list[Publication]:
    results: list[Publication] = []
    for item in items:
        results.append(
            Publication(
                title=item.get("name"),
                publisher=item.get("publisher"),
                published_at=_parse_date(item.get("date")),
                description=item.get("description"),
                url=item.get("url"),
            )
        )
    return results


def _parse_volunteer(items: list[dict]) -> list[VolunteerWork]:
    results: list[VolunteerWork] = []
    for item in items:
        date_range = item.get("dateRange") or {}
        start_date = date_range.get("start")
        end_date = date_range.get("end")
        is_current = bool(start_date) and end_date is None
        results.append(
            VolunteerWork(
                organization=item.get("companyName"),
                role=item.get("role"),
                cause=item.get("cause"),
                started_at=_parse_date(start_date),
                ended_at=_parse_date(end_date),
                is_current=is_current,
                description=item.get("description"),
            )
        )
    return results


def _parse_projects(items: list[dict]) -> list[Project]:
    results: list[Project] = []
    for item in items:
        date_range = item.get("dateRange") or {}
        url = None
        for member in item.get("members", []):
            if member.get("url"):
                url = member["url"]
                break
        results.append(
            Project(
                title=item.get("title"),
                description=item.get("description"),
                url=url,
                started_at=_parse_date(date_range.get("start")),
                ended_at=_parse_date(date_range.get("end")),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Main Voyager fetch function
# ---------------------------------------------------------------------------


async def fetch_profile(public_id: str) -> ProfileData:
    """
    Fetch a LinkedIn profile via the Voyager internal API.

    Args:
        public_id: The LinkedIn profile slug (e.g. "williamhgates").

    Returns:
        A fully populated ProfileData object.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        EnvironmentError: If credentials are not configured.
        ValueError: If the response cannot be parsed.
    """
    async with _build_client() as client:
        # ----------------------------------------------------------------
        # 1. Fetch main profile data
        # ----------------------------------------------------------------
        profile_url = (
            f"{_VOYAGER}/identity/dash/profiles"
            f"?q=memberIdentityUrn"
            f"&memberIdentityUrn=urn%3Ali%3Afsd_profile%3A{public_id}"
            f"&decorationId=com.linkedin.voyager.dash.deco.web.FullProfileWithEntities-91"
        )

        # Also try the simpler profile view endpoint as fallback
        profile_view_url = (
            f"{_VOYAGER}/identity/profiles/{public_id}/profileView"
        )

        logger.info("Fetching Voyager profile for: %s", public_id)

        resp = await client.get(profile_url)

        # Handle 302/303 redirects and authwall HTML responses instantly
        location_hdr = resp.headers.get("location", "").lower()
        content_type = resp.headers.get("content-type", "").lower()
        is_redirect = resp.status_code in (301, 302, 303, 307, 308)
        is_authwall = "authwall" in location_hdr or "login" in location_hdr or "signup" in location_hdr or "text/html" in content_type

        if is_redirect or is_authwall:
            raise PermissionError(
                "LinkedIn session cookies (LI_AT / JSESSIONID) have expired or are invalid. "
                "LinkedIn redirected the API request to authwall/login. "
                "Please update your credentials in .env."
            )

        if resp.status_code in (404, 410):
            logger.info("Dash endpoint returned %s, trying legacy profile_view_url", resp.status_code)
            resp = await client.get(profile_view_url)
            content_type = resp.headers.get("content-type", "")
            if "text/html" in content_type or "authwall" in str(resp.url).lower():
                raise PermissionError(
                    "LinkedIn redirected to authwall/login. "
                    "Your LI_AT or JSESSIONID cookie may have expired or is invalid."
                )

        if resp.status_code in (401, 403):
            raise PermissionError(
                f"LinkedIn returned HTTP {resp.status_code}. "
                "Your LI_AT or JSESSIONID cookie may have expired or is invalid."
            )

        resp.raise_for_status()

        try:
            data = resp.json()
        except Exception as exc:
            if "text/html" in content_type or resp.text.strip().startswith("<"):
                raise PermissionError(
                    "LinkedIn returned HTML instead of JSON. "
                    "Your LI_AT or JSESSIONID cookie is likely invalid or expired."
                )
            raise exc

        # ----------------------------------------------------------------
        # 2. Extract profile entity
        # ----------------------------------------------------------------
        profile_raw: dict = {}
        included: list[dict] = data.get("included", [])

        # The main profile object usually has miniProfile or postalCode fields
        for item in included:
            if item.get("$type") == "com.linkedin.voyager.identity.profile.Profile":
                profile_raw = item
                break

        if not profile_raw:
            # Try the top-level data element
            profile_raw = data.get("data", {}) or {}

        # ----------------------------------------------------------------
        # 3. Extract sub-sections from included
        # ----------------------------------------------------------------
        def _collect(type_key: str) -> list[dict]:
            return [
                i for i in included
                if i.get("$type", "").endswith(type_key)
            ]

        experience_items = _collect("Position")
        education_items = _collect("Education")
        skill_items = _collect("Skill")
        cert_items = _collect("Certification")
        lang_items = _collect("Language")
        honor_items = _collect("Honor")
        pub_items = _collect("Publication")
        vol_items = _collect("VolunteerExperience")
        project_items = _collect("Project")

        # ----------------------------------------------------------------
        # 4. Profile picture
        # ----------------------------------------------------------------
        mini_profile: dict = {}
        for item in included:
            if item.get("$type") == "com.linkedin.voyager.identity.shared.MiniProfile":
                mini_profile = item
                break

        profile_pic_raw = (
            _get(mini_profile, "picture", "com.linkedin.common.VectorImage")
            or _get(mini_profile, "picture")
            or _get(profile_raw, "photoUrl")
        )

        background_raw = (
            _get(profile_raw, "backgroundCoverImage", "com.linkedin.common.VectorImage")
            or _get(profile_raw, "backgroundCoverImage")
        )

        # ----------------------------------------------------------------
        # 5. Location
        # ----------------------------------------------------------------
        geo_location = _get(profile_raw, "geoLocation") or {}
        country_raw = (
            _get(profile_raw, "geoCountryName")
            or _get(geo_location, "country", "defaultLocalizedName")
        )
        location_str = (
            _get(profile_raw, "locationName")
            or _get(geo_location, "defaultLocalizedName")
        )

        backfilled = _get(profile_raw, "geoLocationBackfilled")
        city_str = backfilled if isinstance(backfilled, str) else (_get(backfilled, "cityName") if isinstance(backfilled, dict) else None)

        location_obj = Location(
            city=city_str,
            region=_get(geo_location, "state", "defaultLocalizedName"),
            country=country_raw if isinstance(country_raw, str) else None,
            full=location_str if isinstance(location_str, str) else None,
        ) if location_str or country_raw else None

        # ----------------------------------------------------------------
        # 6. Followers / connections
        # ----------------------------------------------------------------
        network_info: dict = {}
        for item in included:
            if "NetworkInfo" in item.get("$type", ""):
                network_info = item
                break

        connections = _get(network_info, "connectionsCount")
        followers = _get(network_info, "followersCount")

        # ----------------------------------------------------------------
        # 7. Assemble final ProfileData
        # ----------------------------------------------------------------
        first = profile_raw.get("firstName") or mini_profile.get("firstName", "")
        last = profile_raw.get("lastName") or mini_profile.get("lastName", "")
        is_hiring = any("hiring" in str(i).lower() for i in included if isinstance(i, dict))

        return ProfileData(
            public_id=public_id,
            full_name=f"{first} {last}".strip() or None,
            first_name=first or None,
            last_name=last or None,
            headline=(
                profile_raw.get("headline")
                or mini_profile.get("occupation")
            ),
            profile_picture_url=_img_url(profile_pic_raw),
            background_image_url=_img_url(background_raw),
            location=location_obj,
            about=profile_raw.get("summary"),
            open_to_work=bool(
                mini_profile.get("openToWork")
                or any(
                    "openToWork" in str(i) for i in included
                )
            ),
            hiring=is_hiring,
            connections_count=str(connections) if connections is not None else None,
            followers_count=int(followers) if followers is not None else None,
            experience=_parse_experience(experience_items, included),
            education=_parse_education(education_items),
            skills=_parse_skills(skill_items),
            certifications=_parse_certifications(cert_items),
            languages=_parse_languages(lang_items),
            honors_awards=_parse_honors(honor_items),
            publications=_parse_publications(pub_items),
            volunteer_work=_parse_volunteer(vol_items),
            projects=_parse_projects(project_items),
        )
