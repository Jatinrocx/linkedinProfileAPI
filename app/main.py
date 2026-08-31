"""
FastAPI application — LinkedIn Profile API.

Endpoints:
  GET  /                        Health check
  GET  /api/profile?url=...     Fetch profile (GET, for easy browser testing)
  POST /api/profile             Fetch profile (POST, accepts JSON body)
  GET  /docs                    Auto-generated Swagger UI (FastAPI built-in)
  GET  /redoc                   ReDoc API documentation (FastAPI built-in)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

# Load .env file automatically from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE, override=True)
else:
    load_dotenv()

# Fix Playwright asyncio subprocess error on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from .models.profile import ErrorResponse, ProfileResponse
from .scraper import playwright_scraper, voyager
from .utils.url_parser import extract_public_id, is_valid_linkedin_url, normalize_url

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache  (avoids hammering LinkedIn for repeated lookups)
# ---------------------------------------------------------------------------

_CACHE: dict[str, tuple[float, ProfileResponse]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_get(key: str) -> ProfileResponse | None:
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _cache_set(key: str, value: ProfileResponse) -> None:
    _CACHE[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# Lifespan (startup/shutdown hooks)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LinkedIn Profile API starting up ✅")
    yield
    logger.info("LinkedIn Profile API shutting down 🛑")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LinkedIn Profile API",
    description=(
        "Reverse-engineered LinkedIn Profile API. "
        "Accepts a LinkedIn profile URL and returns structured JSON "
        "containing name, headline, location, about, experience, "
        "education, skills, certifications, languages, and profile images."
    ),
    version="1.0.0",
    contact={
        "name": "LinkedIn Profile API",
        "url": "https://github.com/YOUR_USERNAME/linkedinProfileAPI",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
)

# Allow all origins for the hiring challenge (easy to test from anywhere)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------

class ProfileRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not is_valid_linkedin_url(v):
            raise ValueError(
                "Invalid LinkedIn profile URL. "
                "Expected format: https://www.linkedin.com/in/<username>"
            )
        return v


# ---------------------------------------------------------------------------
# Core fetch logic (shared by GET and POST handlers)
# ---------------------------------------------------------------------------

async def _fetch(url: str) -> ProfileResponse:
    """Fetch a LinkedIn profile, trying Voyager then Playwright as fallback."""
    public_id = extract_public_id(url)
    canonical_url = normalize_url(url)

    if not public_id or not canonical_url:
        raise HTTPException(status_code=400, detail="Could not parse LinkedIn profile URL")

    # Check cache first
    cached = _cache_get(public_id)
    if cached:
        logger.info("Cache hit for: %s", public_id)
        return cached

    source = "voyager"
    try:
        logger.info("Attempting Voyager API for: %s", public_id)
        profile_data = await voyager.fetch_profile(public_id)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as voyager_err:
        logger.warning(
            "Voyager API failed for %s (%s), falling back to Playwright",
            public_id,
            voyager_err,
        )
        source = "playwright"
        try:
            profile_data = await playwright_scraper.scrape_profile(public_id)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except Exception as pw_err:
            pw_msg = str(pw_err).lower()
            if "too_many_redirects" in pw_msg or "authwall" in pw_msg or "login" in pw_msg:
                raise HTTPException(
                    status_code=401,
                    detail="LinkedIn session cookies (LI_AT / JSESSIONID) have expired or are invalid.",
                )
            logger.error("Playwright fallback also failed: %s", pw_err)
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Both scraping methods failed. "
                    f"Voyager error: {voyager_err}. "
                    f"Playwright error: {pw_err}"
                ),
            )

    response = ProfileResponse(url=canonical_url, source=source, profile=profile_data)
    _cache_set(public_id, response)
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint — confirms the API is running."""
    return {
        "status": "ok",
        "service": "LinkedIn Profile API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get(
    "/api/profile",
    response_model=ProfileResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid LinkedIn URL"},
        401: {"model": ErrorResponse, "description": "LinkedIn credentials expired"},
        502: {"model": ErrorResponse, "description": "Scraping failed"},
    },
    tags=["Profile"],
    summary="Fetch a LinkedIn profile (GET)",
    description=(
        "Accepts a LinkedIn profile URL as a query parameter and returns "
        "structured JSON with all available profile information."
    ),
)
async def get_profile(
    url: str = Query(
        ...,
        description="LinkedIn profile URL (e.g. https://www.linkedin.com/in/williamhgates)",
        examples={"Bill Gates": {"value": "https://www.linkedin.com/in/williamhgates"}},
    )
):
    """Fetch a LinkedIn profile via GET request."""
    if not is_valid_linkedin_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid LinkedIn profile URL. Expected: https://www.linkedin.com/in/<username>",
        )
    return await _fetch(url)


@app.post(
    "/api/profile",
    response_model=ProfileResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid LinkedIn URL"},
        401: {"model": ErrorResponse, "description": "LinkedIn credentials expired"},
        502: {"model": ErrorResponse, "description": "Scraping failed"},
    },
    tags=["Profile"],
    summary="Fetch a LinkedIn profile (POST)",
    description=(
        "Accepts a JSON body with a `url` field containing a LinkedIn profile URL."
    ),
)
async def post_profile(request: ProfileRequest):
    """Fetch a LinkedIn profile via POST request."""
    return await _fetch(request.url)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                status="error",
                error=str(exc.detail),
                detail=f"HTTP {exc.status_code}",
            ).model_dump(mode="json"),
        )
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            status="error",
            error="Internal server error",
            detail=str(exc),
        ).model_dump(mode="json"),
    )
