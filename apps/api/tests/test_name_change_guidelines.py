from scripts.add_name_change_gazette_guidelines import DOC_ID, _chunks


def test_name_change_guideline_chunk_extraction_keeps_required_anchors():
    text = """
GUIDELINES FOR CHANGE OF NAME FOR ADULT (MAJOR)
The following documents are required for publication of advertisement in the Gazette of India Part-IV
(i) An undertaking duly signed by the applicant.
(ii) Original newspaper.
(iii) Prescribed proforma in duplicate duly typed with signature of applicant and two witnesses.
(iv) C.D. containing the print matter without witness portion in MS Word and type old name in place of signature.
(v) Two self attested passport size photographs and photocopy of ID proof (self attested).
(vi) A certificate duly signed by the applicant declaring therein that the contents of the hard copy and the soft copy are similar.
(vii) Request letter along with requisite fee.
A person attaining the age of 18 years and above who wishes to get his / her change of name published in
the Gazette of India Part-IV has to comply with the following formalities prior to publication of such
advertisement.
1. Change of name should be advertised in one of the daily local leading newspapers stating therein
Father's/ Husband's name along with residential address and forward it in original to this department.
3. Printing matter as prescribed in the attached specimen duly complete in all respects by typing the same
on a separate plain paper and signed by the individual in his/her old name, with two witnesses in duplicate
should be submitted along with soft copy (CD MS Word). The proforma must be computer typed.
For Indians living abroad it is Rs 3500/- only w.e.f. 01/04/2016 to 31/03/2017.
The applicant is requested to download his/her gazette from the website www.egazette.gov.in. in the following manner as the
physical printing and sale of hard copies of the Gazette by the government has been ceased completely.
STEPS TO SEARCH GAZETTE
STEP 1- SEARCH GAZETTE
STEP-2- SEARCH CATEGORY-WEEKLY GAZETTE
STEP-3 IN SELECT PART AND SECTION-PART IV
STEP-6-USE CONTROL KEY+F KEY TO FIND YOUR NAME (OLD /NEW).
The documents once submitted in this department will not be returned in any circumstances.
"""

    chunks = _chunks(text)

    assert [chunk["anchor"] for chunk in chunks] == [
        f"{DOC_ID}#adult-required-documents",
        f"{DOC_ID}#adult-formalities",
        f"{DOC_ID}#egazette-download-and-submission",
    ]
    joined = " ".join(chunk["text"] for chunk in chunks)
    assert "Original newspaper" in joined
    assert "daily local leading newspapers" in joined
    assert "www.egazette.gov.in" in joined
