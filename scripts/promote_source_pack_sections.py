#!/usr/bin/env python3
"""Promote exact, source-pack sections from pinned official Act artifacts.

This utility is intentionally partial-document. Existing source-pack documents
may have useful text but no chunk-level provenance proof. It pins one official
artifact, preserves the predecessor source, and adds only the named section
starts as verified ``-official`` chunks. All other legacy chunks remain
ineligible for production retrieval.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from apps.api.config import get_settings  # noqa: E402
from apps.api.embeddings import (  # noqa: E402
    embedding_to_halfvec_literal,
    get_embedder,
    sparse_to_jsonb,
)
from chunking.act import chunk_act  # noqa: E402
from ingest.normalize.redact import sanitize_for_db  # noqa: E402
from scripts.verify_provenance import extract_pdf_text, refetch_act_pdfs  # noqa: E402


@dataclass(frozen=True)
class PromotionSpec:
    # New manifests may resolve the predecessor from the stable document id;
    # older entries retain an integer for compatibility with existing tests.
    source_id: int | None
    source_url: str
    source_sha256: str
    source_bytes: int
    document_id: str
    title: str
    sections: tuple[str, ...]
    subject_area: str
    expected_origin: str = "indiacode"
    accepted_source_urls: tuple[str, ...] = ()
    accepted_source_filenames: tuple[str, ...] = ()
    accepted_predecessor_origins: tuple[str, ...] = ()
    allow_unpinned_predecessor: bool = False
    allow_hash_only_predecessor: bool = False
    promote_to_new_source: bool = False
    requires_dated_as_at: bool = False
    section_text_sha256: tuple[tuple[str, str], ...] = ()
    local_artifact_path: str | None = None
    supplement_document_id: str | None = None


_STREET_VENDOR_LOCAL_URL = (
    f"file://{ROOT}/data/raw/acts/street-vendors-2014__a2014-07.pdf"
)
_SCST_POA_LOCAL_URL = (
    f"file://{ROOT}/data/raw/acts/sc-st-poa-1989__aA1989-33.pdf"
)
_STREET_VENDOR_URL = "https://www.indiacode.nic.in/bitstream/123456789/2124/1/a2014-07.pdf"

_CONSTITUTION_ARTICLES = {
    "21": {
        "title": "Protection of life and personal liberty",
        "proof": "No person shall be deprived of his life or personal liberty",
        "next": "21A",
    },
    "341": {
        "title": "Scheduled Castes",
        "proof": "specify the castes, races or tribes or parts of or groups within castes, races or tribes",
        "next": "342",
    },
    "342": {
        "title": "Scheduled Tribes",
        "proof": "specify the tribes or tribal communities or parts of or groups within tribes or tribal communities",
        "next": "342A",
    },
}


SPECS = (
    PromotionSpec(
        source_id=46,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/1798/1/aA1988-59.pdf",
        source_sha256="be5bac906607cb2ac902d5c113c42c7f89142be3591a81ccb825cfbb7ee5d50d",
        source_bytes=3740289,
        document_id="motor-vehicles-1988",
        title="TheMotorVehiclesAct,1988",
        sections=("3", "19", "66", "74", "80", "86", "130", "200", "206"),
        subject_area="business_license",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/1798",),
        promote_to_new_source=True,
        section_text_sha256=(
            ("3", "874fa3f03d4f6e47eac0e0a2269fe8908a0a237971e64fe98aaf5ee59ae4bd6b"),
            ("19", "43beeb40d0815f3f882c475b4dae343021738aeea6a7dda8ffb4c347fac3a901"),
            ("66", "0e088f7c21fcafb44aa25381c1df2e31e1557cf1227a162f2dbad3827de7eaef"),
            ("74", "54b7b8a5623717db61ab35e3eb689ae23af076c047a9f3375ec6fe5a31a8107e"),
            ("80", "e7e34d64cd8bc9fa4ba0d451ae6a51374bdf2ab31c2149dbeb2bc530c088ebb1"),
            ("86", "3423a0007cc9c59c698cdf7f2960260d3ac57e707d0c79d00cd32c808e83ab23"),
            ("130", "5bdbd9db7b6a1bfb70a6b077a678d61730ea48adabdfdca95b96d361976cb36e"),
            ("200", "3b77825752c81cedeaea339950c9edefe075c00e5a4869b3661321f9fc76cc93"),
            ("206", "2a0b473f6cbef031e2f4aaeec88a7adc6f10bba8b4ca65db07d904559cefc074"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/motor-vehicles-1988__aA1988-59.pdf"),
    ),
    PromotionSpec(
        source_id=45,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2065/1/aa2005.pdf",
        source_sha256="8956eaba5db4079674bc16e50c14b210e8872c28e8a18f458f01a8fbcdde1479",
        source_bytes=355456,
        document_id="rti-2005",
        title="Right to Information Act 2005",
        sections=("6", "7", "19"),
        subject_area="constitutional",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2065",),
        promote_to_new_source=True,
        section_text_sha256=(
            ("6", "caccf4f1e06cc6bbe263eb6b4aa9b03b0bb96e8eada99320c5485931c424792e"),
            ("7", "ccf5a4d08bab4dee05fd50ed5c1b996bd083b134e449267e6b0436705d07d4c4"),
            ("19", "b7201b045ab73554603179b79fd7f525834eadf6cd186a05a51b7017670aecbf"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/rti-2005__aa2005.pdf"),
    ),
    PromotionSpec(
        source_id=120,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2155/1/a2016-49.pdf",
        source_sha256="e848a1813ed453aeede7c1dea2c8df7c285bb8a7e626803051bd307e6cd33a62",
        source_bytes=322509,
        document_id="rpwd-2016",
        title="Rights of Persons with Disabilities Act 2016",
        sections=("7", "12", "13", "20", "21", "89"),
        subject_area="disability_access",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2155",),
        promote_to_new_source=True,
        section_text_sha256=(
            ("7", "586708c9dedf508049ef320282760046745a0be5e5a7d80f1419cb2fa6000387"),
            ("12", "5d404f2b19224c1bb254290539d3a1b7bc8934417a7587cc56787f07ab072a61"),
            ("13", "233773f2cf6e4d449a361bc19f761aa1f6996966d6680888a6c1846daf2abf43"),
            ("20", "1b11a02ebe73c649e65ff6c4af1a062d8fb752049a1533bf4b334a344171dbe4"),
            ("21", "636758d6cc9ef7aee16e209a0dc8d7afdfa4d855aa71b0f6f21fbed949b8c415"),
            ("89", "62d684d206abb8e24238def0e93371c1ca8ab9b9b7a570eaf3116119d33b296a"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/rpwd-2016__a2016-49.pdf"),
    ),
    PromotionSpec(
        source_id=306,
        source_url=_STREET_VENDOR_URL,
        source_sha256="7159519e0a5ce6c7ee6e2cc553121f78926fca578a84fabecd86965304d8650c",
        source_bytes=229499,
        document_id="street-vendors-2014",
        title="Street Vendors (Protection of Livelihood and Regulation of Street Vending) Act 2014",
        sections=("3", "4", "11", "18", "19", "20", "28", "36", "37"),
        subject_area="street_vendor_municipal",
        accepted_source_urls=(_STREET_VENDOR_LOCAL_URL,),
        promote_to_new_source=True,
        section_text_sha256=(
            ("3", "15db0aaa42d554c08fd6eedd39d300e44239df95d7dabd53bd88924dd7efeb21"),
            ("4", "b917349c8c078aceabcfe323a54d39c5aed24d7cebd8b025abc1a90ec082ec8d"),
            ("11", "bc235bb7d9ffbc5fde389f98e2f49dd03fd3eb49eb959f1297fc46ab7daecee4"),
            ("18", "d10eb5e99f16b825739359e49c9814950cb6c152948a90cf3c57903e53ad5069"),
            ("19", "f3ad16cb1178b0b44122ce39418fd43eeb01d7104e273a0c5a341173cf42a4c0"),
            ("20", "b949c3c4cf82a2fb5f509eea73ca30b51126d6322af8bb57b5e74e81ad554900"),
            ("28", "12e33b35d702a541f4b0554247ace5f0a5ccf39ce19b02ee9dfb39b64357b0f7"),
            ("36", "723f82109bc0171b616425030b7a286012bf27c73d77bc14dfff0a4d198c00bd"),
            ("37", "4c70e4f28eab976e0748bd1393696eb19d72cac7046ced64a14ea27adf40c00a"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/street-vendors-2014__a2014-07.pdf"),
    ),
    PromotionSpec(
        source_id=682,
        source_url="https://www.legislative.gov.in/static/uploads/2025/07/c9fe9c9b6840524844316f74bb1c556c.pdf",
        source_sha256="4c8e93689ec245e26db08e22b5ff3ad645c98736f0e5b7c8b6638acd7861f85b",
        source_bytes=2684622,
        document_id="constitution-india",
        title="Constitution of India",
        sections=("21", "341", "342"),
        subject_area="constitutional",
        expected_origin="legislative_department",
        section_text_sha256=(
            ("21", "bd183d8b9278688cf293a5a1ce31334cfec3f20426814a077ca944b613348a43"),
            ("341", "7d115360d88199a9e5d28f0580c6573c45e583fce447d25016bf5b75cdcd546a"),
            ("342", "bc1d4d2b27e1cbc59308fd1594b8c6040291074fb2e2777ae5a7f95b744d2161"),
        ),
    ),
    PromotionSpec(
        source_id=48,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2021/5/A2005-43.pdf",
        source_sha256="17ea6d7cb89fcae52825ec4b15f61e5573285ae9d6eca6937665161afcdad9b1",
        source_bytes=267233,
        document_id="domestic-violence-2005",
        title="Protection of Women from Domestic Violence Act 2005",
        sections=("2", "3", "12", "17", "18", "19", "20", "27", "29"),
        subject_area="family",
        accepted_source_urls=(
            "https://www.indiacode.nic.in/handle/123456789/5560",
            "https://www.indiacode.nic.in/handle/123456789/12904",
        ),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("2", "fe2bc3779d26f9087d7590f3b75bba3e898aa015e4ce7866bbb0bfeaf41cf46d"),
            ("3", "2d2d2655ada24c2f53b9d4d79e8f061830a8934f41a6bb036deeebb5af4a6b3f"),
            ("12", "5eaea7eccc664426bd7e7c4f370b90bde388fe8a6ad7b89aa458043ad6dfdc38"),
            ("17", "9b1b72a31eff002ca6458baa14911841e4eeb30db1bd8c2d1357c6e6e58bb470"),
            ("18", "48592de561424dc195ac113c7714f353caf22566739ee740d8bdb2f53a45adf4"),
            ("19", "f0b3d41f5b3b69e0db56683f246ed7114c77c91b8c5f4c43dc8794e2f8efd7ed"),
            ("20", "11f8eab83a40796155544de4eb3747f71450ff3296d7519c16c0c1c064690e6d"),
            ("27", "3ae1f1c6e5daa56e35157e68c5f1cba19fc01c5aa2d547db0789d39fe37cd698"),
            ("29", "4c5115125e74757657828e51ed43b52a1697e317d4707ac5a93f0ca3b8c1a538"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/domestic-violence-2005__A2005-43.pdf"),
        supplement_document_id="domestic-violence-2005-official",
    ),
    # These three Acts were already present in the local corpus, but their
    # controlling sections remained ineligible because their old source
    # records were either unverified handles or a partial legacy projection.
    # Promote only the sections needed by the released high-risk workflows.
    PromotionSpec(
        source_id=699,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15272/1/the_code_of_criminal_procedure%2C_1973.pdf",
        source_sha256="5bb6514251a9ec6375b2c894cef5280dab0d1c3cca1e0f4a1e57f29b54033d72",
        source_bytes=1879339,
        document_id="crpc-1973",
        title="Code of Criminal Procedure 1973",
        sections=("167", "482"),
        subject_area="criminal",
        section_text_sha256=(
            ("167", "0ca6e6dcb327486d65b3dbd267dbec0c5ec43a547343caf97392c54306d44870"),
            ("482", "d8d5edf049428c3b6ab3377ee71b28de6137efadadd2b1946c9d1776c6eccd20"),
        ),
    ),
    PromotionSpec(
        source_id=86,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/17101/1/jjact_2015.pdf",
        source_sha256="2ac79c3465b7f4ed21a716e2c86408f954737f588a71a96c75e51fac2eaeeca0",
        source_bytes=231629,
        document_id="jj-2015",
        title="Juvenile Justice (Care and Protection of Children) Act 2015",
        sections=("9", "10", "12", "56", "57", "58", "59", "62", "63", "94"),
        subject_area="criminal",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/17101",),
        promote_to_new_source=True,
        section_text_sha256=(
            ("9", "904b0bc674eb4b4df40d4b769e4ee30e96d54a04564c461b5d81ba76f43df4c4"),
            ("10", "3d1651540123a345e82fc122c862dfe72b64b9ad34fe6c78912c9cecbb5ec1e7"),
            ("12", "4b39ef74dc9b08ed9a9cc4de6f50cfb04c077a1286e65e12d70576cc8086c12e"),
            ("56", "d7f65b8eb27897dc941f0af63a109bc572d8bf264a6a8f05eeda45b331589f42"),
            ("57", "350c95a31e5652cfe63a0cd6903e541cde2acc80cd266e2eab30d6de42ac7f13"),
            ("58", "209b1e7487474c68d3cf98eb23115fe2311be99b860b37bfa9946753a5b6e07f"),
            ("59", "826f78ea3ccd21af8d2a917ce440f70bcacdb2553f9a99eac02834825e402f05"),
            ("62", "0421dac55f941c10f93092ec437f868e9190c6acdac9885062fb2045a950dd14"),
            ("63", "87c2e0a5e8f41202dc410da6bf32a21cde07b871f4c01da7576a2b066911da4c"),
            ("94", "3e20f0fdd7bd7bc0b049e7e984fb10ac697588e8edf9b9910f9bca009a34e0fc"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/jj-2015__jjact_2015.pdf"),
    ),
    PromotionSpec(
        source_id=92,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2435/1/a1961-43.pdf#section-139AA",
        source_sha256="428b1b3cf2c3c09f22014d488f60eb0aebe209fffbf63ae6430d4a6644bd55eb",
        source_bytes=6232336,
        document_id="income-tax-1961",
        title="Income-tax Act 1961",
        sections=("139AA",),
        subject_area="tax",
        promote_to_new_source=True,
        accepted_source_urls=("https://www.indiacode.nic.in/bitstream/123456789/2435/1/a1961-43.pdf",),
        section_text_sha256=(
            ("139AA", "a91a9e34e5be32aeafd2cca9cd1867061f4a442ba27b2856353dfb3a85f6b49f"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/income-tax-1961__a1961-43.pdf"),
        supplement_document_id="income-tax-1961-official",
    ),
    # These are supplements rather than replacements: the existing local
    # documents remain untrusted, while only the exact sections below become
    # eligible through a separately pinned first-party artifact.
    PromotionSpec(
        source_id=346,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2325/1/AA1894___09.pdf",
        source_sha256="33cbdb98fe2155d9d633e9f20244da28679596bd0bc9d15f61b67068872b1033",
        source_bytes=310707,
        document_id="prisons-1894",
        title="Prisons Act 1894",
        sections=("13", "14", "37", "38", "39"),
        subject_area="criminal",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2325",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("13", "319b36e62f3890e6b36d091aab14e71ca5a238963e4e26a002e00ef1496e7c5c"),
            ("14", "6dc43a742d3b02ff2a3d478c4420655206fa2aa88e78cc95a2cf76e1f7420c48"),
            ("37", "16c8579db219cb9bb2696e71ef47c787e63b2d518984aa318b22a41ae9973b0c"),
            ("38", "0cd8356c9a06b0c467942886b2fb7d5aeb6e97fb7c6afa250a3e8a597623bb4d"),
            ("39", "037e571260f3de9e8acc30e568c31438c7d2d29d51d458191bd6feecc83ed0a6"),
        ),
        supplement_document_id="prisons-1894-official",
    ),
    PromotionSpec(
        source_id=336,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/1920/1/aA1989-33.pdf",
        source_sha256="b52783c516d99d3c1d117bc45420c4d3a0c2cdc1d9814f80e5dfb68cf9623e27",
        source_bytes=370806,
        document_id="sc-st-poa-1989",
        title="Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
        sections=("3", "4", "14", "15", "15A", "18", "18A"),
        subject_area="tribal_caste_atrocity",
        accepted_source_urls=(_SCST_POA_LOCAL_URL,),
        accepted_predecessor_origins=("direct",),
        promote_to_new_source=True,
        section_text_sha256=(
            ("3", "3ca93d9a4ad385fa98e68f73189cb69bb06a701eb438e0eea31b573d0ad0a449"),
            ("4", "904cc059b9ee9784693736ff764d28d08a56057c43634d96ce695740d62ccd83"),
            ("14", "b7d68a2dd0a4db4bfa3ed9104bfdefdb29cc45b338f6a9597d3c668da4573ac7"),
            ("15", "afbfa12d68d7fd0b6cf2c77a27843ad6ce94706ec626e777654938dba9271237"),
            ("15A", "753d8d47a0e2b893786f4ba097073d71ee7fbce981bfc7dd9179a43fe7749730"),
            ("18", "44e8237e8ff1006afb058b2d15a7a6477830d2627cef670f8a0c27416d687eef"),
            ("18A", "2d9160e3a29a4e3f68aaa07bd9173867d7b8e4baa3f2e65e9ea82c203169e6db"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/sc-st-poa-1989__aA1989-33.pdf"),
        supplement_document_id="sc-st-poa-1989-official",
    ),
    PromotionSpec(
        source_id=101,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/1925/1/198739.pdf",
        source_sha256="3aae5d5c9f8c2ad100c0553c351af559e35fb36c3fc68a921fd1e64dd4a9318f",
        source_bytes=160490,
        document_id="legal-services-authorities-1987",
        title="Legal Services Authorities Act 1987",
        sections=("9", "12", "19", "20", "21"),
        subject_area="constitutional",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/12883",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        requires_dated_as_at=True,
        section_text_sha256=(
            ("9", "ad4ca41db2786d7c100063c3e266643038b6e4988e5a4b118aa1b5905f477db1"),
            ("12", "b02c52eca7b3544426c1abca4d4526676e113d9be79a4f0ee8013c8c35488328"),
            ("19", "9fc8e8428eff67014efb0cf739c2afa7e765d2e04c7bceaeb81326849bf7ef06"),
            ("20", "4d8efed8062232f031fc5ff5f4138a533d985815fe5c2bf60b6dac5a28a6b268"),
            ("21", "038579822114caa40a4af5068c9291d3729735fb2167c9d206a1eac5217d236d"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/legal-services-authorities-1987__198739.pdf"),
    ),
    PromotionSpec(
        source_id=679,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf",
        source_sha256="e71725fa32e892f887308816046c42275fc855b5cbb4ee1063cdbd518f165140",
        source_bytes=832355,
        document_id="it-2000",
        title="Information Technology Act 2000",
        sections=("66C", "66D", "66E", "67", "67A", "67B", "69", "69A", "79", "90"),
        subject_area="civil_general",
        section_text_sha256=(
            ("66C", "aafe64bf0fd3da0c74905bb567d907b99c140c1f35edccf76c8d527e7c51d2bb"),
            ("66D", "31e94eeb70358306844b6abadd12d062df920ac2bd15d7658e88252837e70cfa"),
            ("66E", "6f7a614aea218f7ac853382e47454f8340d1ee5f7fc6f64c2dc4c76e6390eea7"),
            ("67", "e7e09663584a3f55ac04d58e1aff5fd4be03f506477a85a1e66982618086b435"),
            ("67A", "cb5eaafeec83b40682e4f9c938abe9a29281a46e90daae0aa936eac3c6fc9361"),
            ("67B", "cb975c4aacd36af3a1e65dc4e0ff59536af8c0999cd7a470fbb0046cb82555b6"),
            ("69", "7d35375fb394e7409a339dbef1b2f4b9de6dd26fc18c1d19966f47a3cbcf5c8f"),
            ("69A", "df9112e96471a4c97963cc47159186ca316703cb55ccb830c8010c06b5f6e6fe"),
            ("79", "9b1129bd917e78fe4d6f34a5a2c528d80c711803459c27d2b7f417c760a033d9"),
            ("90", "03194d37db6caada0539f72403f23c8dcd8eae63b58cfebc1099283d90779998"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/it-2000__it_act_2000_updated.pdf"),
    ),
    PromotionSpec(
        source_id=112,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/19243/1/a1956-104.pdf",
        source_sha256="4174149c01dac6d0e4c8845dd80d45b1e106107d9913cedfccb71e507e6672ca",
        source_bytes=306671,
        document_id="itpa-1956",
        title="Immoral Traffic (Prevention) Act 1956",
        sections=("4", "5", "6", "7", "8", "17"),
        subject_area="criminal",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/20019",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("4", "1bb4bdb17ca3c3a804efeb201cb326b3a38f41b3633b599edb6cdddfd545e445"),
            ("5", "006d47d3c369c2ace098ac6cffc6cb06312dc0023d7dbc53818fb2294d4bd9ef"),
            ("6", "afa97aa20ff05e9107b179217dba77cc8a35a96bf9b4304b1be278cffa986efe"),
            ("7", "39361d8a45ddf07b31f9746f8dd557614978c7237a653eff4197f173af6bd1a1"),
            ("8", "fc96ee555938f84a081853d68524723d17330d28d93135063b2d8ead6da3eb38"),
            ("17", "78639f998ba5b9643a2b798d5c900572f82f98e3d241c05a6e723059ed64e782"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/itpa-1956__a1956-104.pdf"),
    ),
    PromotionSpec(
        source_id=309,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/6930/1/the_mahatma_gandhi_national_rural_employment_guarantee_act%2C_2005.pdf",
        source_sha256="3fe1d5cff3243505347034f1901b8f43fe5e1bb7ccab6cfe93e06be4562bff3a",
        source_bytes=13593204,
        document_id="mgnrega-2005",
        title="Mahatma Gandhi National Rural Employment Guarantee Act 2005",
        sections=("3", "6", "7", "15", "17", "19", "23", "27", "35"),
        subject_area="service_employment",
        accepted_source_urls=(
            "file:///Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc/data/raw/acts/mgnrega-2005__the_mahatma_gandhi_national_rural_employment_guarantee_act_2005.pdf",
        ),
        promote_to_new_source=True,
        section_text_sha256=(
            ("3", "13b706fe3167ee55fa78a8a9c86552db26531c44b90e752d3eac603f4623f665"),
            ("6", "4cdedd1310994f37ebf7d51ff23569e9b3509885a71c06b26f1527b9c0123705"),
            ("7", "861279a7efcc5b1bc86511e5785b077bcbec86116803a57ec812099cb563deee"),
            ("15", "a0813c0f568e14d1fbfc926fb22f946ae5ac5e106915849ca8bb2cd0347a421a"),
            ("17", "c39fe649ed5e84b5fe0afb7e92cf6e503363df81f068b7c370c3d6d34565ca53"),
            ("19", "d5827cd20be9f91113cb128ae779822e74bd4163b1bedb4c7157d94cb3b98fb0"),
            ("23", "d7c3aa4dfea182422e1a004591e76389a380b64c2cb566adb450f128b9385678"),
            ("27", "c43a1ddcf7ff4fa7693f3986866c3055bc993cf91decead7b558d4cbf8c8f448"),
            ("35", "a243acf57b0e40b95d7dfe339236b7058f8c1c4d26b58df1c9a0d0f8ebcd78b6"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/mgnrega-2005__the_mahatma_gandhi_national_rural_employment_guarantee_act_2005.pdf"),
    ),
    PromotionSpec(
        source_id=81,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/1713/1/AAA1956suc___30.pdf",
        source_sha256="8ee27226825b90210a3c17646049cb3e73cb2e32fd92d7d8c857e8808adb3ca2",
        source_bytes=257077,
        document_id="hindu-succession-1956",
        title="Hindu Succession Act 1956 (with 2005 amendment)",
        sections=("6", "8", "10", "14", "15"),
        subject_area="family",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/1713",),
        allow_unpinned_predecessor=True,
        allow_hash_only_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("6", "23e4e2ff048462a6dc91d913b0222dbc292899091cf9e7dc6900253e7aebe3c0"),
            ("8", "c80a21867857b9e163edd6fb51874dbd00e00d9d2c8873bf48616197bc15d889"),
            ("10", "81792035da90874ee2da661c2171f6a80aaddc15830954b9575d8358291ff3a9"),
            ("14", "852de1a162dfc306b2a74841d3b5d1613c30ca6d27ae517858dd6678bbb321ac"),
            ("15", "929136369d978b4e84689b5ce7ff1f9402bfe9a6e415815c909e9b685c2e50b2"),
        ),
        local_artifact_path=str(ROOT / "data/raw/acts/hindu-succession-1956__AAA1956suc___30.pdf"),
    ),
    # Stage 38: the final-500 audit found these national source packs in the
    # corpus but still fail-closed because their predecessor sources have no
    # byte-level provenance. Keep the batch section-scoped. In particular, do
    # not promote the stale cached IBC/Copyright PDFs: their bytes differ from
    # the current official India Code artifacts, so those two specs refetch
    # and verify the pinned URL at promotion time.
    PromotionSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2154/1/A201631.pdf",
        source_sha256="d13ef44426184e496133029f601b63412dea188bc36a23f90b0b719c16c5f000",
        source_bytes=1324694,
        document_id="ibc-2016",
        title="Insolvency and Bankruptcy Code 2016",
        sections=("7", "8", "9", "54A", "61"),
        subject_area="company_securities",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2154",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("7", "c815d13f344b6bb4b215189ad988a056976c64aa90f5169e2495338a64c8a6f0"),
            ("8", "7c4e1d6a65679cfeb29aef7c65dd4a26ee532e1b4d444d341bf25a28c902d529"),
            ("9", "fb7ad0357cd353def4a58e47404b57c5c6ca0a05911ade005e94c2615364e1fa"),
            ("54A", "ebc32bf09d701ea57d1cacc2e320cbf4c712a3b1c022d93c0228076c87d17ad4"),
            ("61", "c78c0d1e183d13cbd288f1e7ce85ed0ca9ed6579d7780b82e526dafe15406aee"),
        ),
    ),
    PromotionSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/1367/1/A195714.pdf",
        source_sha256="da4144b68419cf81bbf10979183ed1cf3fbe3795188995d1efc85fd7d65713bd",
        source_bytes=593425,
        document_id="copyright-1957",
        title="Copyright Act 1957",
        sections=("51", "52", "55", "63"),
        subject_area="civil_general",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/1367",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("51", "a3bd64ab1ba44c5d6537d1365686d5063aaef3f49ec44896a2a7aa23e732f30b"),
            ("52", "ee18ef029ca2acf0e7ead5127a24282cbaf6464b80033e4533a33148b7f2cb77"),
            ("55", "ea20729ac60818df4ed01cde75fe9b4b94b45c1352bbe8229dde6d6008bcb716"),
            ("63", "fabcbd7ef70e196c8657250755cd3edae7f4098fd9922a13705f9ab510dc1ebb"),
        ),
    ),
    PromotionSpec(
        source_id=None,
        source_url=(
            "https://www.indiacode.nic.in/bitstream/123456789/12869/1/"
            "the_family_courts_act_1984_no._66_of_1984_dt._14-09-1984.pdf"
        ),
        source_sha256="cba57aa38f39862176fbad1b42f7af65da2c19bfddc25dbbf4e7072d7b24981c",
        source_bytes=277490,
        document_id="family-courts-1984",
        title="Family Courts Act 1984",
        sections=("7", "8", "9"),
        subject_area="family",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/12869",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("7", "444f39ccac0ffdfa9260be435a5426ff958b3bbcb4577a9c35ca2e8c52645f81"),
            ("8", "77c47e5a837f8023b7a07314a9f495ad9b949ca47616ddedf0d1e706bf9bef81"),
            ("9", "be213e5ba9cbc32d9f54ddc46b737908fabdb779fd2f05d0dea7539b3750c864"),
        ),
    ),
    PromotionSpec(
        source_id=None,
        source_url="https://dfpd.gov.in/WriteReadData/Other/nfsa_1.pdf",
        source_sha256="4f7f27f452ceda2a1951e4bde77177717971487453e45906b1ffc2bb75579c34",
        source_bytes=4198801,
        document_id="national-food-security-2013",
        title="National Food Security Act 2013",
        sections=("3", "12", "13", "14", "15", "24"),
        subject_area="constitutional",
        expected_origin="direct",
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("3", "d81639530469bd9403343ede5ef441e9025bc3e8cdfeb2c566fb503a7722c28f"),
            ("12", "f8c51b20691b1ca7b52effed8a44b0cd415b8fd5ebcb2e33e175549e42c05b7d"),
            ("13", "599d24969181a57e6609740a9b6b2ea526036d420995b8e24a759190cb65923b"),
            ("14", "b9a0a7b3465e2972ad16d0eb6fbf2d3b2ec6e80c20cadb1797a0acc8db810180"),
            ("15", "c3abb822431cea8701e8a267e861ea90f77176f67ba57fea6f501b52241f30a1"),
            ("24", "9a08123e35629cac2c7455dcc5da363806306a69e738747201aebd0ece27c3ce"),
        ),
    ),
    PromotionSpec(
        source_id=None,
        source_url=(
            "https://www.indiacode.nic.in/bitstream/123456789/20952/1/"
            "the_industrial_disputes_act%2c_1947.pdf"
        ),
        source_sha256="6d5c6458ec96eaea0d19a2252bfc80c0b41e19b13138db14822c9894a928119c",
        source_bytes=510639,
        document_id="industrial-disputes-1947",
        title="Industrial Disputes Act 1947",
        sections=("2A", "10", "12", "25F", "25G", "25H"),
        subject_area="service_employment",
        accepted_source_filenames=(
            "industrial-disputes-1947__the_industrial_disputes_act%2c_1947.pdf",
        ),
        accepted_predecessor_origins=("direct",),
        allow_unpinned_predecessor=True,
        promote_to_new_source=True,
        section_text_sha256=(
            ("2A", "d819358b5292904684b0b56d35d37d7910c3ed6dbb60380a5d44568f5b3b9558"),
            ("10", "24870eb533f6a209d638424db804ded6a7df22edff26813fa2925ae4402be990"),
            ("12", "6539b2f328aaf034a31519edcb4745763ea34f2f96450b6e58a77e35231ddadc"),
            ("25F", "689b0c639454ea44148b9888f3b41cde09091592a6f00df16b8f3e4354a7e871"),
            ("25G", "b33061224b4a810919d0a5ad32d34302d8613e765db715da584680e65833cc3d"),
            ("25H", "c33fe2cb734248c3ca27898ce6303f9802d79a2a55da4e0a1c8093bbcf2c6b5a"),
        ),
    ),
)


def _target_anchor(spec: PromotionSpec, section: str) -> str:
    document_id = spec.supplement_document_id or spec.document_id
    return f"{document_id}/sec-{section}-official"


@lru_cache(maxsize=None)
def _fetch_pinned_pdf(
    source_url: str,
    source_sha256: str,
    source_bytes: int,
    local_artifact_path: str | None = None,
) -> bytes:
    if local_artifact_path:
        cache_path = Path(local_artifact_path).resolve()
        if cache_path.exists():
            cached = cache_path.read_bytes()
            if (
                len(cached) != source_bytes
                or hashlib.sha256(cached).hexdigest() != source_sha256
            ):
                raise RuntimeError(f"refusing {source_url}: pinned local artifact hash mismatch")
            return cached
    if source_url.startswith("file://"):
        path = Path(unquote(source_url.removeprefix("file://"))).resolve()
        data = path.read_bytes()
        candidates = [data]
    else:
        candidates = [
            data
            for data, _status, _code, _url in refetch_act_pdfs(source_url)
        ]
    matches = [
        data
        for data in candidates
        if len(data) == source_bytes
        and hashlib.sha256(data).hexdigest() == source_sha256
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {source_url}: expected one pinned artifact, found {len(matches)}"
        )
    return matches[0]


def _canonical_section_text(spec: PromotionSpec, section: str, pdf_bytes: bytes) -> str:
    raw_text, _pages = extract_pdf_text(pdf_bytes)
    if raw_text is None:
        raise RuntimeError(f"refusing {spec.document_id} section {section}: PDF extraction failed")
    if spec.document_id == "constitution-india":
        return _canonical_constitution_article_text(spec, section, raw_text)
    chunks = list(chunk_act(spec.document_id, raw_text, act_title=spec.title))
    section_number = str(section).upper()
    matches = []
    for chunk in chunks:
        if str(chunk.metadata.get("section_no") or "").upper() != section_number:
            continue
        anchor = str(chunk.anchor or "")
        if re.search(rf"(?:^|/)sec-{re.escape(section)}(?:@|$)", anchor, re.IGNORECASE):
            rank = 0
        elif re.search(rf"(?:^|/)sec-{re.escape(section)}-a(?:@|$)", anchor, re.IGNORECASE):
            rank = 1
        else:
            continue
        matches.append((rank, chunk))
    if not matches:
        raise RuntimeError(
            f"refusing {spec.document_id} section {section}: no exact section start"
        )
    matches.sort(key=lambda item: (item[0], item[1].anchor))
    best_rank = matches[0][0]
    best_matches = [chunk for rank, chunk in matches if rank == best_rank]
    if len(best_matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section {section}: ambiguous exact section start"
        )
    return sanitize_for_db(best_matches[0].text)


def _metadata(spec: PromotionSpec, section: str) -> dict[str, object]:
    metadata: dict[str, object] = {
        "section_no": section,
        "canonical_artifact_sha256": spec.source_sha256,
        "canonical_repair": True,
        "provenance_verification_method": "pinned_artifact_exact_section_extraction",
        "source_url": spec.source_url,
        "required_source_pack_section": True,
    }
    section_text_hash = dict(spec.section_text_sha256).get(section)
    if section_text_hash:
        metadata["canonical_text_sha256"] = section_text_hash
    return metadata


def _validate_section_text_hashes(
    spec: PromotionSpec,
    texts: dict[str, str],
) -> None:
    expected_hashes = dict(spec.section_text_sha256)
    if set(expected_hashes) != set(spec.sections):
        raise RuntimeError(f"refusing {spec.document_id}: incomplete section text hash pin")
    for section in spec.sections:
        expected_hash = expected_hashes[section]
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise RuntimeError(
                f"refusing {spec.document_id} section {section}: invalid section text hash pin"
            )
        actual_hash = hashlib.sha256(texts[section].encode("utf-8")).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"refusing {spec.document_id} section {section}: normalized text hash mismatch"
            )


def _metadata_dict(value: object) -> dict:
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return dict(value or {})


def _predecessor_identity_matches(spec: PromotionSpec, source: object) -> bool:
    if source is None:
        return False
    accepted_origins = {spec.expected_origin, *spec.accepted_predecessor_origins}
    accepted_urls = {spec.source_url, *spec.accepted_source_urls}
    source_url = str(source["url"])
    filename_match = False
    if source_url.startswith("file://") and spec.accepted_source_filenames:
        source_filename = Path(unquote(source_url.removeprefix("file://"))).name
        filename_match = any(
            source_filename == unquote(accepted_filename)
            for accepted_filename in spec.accepted_source_filenames
        )
    return (
        (source_url in accepted_urls or filename_match)
        and source["source_type"] == "bare_act"
        and source["origin"] in accepted_origins
    )


def _predecessor_content_matches(spec: PromotionSpec, source: object) -> bool:
    """Accept only an exact predecessor, or an explicitly allowed empty record.

    The latter option exists solely for a supplementary, independently pinned
    source. It never verifies, re-enables, or replaces predecessor content.
    """
    if not _predecessor_identity_matches(spec, source):
        return False
    raw_hash = source["raw_sha256"]
    raw_size = source["raw_bytes_size"]
    if raw_hash == spec.source_sha256 and raw_size in (None, 0):
        return spec.promote_to_new_source and spec.allow_hash_only_predecessor
    if raw_hash in (None, "") and raw_size in (None, 0):
        return spec.promote_to_new_source and spec.allow_unpinned_predecessor
    return raw_hash == spec.source_sha256 and raw_size == spec.source_bytes


def _is_pinned_target_source(spec: PromotionSpec, source: object) -> bool:
    """Return whether ``source`` is the canonical artifact produced by this spec.

    A source promotion changes the document's source_id. On a later invocation
    the document therefore points at the canonical source rather than the old
    predecessor. Treating that state as a valid predecessor makes the
    section repair idempotent while still requiring the full pinned identity.
    """
    if source is None:
        return False
    try:
        metadata_value = source["metadata"]
    except (KeyError, TypeError):
        metadata_value = None
    metadata = _metadata_dict(metadata_value)
    return (
        source["source_type"] == "bare_act"
        and source["origin"] == spec.expected_origin
        and source["url"] == spec.source_url
        and source["raw_sha256"] == spec.source_sha256
        and source["raw_bytes_size"] == spec.source_bytes
        and source["provenance_tier"] == "canonical"
        and metadata.get("canonical_pdf_hash_pinned") is True
        and metadata.get("canonical_pdf_url") == spec.source_url
    )


def _canonical_constitution_article_text(
    spec: PromotionSpec,
    section: str,
    raw_text: str,
) -> str:
    article = _CONSTITUTION_ARTICLES.get(str(section).upper())
    if article is None:
        raise RuntimeError(
            f"refusing {spec.document_id} section {section}: no exact article rule"
        )
    heading = re.compile(
        rf"^[ \t]*{re.escape(str(section))}\.[ \t]+"
        rf"{re.escape(article['title'])}[\.—–-][ \t]*",
        re.MULTILINE,
    )
    boundary = re.compile(
        rf"^[ \t]*(?:\d+\[)?{re.escape(article['next'])}\.[ \t]+",
        re.MULTILINE,
    )
    normalized_proof = " ".join(article["proof"].split()).casefold()
    candidates: list[str] = []
    for match in heading.finditer(raw_text):
        next_match = boundary.search(raw_text, match.end())
        if next_match is None:
            continue
        candidate = raw_text[match.start() : next_match.start()].strip()
        normalized_candidate = " ".join(candidate.split()).casefold()
        if normalized_proof not in normalized_candidate:
            continue
        candidates.append(candidate)
    if len(candidates) == 1:
        return sanitize_for_db(f"{spec.title}, Article {section}\n\n{candidates[0]}")
    if len(candidates) > 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section {section}: ambiguous exact article start"
        )
    raise RuntimeError(
        f"refusing {spec.document_id} section {section}: no exact article start"
    )


async def _ensure_canonical_source(
    conn: asyncpg.Connection,
    spec: PromotionSpec,
    predecessor_source_id: int,
) -> int:
    url_hash = hashlib.sha256(spec.source_url.encode()).hexdigest()
    rows = await conn.fetch(
        "SELECT id, source_type, origin, url, canonical_url_hash, raw_sha256, "
        "raw_bytes_size, provenance_tier, metadata FROM sources "
        "WHERE canonical_url_hash=$1 FOR UPDATE",
        url_hash,
    )
    if len(rows) > 1:
        raise RuntimeError(f"refusing {spec.document_id}: duplicate canonical source identity")
    expected_transition = {
        "replaces_unverified_source_id": predecessor_source_id,
        "replaces_unverified_source_urls": list(spec.accepted_source_urls),
        "predecessor_content_verified": False,
        "source_transition": "independent_first_party_artifact_replacement",
    }
    if rows:
        row = rows[0]
        if (
            row["source_type"] == "bare_act"
            and row["origin"] == spec.expected_origin
            and row["url"] == spec.source_url
            and row["provenance_tier"] == "unverified"
            and row["raw_sha256"] in (None, "")
            and row["raw_bytes_size"] in (None, 0)
        ):
            existing_metadata = _metadata_dict(row["metadata"])
            canonical_metadata = {
                "canonical_pdf_hash_pinned": True,
                "canonical_pdf_url": spec.source_url,
                **expected_transition,
            }
            for key, expected_value in canonical_metadata.items():
                if key in existing_metadata and existing_metadata[key] != expected_value:
                    raise RuntimeError(
                        f"refusing {spec.document_id}: unverified canonical URL metadata conflicts"
                    )
            sibling_count = await conn.fetchval(
                "SELECT count(*) FROM documents WHERE source_id=$1 AND doc_id<>$2",
                row["id"],
                spec.document_id,
            )
            if int(sibling_count or 0) != 0:
                raise RuntimeError(
                    f"refusing {spec.document_id}: unverified canonical URL has sibling documents"
                )
            updated = await conn.execute(
                "UPDATE sources SET raw_sha256=$1, raw_bytes_size=$2, "
                "provenance_tier='canonical', metadata=COALESCE(metadata,'{}'::jsonb)||$3::jsonb "
                "WHERE id=$4 AND provenance_tier='unverified' "
                "AND raw_sha256 IS NULL AND raw_bytes_size IS NULL",
                spec.source_sha256,
                spec.source_bytes,
                json.dumps(canonical_metadata),
                row["id"],
            )
            if updated != "UPDATE 1":
                raise RuntimeError(f"refusing {spec.document_id}: canonical source CAS failed")
            return int(row["id"])
        if (
            row["source_type"] != "bare_act"
            or row["origin"] != spec.expected_origin
            or row["url"] != spec.source_url
            or row["raw_sha256"] != spec.source_sha256
            or row["raw_bytes_size"] != spec.source_bytes
            or row["provenance_tier"] != "canonical"
            or any(_metadata_dict(row["metadata"]).get(k) != v for k, v in expected_transition.items())
        ):
            raise RuntimeError(f"refusing {spec.document_id}: canonical source conflicts")
        return int(row["id"])
    return int(await conn.fetchval(
        "INSERT INTO sources (source_type, origin, url, canonical_url_hash, raw_sha256, "
        "raw_bytes_size, provenance_tier, metadata) "
        "VALUES ('bare_act',$1,$2,$3,$4,$5,'canonical',$6::jsonb) RETURNING id",
        spec.expected_origin,
        spec.source_url,
        url_hash,
        spec.source_sha256,
        spec.source_bytes,
        json.dumps({
            "canonical_pdf_hash_pinned": True,
            "canonical_pdf_url": spec.source_url,
            **expected_transition,
        }),
    ))


async def _ensure_supplement_document(
    conn: asyncpg.Connection,
    spec: PromotionSpec,
    source_id: int,
) -> dict:
    if not spec.supplement_document_id:
        raise RuntimeError("supplement document id is required")
    metadata = {
        "canonical_section_supplement": True,
        "canonical_artifact_sha256": spec.source_sha256,
        "source_url": spec.source_url,
        "supplements_document_id": spec.document_id,
    }
    existing = await conn.fetchrow(
        "SELECT id, title, source_id, metadata FROM documents WHERE doc_id=$1 FOR UPDATE",
        spec.supplement_document_id,
    )
    if existing is not None:
        if existing["title"] != spec.title or existing["source_id"] != source_id:
            raise RuntimeError(
                f"refusing {spec.supplement_document_id}: supplemental document identity conflict"
            )
        existing_metadata = _metadata_dict(existing["metadata"])
        if any(existing_metadata.get(key) != value for key, value in metadata.items()):
            raise RuntimeError(
                f"refusing {spec.supplement_document_id}: supplemental document metadata conflict"
            )
        return existing
    created = await conn.fetchrow(
        "INSERT INTO documents (source_id, doc_id, title, subject_area, metadata) "
        "VALUES ($1,$2,$3,$4,$5::jsonb) RETURNING id, title, source_id",
        source_id,
        spec.supplement_document_id,
        spec.title,
        spec.subject_area,
        json.dumps(metadata),
    )
    if created is None:
        raise RuntimeError(f"refusing {spec.supplement_document_id}: document insert failed")
    return created


async def _promote_supplement(
    conn: asyncpg.Connection,
    spec: PromotionSpec,
    *,
    texts: dict[str, str],
    dry_run: bool,
) -> list[dict[str, object]]:
    """Add an exact verified section without changing a legacy document's scope."""
    if not spec.promote_to_new_source:
        raise RuntimeError(f"refusing {spec.document_id}: supplements require a canonical source")
    if dry_run:
        return [
            {"section": section, "anchor": _target_anchor(spec, section), "action": "would_promote_supplement"}
            for section in spec.sections
        ]

    dense, sparse = get_embedder().encode_with_sparse([texts[s] for s in spec.sections])
    embedded = {
        section: (embedding_to_halfvec_literal(dense[index]), sparse_to_jsonb(sparse[index]))
        for index, section in enumerate(spec.sections)
    }
    async with conn.transaction():
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"law-rag-promote-source-pack-supplement:{spec.supplement_document_id}:{spec.source_sha256}",
        )
        source = await conn.fetchrow(
            "SELECT id, url, origin, canonical_url_hash, raw_sha256, raw_bytes_size, "
            "source_type, provenance_tier FROM sources WHERE id=$1 FOR UPDATE",
            spec.source_id,
        )
        if not _predecessor_content_matches(spec, source):
            raise RuntimeError(f"refusing {spec.document_id}: source changed during supplement promotion")
        predecessor = await conn.fetchrow(
            "SELECT id, title, source_id FROM documents WHERE doc_id=$1 FOR UPDATE",
            spec.document_id,
        )
        if (
            predecessor is None
            or predecessor["title"] != spec.title
            or predecessor["source_id"] != spec.source_id
        ):
            raise RuntimeError(f"refusing {spec.document_id}: predecessor document changed")

        # The predecessor is only an identity bridge to an independently
        # pinned source. It must not keep document-level eligibility, and any
        # non-registry predecessor chunk must remain unavailable in serving.
        await conn.execute(
            "UPDATE documents SET provenance_verified=false, provenance_verified_at=NULL WHERE id=$1",
            predecessor["id"],
        )
        await conn.execute(
            "UPDATE chunks SET provenance_verified=false, provenance_verified_at=NULL "
            "WHERE document_id=$1 AND NOT ("
            "COALESCE(metadata->>'registry_projection','')='chunk' "
            "AND metadata ? 'authority_record_sha256' "
            "AND COALESCE((metadata->>'text_is_verbatim')::boolean,false)"
            ")",
            predecessor["id"],
        )

        canonical_source_id = await _ensure_canonical_source(
            conn, spec, predecessor_source_id=spec.source_id
        )
        document = await _ensure_supplement_document(conn, spec, canonical_source_id)
        target_anchors = [_target_anchor(spec, section) for section in spec.sections]
        # A supplement document is exact-section only. Retain eligibility for
        # the reviewed target anchors and fail closed for any older/stale row.
        await conn.execute(
            "UPDATE documents SET provenance_verified=false, provenance_verified_at=NULL WHERE id=$1",
            document["id"],
        )
        await conn.execute(
            "UPDATE chunks SET provenance_verified=false, provenance_verified_at=NULL "
            "WHERE document_id=$1 AND NOT (anchor = ANY($2::text[]))",
            document["id"],
            target_anchors,
        )
        results: list[dict[str, object]] = []
        for section in spec.sections:
            anchor = _target_anchor(spec, section)
            metadata = _metadata(spec, section) | {
                "canonical_section_supplement": True,
                "supplements_document_id": spec.document_id,
            }
            rows = await conn.fetch(
                "SELECT id, text, metadata, provenance_verified, quarantined "
                "FROM chunks WHERE document_id=$1 AND anchor=$2 AND as_at IS NULL ORDER BY id",
                document["id"],
                anchor,
            )
            if len(rows) > 1:
                raise RuntimeError(f"refusing {spec.supplement_document_id}: duplicate target {anchor}")
            existing = rows[0] if rows else None
            if existing and (
                existing["text"] == texts[section]
                and existing["provenance_verified"]
                and not existing["quarantined"]
                and _metadata_dict(existing["metadata"]).items() >= metadata.items()
            ):
                results.append({"section": section, "anchor": anchor, "action": "no_op", "chunk_id": existing["id"]})
                continue
            dense_value, sparse_value = embedded[section]
            if existing:
                update = await conn.execute(
                    "UPDATE chunks SET source_type='bare_act', subject_area=$1, paragraph_no=NULL, "
                    "token_count=$2, text=$3, embedding=$4::halfvec, embedding_sparse=$5::jsonb, "
                    "chunk_strategy='section', metadata=COALESCE(metadata,'{}'::jsonb)||$6::jsonb, "
                    "provenance_verified=true, provenance_verified_at=now(), quarantined=false "
                    "WHERE id=$7 AND document_id=$8 AND anchor=$9 AND text=$10 "
                    "AND provenance_verified IS NOT DISTINCT FROM $11 AND quarantined IS NOT DISTINCT FROM $12 "
                    "AND as_at IS NULL",
                    spec.subject_area,
                    len(texts[section].split()),
                    texts[section],
                    dense_value,
                    sparse_value,
                    json.dumps(metadata),
                    existing["id"],
                    document["id"],
                    anchor,
                    existing["text"],
                    existing["provenance_verified"],
                    existing["quarantined"],
                )
                if update != "UPDATE 1":
                    raise RuntimeError(f"refusing {spec.supplement_document_id}: target CAS failed for {anchor}")
                chunk_id = existing["id"]
                action = "repaired"
            else:
                chunk_id = await conn.fetchval(
                    "INSERT INTO chunks (document_id, source_type, subject_area, anchor, paragraph_no, "
                    "token_count, text, embedding, embedding_sparse, chunk_strategy, as_at, metadata, "
                    "quarantined, provenance_verified, provenance_verified_at) "
                    "VALUES ($1,'bare_act',$2,$3,NULL,$4,$5,$6::halfvec,$7::jsonb,'section',NULL,$8::jsonb,false,true,now()) RETURNING id",
                    document["id"],
                    spec.subject_area,
                    anchor,
                    len(texts[section].split()),
                    texts[section],
                    dense_value,
                    sparse_value,
                    json.dumps(metadata),
                )
                action = "inserted"
            results.append({"section": section, "anchor": anchor, "action": action, "chunk_id": chunk_id})
        return results


async def promote_spec(
    conn: asyncpg.Connection,
    spec: PromotionSpec,
    *,
    dry_run: bool,
) -> list[dict[str, object]]:
    if spec.requires_dated_as_at:
        raise RuntimeError(
            f"refusing {spec.document_id}: dated as_at provenance requires a dedicated promoter"
        )

    # Resolve the current predecessor through the stable document identity.
    # The manifest source_id remains a compatibility hint for older entries,
    # but a checkout-local numeric id must never select a different source.
    document = await conn.fetchrow(
        "SELECT id, title, source_id FROM documents WHERE doc_id=$1",
        spec.document_id,
    )
    try:
        document_title = document["title"] if document is not None else None
    except (KeyError, TypeError):
        document_title = None
    if document is None or document_title != spec.title:
        raise RuntimeError(f"refusing {spec.document_id}: document identity mismatch")
    predecessor_source_id = document["source_id"]
    if predecessor_source_id is None:
        raise RuntimeError(f"refusing {spec.document_id}: document has no predecessor source")
    source = await conn.fetchrow(
        "SELECT id, url, origin, canonical_url_hash, raw_sha256, raw_bytes_size, source_type, "
        "provenance_tier, metadata FROM sources WHERE id=$1",
        predecessor_source_id,
    )
    if not _predecessor_identity_matches(spec, source):
        raise RuntimeError(f"refusing {spec.document_id}: source identity mismatch")
    if not _predecessor_content_matches(spec, source):
        raise RuntimeError(f"refusing {spec.document_id}: source size conflicts")
    already_promoted = spec.promote_to_new_source and _is_pinned_target_source(spec, source)
    if not spec.promote_to_new_source and document["source_id"] != predecessor_source_id:
        raise RuntimeError(f"refusing {spec.document_id}: document source identity mismatch")
    if not spec.promote_to_new_source:
        expected_url_hash = hashlib.sha256(spec.source_url.encode()).hexdigest()
        if (
            source["url"] != spec.source_url
            or source["canonical_url_hash"] != expected_url_hash
            or source["raw_sha256"] != spec.source_sha256
            or source["raw_bytes_size"] != spec.source_bytes
            or source["provenance_tier"] != "canonical"
        ):
            raise RuntimeError(
                f"refusing {spec.document_id}: unpinned predecessor requires canonical source promotion"
            )

    texts = {
        section: _canonical_section_text(
            spec,
            section,
            _fetch_pinned_pdf(
                spec.source_url,
                spec.source_sha256,
                spec.source_bytes,
                spec.local_artifact_path,
            ),
        )
        for section in spec.sections
    }
    _validate_section_text_hashes(spec, texts)
    if spec.supplement_document_id:
        return await _promote_supplement(conn, spec, texts=texts, dry_run=dry_run)
    embedded = {}
    if not dry_run:
        dense, sparse = get_embedder().encode_with_sparse([texts[s] for s in spec.sections])
        for index, section in enumerate(spec.sections):
            embedded[section] = (
                embedding_to_halfvec_literal(dense[index]),
                sparse_to_jsonb(sparse[index]),
            )

    async def apply() -> list[dict[str, object]]:
        async with conn.transaction():
            await conn.fetchval(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"law-rag-promote-source-pack:{spec.document_id}:{spec.source_sha256}",
            )
            current_source = await conn.fetchrow(
                "SELECT id, url, origin, canonical_url_hash, raw_sha256, raw_bytes_size, "
                "source_type, provenance_tier, metadata FROM sources WHERE id=$1 FOR UPDATE",
                predecessor_source_id,
            )
            if current_source is None or any(
                current_source[key] != source[key]
                for key in (
                    "url",
                    "origin",
                    "canonical_url_hash",
                    "raw_sha256",
                    "raw_bytes_size",
                    "source_type",
                    "provenance_tier",
                )
            ):
                raise RuntimeError(f"refusing {spec.document_id}: source changed during promotion")
            current_document = await conn.fetchrow(
                "SELECT id, title, source_id FROM documents WHERE doc_id=$1 FOR UPDATE",
                spec.document_id,
            )
            if current_document != document and (
                current_document is None
                or current_document["title"] != document["title"]
            ):
                raise RuntimeError(f"refusing {spec.document_id}: document changed")
            if (
                not spec.promote_to_new_source
                and current_document["source_id"] != predecessor_source_id
            ):
                raise RuntimeError(f"refusing {spec.document_id}: document source changed during promotion")
            if spec.promote_to_new_source and not already_promoted:
                canonical_source_id = await _ensure_canonical_source(
                    conn, spec, predecessor_source_id=predecessor_source_id
                )
                result = await conn.execute(
                    "UPDATE documents SET source_id=$1 WHERE id=$2 "
                    "AND source_id = ANY($3::bigint[])",
                    canonical_source_id,
                    document["id"],
                    [predecessor_source_id, canonical_source_id],
                )
                if result != "UPDATE 1":
                    raise RuntimeError(f"refusing {spec.document_id}: source CAS failed")

            # A partial promotion must never leave a document-level flag or a
            # previously marked legacy chunk eligible for retrieval. Preserve
            # only registry-projected, verbatim chunks with their own immutable
            # authority record: they carry independent provenance and are not
            # inheriting eligibility from this document source. The exact target
            # chunks are re-enabled below from the pinned artifact; every other
            # legacy chunk must be re-proven in a later promotion.
            await conn.execute(
                "UPDATE documents SET provenance_verified=false, provenance_verified_at=NULL "
                "WHERE id=$1",
                document["id"],
            )
            await conn.execute(
                "UPDATE chunks SET provenance_verified=false, provenance_verified_at=NULL "
                "WHERE document_id=$1 AND NOT ("
                "COALESCE(metadata->>'registry_projection','')='chunk' "
                "AND metadata ? 'authority_record_sha256' "
                "AND COALESCE((metadata->>'text_is_verbatim')::boolean,false)"
                ")",
                document["id"],
            )

            results = []
            for section in spec.sections:
                anchor = _target_anchor(spec, section)
                metadata = _metadata(spec, section)
                rows = await conn.fetch(
                    "SELECT id, text, metadata, provenance_verified, quarantined "
                    "FROM chunks WHERE document_id=$1 AND anchor=$2 AND as_at IS NULL ORDER BY id",
                    document["id"],
                    anchor,
                )
                if len(rows) > 1:
                    raise RuntimeError(f"refusing {spec.document_id}: duplicate target {anchor}")
                existing = rows[0] if rows else None
                if existing and (
                    existing["text"] == texts[section]
                    and existing["provenance_verified"]
                    and not existing["quarantined"]
                    and _metadata_dict(existing["metadata"]).items() >= metadata.items()
                ):
                    results.append({"section": section, "anchor": anchor, "action": "no_op", "chunk_id": existing["id"]})
                    continue
                dense, sparse = embedded[section]
                if existing:
                    update = await conn.execute(
                        "UPDATE chunks SET source_type='bare_act', subject_area=$1, paragraph_no=NULL, "
                        "token_count=$2, text=$3, embedding=$4::halfvec, embedding_sparse=$5::jsonb, "
                        "chunk_strategy='section', metadata=COALESCE(metadata,'{}'::jsonb)||$6::jsonb, "
                        "provenance_verified=true, provenance_verified_at=now(), quarantined=false "
                        "WHERE id=$7 AND document_id=$8 AND anchor=$9 AND text=$10 "
                        "AND provenance_verified IS NOT DISTINCT FROM $11 AND quarantined IS NOT DISTINCT FROM $12 "
                        "AND as_at IS NULL",
                        spec.subject_area, len(texts[section].split()), texts[section], dense, sparse,
                        json.dumps(metadata), existing["id"], document["id"], anchor,
                        existing["text"], existing["provenance_verified"], existing["quarantined"],
                    )
                    if update != "UPDATE 1":
                        raise RuntimeError(f"refusing {spec.document_id}: target CAS failed for {anchor}")
                    chunk_id = existing["id"]
                    action = "repaired"
                else:
                    chunk_id = await conn.fetchval(
                        "INSERT INTO chunks (document_id, source_type, subject_area, anchor, paragraph_no, "
                        "token_count, text, embedding, embedding_sparse, chunk_strategy, as_at, metadata, "
                        "quarantined, provenance_verified, provenance_verified_at) "
                        "VALUES ($1,'bare_act',$2,$3,NULL,$4,$5,$6::halfvec,$7::jsonb,'section',NULL,$8::jsonb,false,true,now()) RETURNING id",
                        document["id"], spec.subject_area, anchor, len(texts[section].split()), texts[section],
                        dense, sparse, json.dumps(metadata),
                    )
                    action = "inserted"
                results.append({"section": section, "anchor": anchor, "action": action, "chunk_id": chunk_id})
            return results

    if dry_run:
        return [
            {"section": section, "anchor": _target_anchor(spec, section), "action": "would_promote"}
            for section in spec.sections
        ]
    return await apply()


async def run(*, dry_run: bool, only: str | None) -> list[dict[str, object]]:
    selected = [spec for spec in SPECS if only is None or spec.document_id == only]
    if not selected:
        raise RuntimeError(f"unknown document: {only}")
    conn = await asyncpg.connect(get_settings().resolved_database_url_host_side)
    try:
        output: list[dict[str, object]] = []
        for spec in selected:
            output.extend(await promote_spec(conn, spec, dry_run=dry_run))
        return output
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=sorted({spec.document_id for spec in SPECS}))
    args = parser.parse_args()
    for row in asyncio.run(run(dry_run=args.dry_run, only=args.only)):
        print(json.dumps(row, ensure_ascii=True))


if __name__ == "__main__":
    main()
