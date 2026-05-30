from scripts.add_income_tax_43b_h_chunk import SECTION_TEXT, TRANSITION_TEXT


def test_income_tax_43b_chunk_contains_exact_operating_terms():
    normalized = " ".join(SECTION_TEXT.split())
    assert "43B. Notwithstanding anything contained in any other provision of this Act" in SECTION_TEXT
    assert "(h) any sum payable by the assessee to a micro or small enterprise" in SECTION_TEXT
    assert "beyond the time limit specified in section 15" in normalized
    assert "only in computing the income referred to in section 28" in normalized


def test_income_tax_transition_chunk_marks_2026_repeal_and_old_year_savings():
    assert "1961 Act stands repealed on 01.04.2026" in TRANSITION_TEXT
    assert "tax years before April 1, 2026" in TRANSITION_TEXT
    assert "Tax Year 2026-27" in TRANSITION_TEXT
