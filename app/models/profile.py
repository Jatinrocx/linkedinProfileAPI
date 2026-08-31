"""
Pydantic response models for the LinkedIn Profile API.
These define the exact JSON shape returned to the caller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class DateRange(BaseModel):
    month: Optional[int] = Field(None, ge=1, le=12)
    year: Optional[int] = None


class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    full: Optional[str] = None          # Raw string from LinkedIn e.g. "San Francisco, CA"


class Experience(BaseModel):
    company: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    started_at: Optional[DateRange] = None
    ended_at: Optional[DateRange] = None
    is_current: bool = False
    description: Optional[str] = None


class Education(BaseModel):
    school: Optional[str] = None
    school_linkedin_url: Optional[str] = None
    school_logo_url: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    started_at: Optional[DateRange] = None
    ended_at: Optional[DateRange] = None
    description: Optional[str] = None
    activities: Optional[str] = None


class Certification(BaseModel):
    name: Optional[str] = None
    issuing_organization: Optional[str] = None
    issuing_org_logo_url: Optional[str] = None
    issued_at: Optional[DateRange] = None
    expires_at: Optional[DateRange] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class Language(BaseModel):
    name: Optional[str] = None
    proficiency: Optional[str] = None   # e.g. "NATIVE_OR_BILINGUAL", "FULL_PROFESSIONAL"


class HonorAward(BaseModel):
    title: Optional[str] = None
    issuer: Optional[str] = None
    issued_at: Optional[DateRange] = None
    description: Optional[str] = None


class Publication(BaseModel):
    title: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[DateRange] = None
    description: Optional[str] = None
    url: Optional[str] = None


class VolunteerWork(BaseModel):
    organization: Optional[str] = None
    role: Optional[str] = None
    cause: Optional[str] = None
    started_at: Optional[DateRange] = None
    ended_at: Optional[DateRange] = None
    is_current: bool = False
    description: Optional[str] = None


class Project(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    started_at: Optional[DateRange] = None
    ended_at: Optional[DateRange] = None


# ---------------------------------------------------------------------------
# Top-level profile model
# ---------------------------------------------------------------------------


class ProfileData(BaseModel):
    public_id: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    profile_picture_url: Optional[str] = None
    background_image_url: Optional[str] = None
    location: Optional[Location] = None
    about: Optional[str] = None
    open_to_work: bool = False
    hiring: bool = False
    connections_count: Optional[str] = None   # LinkedIn returns "500+" not an int
    followers_count: Optional[int] = None
    experience: list[Experience] = []
    education: list[Education] = []
    skills: list[str] = []
    certifications: list[Certification] = []
    languages: list[Language] = []
    honors_awards: list[HonorAward] = []
    publications: list[Publication] = []
    volunteer_work: list[VolunteerWork] = []
    projects: list[Project] = []


# ---------------------------------------------------------------------------
# API response wrappers
# ---------------------------------------------------------------------------


class ProfileResponse(BaseModel):
    status: str = "success"
    url: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field("voyager", description="'voyager' | 'playwright'")
    profile: ProfileData


class ErrorResponse(BaseModel):
    status: str = "error"
    url: Optional[str] = None
    error: str
    detail: Optional[str] = None
