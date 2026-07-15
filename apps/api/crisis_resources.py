"""Crisis/support resources shown by safety-first route cards.

These are not legal authorities. They are operational support resources and
must be reviewed before public deployment because helplines can change.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrisisResource:
    name: str
    contact: str
    availability: str
    source_url: str
    last_verified: str

    def portal_label(self) -> str:
        return f"{self.name}: {self.contact} ({self.availability}; verified {self.last_verified})"


INDIA_SELF_HARM_CRISIS_RESOURCES: tuple[CrisisResource, ...] = (
    CrisisResource(
        name="AASRA",
        contact="+91-22-27546669",
        availability="24x7",
        source_url="https://www.aasra.info/",
        last_verified="2026-06-04",
    ),
    CrisisResource(
        name="KIRAN",
        contact="1800-599-0019",
        availability="24x7 national mental-health rehabilitation helpline",
        source_url="https://pib.gov.in/PressReleasePage.aspx?PRID=1652240",
        last_verified="2026-06-04",
    ),
    CrisisResource(
        name="Vandrevala Foundation",
        contact="+91 9999 666 555",
        availability="24x7x365 crisis intervention helpline",
        source_url="https://www.vandrevalafoundation.com/free-counseling/contact-us",
        last_verified="2026-06-04",
    ),
)


def india_self_harm_portal_labels() -> list[str]:
    return [resource.portal_label() for resource in INDIA_SELF_HARM_CRISIS_RESOURCES]


__all__ = ["CrisisResource", "INDIA_SELF_HARM_CRISIS_RESOURCES", "india_self_harm_portal_labels"]
