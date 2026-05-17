"""Tests for the subject-area inference.

The expanded keyword map (slice + 8 "other" categories) is meant to
guarantee that almost every real Indian judgment gets a label. We test:

1. Slice subjects are still detected correctly.
2. "Other" subjects (constitutional, tax, civil_general, etc.) that
   previously slipped through as None are now tagged.
3. is_slice_subject correctly partitions the slice from the rest.
4. A judgment with multiple subject signals picks the one with the
   strongest evidence.
"""
from __future__ import annotations

import pytest

from ingest.adapters.base import (
    SLICE_SUBJECTS,
    infer_subject_area,
    is_slice_subject,
)


# ---- slice-subject regression tests -------------------------------------

class TestSliceSubjectsStillDetected:
    def test_consumer_protection_judgment(self) -> None:
        text = (
            "The appellant filed a complaint before the District Consumer "
            "Disputes Redressal Forum alleging deficiency in service by the "
            "respondent under the Consumer Protection Act."
        )
        assert infer_subject_area(text) == "consumer"

    def test_family_judgment(self) -> None:
        text = (
            "This is a matrimonial appeal under section 13(1) of the Hindu "
            "Marriage Act, 1955 seeking a decree of divorce on the ground of "
            "cruelty. Custody of the child is also sought."
        )
        assert infer_subject_area(text) == "family"

    def test_criminal_judgment(self) -> None:
        text = (
            "The petitioner sought anticipatory bail under Section 438 CrPC "
            "in connection with an FIR registered under Section 302 of the "
            "Indian Penal Code."
        )
        assert infer_subject_area(text) == "criminal"

    def test_wages_judgment(self) -> None:
        text = (
            "The workmen approached the Industrial Tribunal under the "
            "Industrial Disputes Act seeking termination of service relief "
            "and unpaid Payment of Wages dues."
        )
        assert infer_subject_area(text) == "wages"

    def test_rti_judgment(self) -> None:
        text = (
            "The appellant approached the Central Information Commission "
            "under the Right to Information Act seeking disclosure of "
            "departmental records."
        )
        assert infer_subject_area(text) == "rti"

    def test_motor_judgment(self) -> None:
        text = (
            "The claim petition was filed before the Motor Accident Claims "
            "Tribunal seeking compensation under section 166 of the Motor "
            "Vehicles Act, 1988 for a motor vehicle accident."
        )
        assert infer_subject_area(text) == "motor"


# ---- "other" category coverage (previously silently dropped) ------------

class TestOtherCategoriesNowTagged:
    """Real SC/HC judgments in these areas used to be tagged None. The
    expanded map should catch them. Each is_slice_subject() must be False
    (they're not part of the slice UI), but the tag itself must be present
    so the coverage chip can surface them as "not classified for slice"."""

    def test_constitutional_law(self) -> None:
        text = (
            "The petitioner challenges the impugned order as violating "
            "fundamental rights under Article 14, Article 19 and Article 21 "
            "of the Constitution of India."
        )
        area = infer_subject_area(text)
        assert area == "constitutional"
        assert not is_slice_subject(area)

    def test_tax_law(self) -> None:
        text = (
            "The appeal before the Income Tax Appellate Tribunal (ITAT) "
            "challenges the order under section 271 of the Income Tax Act. "
            "Service tax demand is also disputed."
        )
        area = infer_subject_area(text)
        assert area == "tax"
        assert not is_slice_subject(area)

    def test_company_securities(self) -> None:
        text = (
            "The petition under the Companies Act before the NCLT relates to "
            "a scheme of arrangement involving share capital reduction. SEBI "
            "regulations are also invoked."
        )
        area = infer_subject_area(text)
        assert area == "company_securities"
        assert not is_slice_subject(area)

    def test_property_law(self) -> None:
        text = (
            "Specific performance is sought under the Specific Relief Act "
            "based on an agreement to sell. The defendant disputes the title "
            "to the suit property and pleads encroachment."
        )
        area = infer_subject_area(text)
        assert area == "property"
        assert not is_slice_subject(area)

    def test_service_employment_law(self) -> None:
        text = (
            "The petitioner challenges his dismissal from service following "
            "a departmental enquiry. Promotion and seniority claims are "
            "also raised. He seeks reinstatement with retirement benefits."
        )
        area = infer_subject_area(text)
        assert area == "service_employment"
        assert not is_slice_subject(area)

    def test_civil_general(self) -> None:
        text = (
            "The trial court passed a money decree. The execution petition "
            "under Order XXI of the Civil Procedure Code is the subject of "
            "this revision."
        )
        area = infer_subject_area(text)
        assert area == "civil_general"
        assert not is_slice_subject(area)


# ---- edge cases ---------------------------------------------------------

class TestEdgeCases:
    def test_empty_text(self) -> None:
        assert infer_subject_area("") is None

    def test_no_legal_keywords(self) -> None:
        text = "The weather was pleasant. There was no legal matter to discuss."
        assert infer_subject_area(text) is None

    def test_multi_subject_picks_strongest(self) -> None:
        """A judgment that mentions both family and criminal law picks the
        one with more keyword hits."""
        text = (
            "This Section 498A IPC matter arose during pending divorce "
            "proceedings under the Hindu Marriage Act. The complainant-wife "
            "filed an FIR alleging cruelty under the Indian Penal Code."
        )
        # Both family and criminal score; criminal has more distinct keywords
        # (Section 498A, IPC, FIR, Indian Penal Code) vs family (divorce,
        # Hindu Marriage Act, wife)
        assert infer_subject_area(text) == "criminal"

    def test_short_text(self) -> None:
        """Even a one-line procedural order with one keyword gets tagged."""
        assert infer_subject_area("Anticipatory bail granted.") == "criminal"


# ---- slice partition ----------------------------------------------------

def test_slice_subjects_are_exactly_the_six_named() -> None:
    assert SLICE_SUBJECTS == frozenset({
        "consumer", "family", "criminal", "wages", "rti", "motor",
    })


def test_is_slice_subject_partitioning() -> None:
    for s in ("consumer", "family", "criminal", "wages", "rti", "motor"):
        assert is_slice_subject(s) is True
    for s in (
        "constitutional", "tax", "company_securities", "property",
        "service_employment", "civil_general", "land_revenue", "election",
        "education",
    ):
        assert is_slice_subject(s) is False
    assert is_slice_subject(None) is False
