"""Request bodies and how they turn into the marketer's choices."""

from typing import Any

from pydantic import BaseModel, Field

from factlock.application.service import Choices


class BundleIn(BaseModel):
    target_id: str
    agents: int = Field(ge=1, le=10_000)


class DraftIn(BaseModel):
    target_id: str
    live: bool = True
    include_price: bool = False
    must_include: list[str] = Field(default_factory=list, max_length=10)
    pains: list[str] | None = Field(default=None, max_length=10)
    conditions: list[str] | None = Field(default=None, max_length=20)
    emphasize: list[str] = Field(default_factory=list, max_length=10)
    experience_slot: bool = False


class SlideIn(BaseModel):
    kicker: str = Field(max_length=40)
    headline: str = Field(max_length=120)
    body: str = Field(max_length=400)


class CarouselReviewIn(BaseModel):
    target_id: str | None = None
    slides: list[SlideIn] = Field(max_length=10)
    caption: str = Field(max_length=5000)
    hashtags: list[str] = Field(max_length=40)
    must_include: list[str] = Field(default_factory=list, max_length=10)
    conditions: list[str] | None = Field(default=None, max_length=20)
    emphasize: list[str] = Field(default_factory=list, max_length=10)


class ReviewIn(BaseModel):
    title: str = Field(max_length=300)
    body: str = Field(max_length=60_000)
    target_id: str | None = None
    ai: bool = False
    must_include: list[str] = Field(default_factory=list, max_length=10)
    conditions: list[str] | None = Field(default=None, max_length=20)
    emphasize: list[str] = Field(default_factory=list, max_length=10)


class UserFactIn(BaseModel):
    statement: str = Field(min_length=4, max_length=200)
    kind: str = Field(default="feature", pattern="^(pain|condition|feature)$")


class PlanIn(BaseModel):
    description: str = Field(min_length=2, max_length=200)


def choices_from(body: Any) -> Choices:
    """The marketer's picks from a request body. Missing fields fall back to the defaults."""
    conditions = getattr(body, "conditions", None)
    pains = getattr(body, "pains", None)
    return Choices(
        live=getattr(body, "live", True),
        include_price=getattr(body, "include_price", False),
        must_include=tuple(body.must_include),
        emphasize=tuple(body.emphasize),
        experience_slot=getattr(body, "experience_slot", False),
        pains=tuple(pains) if pains is not None else None,
        conditions=tuple(conditions) if conditions is not None else None,
    )
