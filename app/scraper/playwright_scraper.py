"""
Playwright stealth scraper — Layer 2 (fallback).

Used when the Voyager API returns unexpected responses or when
cookies need to be refreshed. Launches a stealth Chromium browser,
injects the li_at cookie, navigates to the profile URL, and parses
the rendered HTML.

Requires:
  playwright install chromium  (done automatically in Dockerfile)
"""

from __future__ import annotations

import logging
import os
import re

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext

from ..models.profile import (
    Certification,
    DateRange,
    Education,
    Experience,
    Language,
    Location,
    ProfileData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Browser / Context management
# ---------------------------------------------------------------------------

_STEALTH_JS = """
() => {
    // Override navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // Override plugins to appear as a real browser
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // Pass Chrome check
    window.chrome = { runtime: {} };
}
"""


from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


async def _make_context(browser: Browser) -> BrowserContext:
    """Create a browser context that looks like a real Chrome user."""
    if _ENV_PATH.exists():
        load_dotenv(dotenv_path=_ENV_PATH, override=True)
    else:
        load_dotenv()
    li_at = os.environ.get("LI_AT", "")
    jsessionid = os.environ.get("JSESSIONID", "")

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="Asia/Kolkata",
        extra_http_headers={
            "accept-language": "en-US,en;q=0.9",
        },
    )

    # Inject stealth patches before any page is loaded
    await context.add_init_script(_STEALTH_JS)

    # Set LinkedIn session cookies
    cookies = []
    if li_at:
        cookies.append({
            "name": "li_at",
            "value": li_at,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
        })
    if jsessionid:
        cookies.append({
            "name": "JSESSIONID",
            "value": jsessionid,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
        })

    if cookies:
        await context.add_cookies(cookies)

    return context


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _safe_text(el) -> str | None:
    if not el:
        return None
    # De-duplicate visually hidden text elements commonly found on LinkedIn
    for hidden in el.find_all(attrs={"aria-hidden": "true"}):
        hidden.decompose()
    text = el.get_text(strip=True)
    return text if text else None


def _parse_date_str(text: str | None) -> DateRange | None:
    """Parse strings like 'Jan 2022' or '2022' into DateRange."""
    if not text:
        return None
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    text = text.strip().lower()
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    year = int(year_match.group()) if year_match else None
    month = None
    for abbr, num in months.items():
        if abbr in text:
            month = num
            break
    if year:
        return DateRange(month=month, year=year)
    return None


def _parse_date_range_str(text: str | None):
    """Parse 'Jan 2020 – Present' or 'Jan 2020 – Mar 2023' into (start, end, is_current)."""
    if not text:
        return None, None, False
    text = text.strip()
    is_current = "present" in text.lower()
    parts = re.split(r"[–—-]", text, maxsplit=1)
    start = _parse_date_str(parts[0].strip()) if parts else None
    end = None if is_current else (_parse_date_str(parts[1].strip()) if len(parts) > 1 else None)
    return start, end, is_current


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_experience_html(soup: BeautifulSoup) -> list[Experience]:
    results: list[Experience] = []
    section = soup.find("section", {"id": "experience"}) or \
              soup.find("div", {"id": "experience-section"})
    if not section:
        return results

    for item in section.find_all("li", class_=re.compile("artdeco-list__item|pv-entity")):
        title_el = item.find(["h3", "span"], attrs={"class": re.compile("t-bold|title")})
        company_el = item.find(["h4", "span"], attrs={"class": re.compile("company|t-normal")})
        loc_el = item.find("span", class_=re.compile("location"))
        date_el = item.find("span", class_=re.compile("date-range|t-black--light"))
        desc_el = item.find(["p", "div"], class_=re.compile("description|summary"))

        date_text = _safe_text(date_el)
        start, end, is_current = _parse_date_range_str(date_text)

        results.append(
            Experience(
                title=_safe_text(title_el),
                company=_safe_text(company_el),
                location=_safe_text(loc_el),
                started_at=start,
                ended_at=end,
                is_current=is_current,
                description=_safe_text(desc_el),
            )
        )
    return results


def _parse_education_html(soup: BeautifulSoup) -> list[Education]:
    results: list[Education] = []
    section = soup.find("section", {"id": "education"}) or \
              soup.find("div", {"id": "education-section"})
    if not section:
        return results

    for item in section.find_all("li", class_=re.compile("artdeco-list__item|pv-entity")):
        school_el = item.find(["h3", "span"], attrs={"class": re.compile("t-bold|school")})
        degree_el = item.find(["h4", "span"], attrs={"class": re.compile("degree|t-normal")})
        field_el = item.find("span", class_=re.compile("field|specialization"))
        date_el = item.find("span", class_=re.compile("date-range|t-black--light"))
        desc_el = item.find(["p", "div"], class_=re.compile("description|activities"))

        date_text = _safe_text(date_el)
        start, end, _ = _parse_date_range_str(date_text)

        results.append(
            Education(
                school=_safe_text(school_el),
                degree=_safe_text(degree_el),
                field_of_study=_safe_text(field_el),
                started_at=start,
                ended_at=end,
                description=_safe_text(desc_el),
            )
        )
    return results


def _parse_skills_html(soup: BeautifulSoup) -> list[str]:
    section = soup.find("section", {"id": "skills"}) or \
              soup.find("div", {"id": "skills-section"})
    if not section:
        return []
    skills = []
    for el in section.find_all("span", class_=re.compile("t-bold|skill-name")):
        text = el.get_text(strip=True)
        if text and text not in skills:
            skills.append(text)
    return skills


def _parse_certifications_html(soup: BeautifulSoup) -> list[Certification]:
    results: list[Certification] = []
    section = soup.find("section", {"id": "certifications"}) or \
              soup.find("div", {"id": "certifications-section"})
    if not section:
        return results

    for item in section.find_all("li", class_=re.compile("artdeco-list__item|pv-entity")):
        name_el = item.find(["h3", "span"], attrs={"class": re.compile("t-bold|title")})
        org_el = item.find(["h4", "span"], attrs={"class": re.compile("org|authority|t-normal")})
        date_el = item.find("span", class_=re.compile("date-range|t-black--light"))
        results.append(
            Certification(
                name=_safe_text(name_el),
                issuing_organization=_safe_text(org_el),
                issued_at=_parse_date_str(_safe_text(date_el)),
            )
        )
    return results


def _parse_languages_html(soup: BeautifulSoup) -> list[Language]:
    results: list[Language] = []
    section = soup.find("section", {"id": "languages"}) or \
              soup.find("div", {"id": "languages-section"})
    if not section:
        return results

    for item in section.find_all("li", class_=re.compile("artdeco-list__item|pv-entity")):
        name_el = item.find(["h3", "span"], attrs={"class": re.compile("t-bold|language-name")})
        prof_el = item.find(["h4", "p"], class_=re.compile("proficiency|t-normal"))
        results.append(
            Language(
                name=_safe_text(name_el),
                proficiency=_safe_text(prof_el),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Main scrape function
# ---------------------------------------------------------------------------

async def scrape_profile(public_id: str) -> ProfileData:
    """
    Scrape a LinkedIn profile using Playwright stealth browser.

    Args:
        public_id: LinkedIn profile slug.

    Returns:
        ProfileData populated from rendered HTML.
    """
    profile_url = f"https://www.linkedin.com/in/{public_id}/"

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-infobars",
                "--window-size=1280,800",
            ],
        )

        try:
            context = await _make_context(browser)
            page = await context.new_page()

            # Block unnecessary resources to speed up loading
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,mp4,mp3}",
                lambda route: route.abort(),
            )

            logger.info("Playwright navigating to: %s", profile_url)
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=45_000)

            curr_url = page.url.lower()
            if "authwall" in curr_url or "login" in curr_url or "signup" in curr_url:
                raise PermissionError(
                    "Playwright was redirected to LinkedIn authwall/login. "
                    "Your LI_AT or JSESSIONID cookie may have expired or is invalid."
                )

            # Wait for the profile sections to render
            try:
                await page.wait_for_selector("main", timeout=10_000)
            except Exception:
                logger.warning("Main element not found in time; continuing anyway")

            html = await page.content()
        finally:
            await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # -----------------------------------------------------------------------
    # Basic info from meta / top section
    # -----------------------------------------------------------------------
    name_el = (
        soup.find("h1", class_=re.compile("text-heading-xlarge|pv-top-card"))
        or soup.find("h1")
    )
    headline_el = soup.find(
        "div", class_=re.compile("text-body-medium|pv-top-card--headline")
    )
    location_el = soup.find(
        "span", class_=re.compile("text-body-small.*t-black--light|pv-top-card--location")
    )
    about_el = (
        soup.find("div", {"id": "about-section"})
        or soup.find("section", {"id": "summary"})
    )
    pic_meta = soup.find("meta", property="og:image")
    pic_url = pic_meta["content"] if pic_meta and pic_meta.get("content") else None

    location_text = _safe_text(location_el)
    location_obj = Location(full=location_text) if location_text else None

    full_name = _safe_text(name_el)
    name_parts = full_name.split(" ", 1) if full_name else ["", ""]

    return ProfileData(
        public_id=public_id,
        full_name=full_name,
        first_name=name_parts[0] if name_parts else None,
        last_name=name_parts[1] if len(name_parts) > 1 else None,
        headline=_safe_text(headline_el),
        profile_picture_url=pic_url,
        location=location_obj,
        about=_safe_text(about_el),
        experience=_parse_experience_html(soup),
        education=_parse_education_html(soup),
        skills=_parse_skills_html(soup),
        certifications=_parse_certifications_html(soup),
        languages=_parse_languages_html(soup),
    )
