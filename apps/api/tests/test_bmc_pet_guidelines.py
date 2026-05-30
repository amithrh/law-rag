from __future__ import annotations

from scripts.add_bmc_pet_guidelines import _chunks


def test_bmc_pet_guideline_chunk_extraction_keeps_three_focused_anchors():
    fixture = """
    I) WITH RESPECT TO PET DOGS & PET OWNING RESIDENTS:-
    1. Residents' Welfare Associations and Apartment Owners Associations cannot legally introduce any sort of Ban on keeping of Pet dogs/cats.
    8. The Associations cannot disallow the owners of the pets from using lifts.
    II) WITH RESPECT TO STREET DOGS:-
    25. It is illegal for a housing society to pass pet bye laws that disallow pets.
    However, society can make and enforce rules and regulations of keeping dogs to ensure the welfare of pet as well as for safeguarding the interest of the residents.
    For any kind of queries / information required
    It is mandatory for Pet Owners to abide by the terms and conditions of the BMC
    license and various guidelines, rules and circulars issued by AWBI.
    Pet owners must keep the society up to date about his/her pet’s license, vaccinations etc.
    Pet owners can purchase a pedigree dog
    """

    chunks = _chunks(fixture)

    assert [chunk["anchor"] for chunk in chunks] == [
        "bmc-pet-dog-guidelines#pet-dog-residents",
        "bmc-pet-dog-guidelines#housing-society-pet-bylaws",
        "bmc-pet-dog-guidelines#pet-owner-license-and-rwa",
    ]
    assert "cannot legally introduce" in chunks[0]["text"]
    assert "illegal for a housing society" in chunks[1]["text"]
    assert "license" in chunks[2]["text"]
