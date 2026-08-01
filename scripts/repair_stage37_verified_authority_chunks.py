#!/usr/bin/env python3
"""Promote two exact official authority chunks required by released packs.

The existing corpus contains the Court Fees document without a pinned source
hash, and the Constitution parser missed Article 46. This utility is narrow:
it refetches the pinned official artifacts, extracts only the required
provisions, embeds them, and marks only those chunks as provenance-verified.
Neighboring legacy chunks remain untouched and therefore remain fail-closed.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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
class RepairSpec:
    source_id: int | None
    source_url: str
    source_sha256: str
    source_bytes: int
    document_id: str
    title: str
    anchor: str
    section_no: str
    section_title: str
    subject_area: str
    kind: str
    accepted_source_urls: tuple[str, ...] = ()
    promote_to_new_source: bool = False
    as_at: date | None = None
    expected_text_sha256: str | None = None
    allow_create: bool = False
    local_artifact_path: str | None = None


SPECS = (
    RepairSpec(
        source_id=380,
        source_url="https://www.indiacode.nic.in/handle/123456789/17039",
        source_sha256="a5fe9d61e3c3a4c46edefb7b258810332d264a75e527a787861ee0671a75ebfb",
        source_bytes=1408899,
        document_id="court-fees-1870",
        title="The Court-Fees Act, 1870",
        anchor="court-fees-1870/sec-7-official",
        section_no="7",
        section_title="Computation of fees payable in certain suits",
        subject_area="civil_procedure",
        kind="court_fees",
        expected_text_sha256="41fdbafaddab67dcca5fa8a5e6475ca97e089bcfc0ad6203e4ffd7bff6ea4b91",
    ),
    RepairSpec(
        source_id=682,
        source_url="https://www.legislative.gov.in/static/uploads/2025/07/c9fe9c9b6840524844316f74bb1c556c.pdf",
        source_sha256="4c8e93689ec245e26db08e22b5ff3ad645c98736f0e5b7c8b6638acd7861f85b",
        source_bytes=2684622,
        document_id="constitution-india",
        title="Constitution of India",
        anchor="constitution-india/sec-46",
        section_no="46",
        section_title="Promotion of educational and economic interests of Scheduled Castes, Scheduled Tribes and other weaker sections",
        subject_area="constitutional",
        kind="constitution_article_46",
        expected_text_sha256="e97562c90aec7e87f456950c88f44c17f32639c2c9655f17e982331afa4965ae",
    ),
    RepairSpec(
        source_id=382,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15278/1/drug_cosmeticsa1940-23.pdf",
        source_sha256="776ff2af5513a9125206529f93cd31223c38329314ff6f3b37e9593093284046",
        source_bytes=634530,
        document_id="drugs-cosmetics-1940",
        title="Drugs and Cosmetics Act 1940",
        anchor="drugs-cosmetics-1940/sec-18-official",
        section_no="18",
        section_title="Prohibition of manufacture and sale of certain drugs and cosmetics",
        subject_area="business_license",
        kind="drugs_act_section",
        expected_text_sha256="e1063c09848e2bea0e1d48ce3e746fc7eb41e4b7d68a8b2df3bee50723073181",
        accepted_source_urls=(
            "https://cdsco.mohfw.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf",
        ),
        promote_to_new_source=True,
    ),
    RepairSpec(
        source_id=382,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15278/1/drug_cosmeticsa1940-23.pdf",
        source_sha256="776ff2af5513a9125206529f93cd31223c38329314ff6f3b37e9593093284046",
        source_bytes=634530,
        document_id="drugs-cosmetics-1940",
        title="Drugs and Cosmetics Act 1940",
        anchor="drugs-cosmetics-1940/sec-22-official",
        section_no="22",
        section_title="Powers of Inspectors",
        subject_area="business_license",
        kind="drugs_act_section",
        expected_text_sha256="1fda694352f91a943db6eaf580b1206c16a26ce197f7dc32306ef00a31e18288",
        accepted_source_urls=(
            "https://cdsco.mohfw.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf",
        ),
        promote_to_new_source=True,
    ),
    RepairSpec(
        source_id=382,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15278/1/drug_cosmeticsa1940-23.pdf",
        source_sha256="776ff2af5513a9125206529f93cd31223c38329314ff6f3b37e9593093284046",
        source_bytes=634530,
        document_id="drugs-cosmetics-1940",
        title="Drugs and Cosmetics Act 1940",
        anchor="drugs-cosmetics-1940/sec-23-official",
        section_no="23",
        section_title="Procedure of Inspectors",
        subject_area="business_license",
        kind="drugs_act_section",
        expected_text_sha256="6a3e199aa75ac7c8022a2c228ea12e7d4b765ddee8dc5fafe94d53389a6f1e30",
        accepted_source_urls=(
            "https://cdsco.mohfw.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf",
        ),
        promote_to_new_source=True,
    ),
    RepairSpec(
        source_id=382,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15278/1/drug_cosmeticsa1940-23.pdf",
        source_sha256="776ff2af5513a9125206529f93cd31223c38329314ff6f3b37e9593093284046",
        source_bytes=634530,
        document_id="drugs-cosmetics-1940",
        title="Drugs and Cosmetics Act 1940",
        anchor="drugs-cosmetics-1940/sec-27-official",
        section_no="27",
        section_title="Penalty for manufacture, sale, etc., of drugs in contravention of this Chapter",
        subject_area="business_license",
        kind="drugs_act_section_27",
        expected_text_sha256="1aad8890d25b053b6ffa21dd50c256cb799824f1dbe8cb906cdbbf819281c97e",
        accepted_source_urls=(
            "https://cdsco.mohfw.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf",
        ),
        promote_to_new_source=True,
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15272/1/the_code_of_criminal_procedure%2C_1973.pdf",
        source_sha256="5bb6514251a9ec6375b2c894cef5280dab0d1c3cca1e0f4a1e57f29b54033d72",
        source_bytes=1879339,
        document_id="crpc-1973",
        title="Code of Criminal Procedure 1973",
        anchor="crpc-1973/sec-154",
        section_no="154",
        section_title="Information in cognizable cases",
        subject_area="criminal_procedure",
        kind="crpc_section_154",
        expected_text_sha256="cdbc71d31392685338950e2e6286f8e0442ea4f8ed6f64aa4fa800ba0a98c842",
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.mha.gov.in/sites/default/files/250884_2_english_01042024.pdf",
        source_sha256="5e60e2afe30d0fe7eca4f8126301146b76c86a444e690581f81eb564843517fe",
        source_bytes=2033181,
        document_id="bnss-2023",
        title="Bharatiya Nagarik Suraksha Sanhita 2023",
        anchor="bnss-2023/sec-173-a@2024-07-01",
        section_no="173-a",
        section_title="Information in cognizable cases (initial information)",
        subject_area="criminal",
        kind="bnss_chunk",
        as_at=date(2024, 7, 1),
        expected_text_sha256="ae19bedb7b5079c4334e3c0812842e12ddcac447240015e6596c020c99f2022d",
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.mha.gov.in/sites/default/files/250884_2_english_01042024.pdf",
        source_sha256="5e60e2afe30d0fe7eca4f8126301146b76c86a444e690581f81eb564843517fe",
        source_bytes=2033181,
        document_id="bnss-2023",
        title="Bharatiya Nagarik Suraksha Sanhita 2023",
        anchor="bnss-2023/sec-173-c@2024-07-01",
        section_no="173-c",
        section_title="Information in cognizable cases (post-refusal escalation)",
        subject_area="criminal",
        kind="bnss_chunk",
        as_at=date(2024, 7, 1),
        expected_text_sha256="40b48d8788c88df5d3d8a7813262f763de7e57f7a1f18e31d7f0c3a653751ab8",
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.mha.gov.in/sites/default/files/250884_2_english_01042024.pdf",
        source_sha256="5e60e2afe30d0fe7eca4f8126301146b76c86a444e690581f81eb564843517fe",
        source_bytes=2033181,
        document_id="bnss-2023",
        title="Bharatiya Nagarik Suraksha Sanhita 2023",
        anchor="bnss-2023/sec-175@2024-07-01",
        section_no="175",
        section_title="Police officer power to investigate cognizable case and Magistrate order",
        subject_area="criminal",
        kind="bnss_chunk",
        as_at=date(2024, 7, 1),
        expected_text_sha256="f28374f89fb1f57022e455e2f4b0a0d1253f0b23b77dbfbb7f24bd41a63dfd51",
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf",
        source_sha256="ff92dcc72778944011807644b6033b1140ddbe6d7e9f82ac32fd419dae03aa86",
        source_bytes=896392,
        document_id="bns-2023",
        title="Bharatiya Nyaya Sanhita 2023",
        anchor="bns-2023/sec-303-a@2024-07-01",
        section_no="303",
        section_title="Theft",
        subject_area="criminal",
        kind="generic_act_section",
        as_at=date(2024, 7, 1),
        expected_text_sha256="a645fa9823e5f29ae6529971e7bea93377f7add77a39f774c7cc34586baeb37c",
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf",
        source_sha256="ff92dcc72778944011807644b6033b1140ddbe6d7e9f82ac32fd419dae03aa86",
        source_bytes=896392,
        document_id="bns-2023",
        title="Bharatiya Nyaya Sanhita 2023",
        anchor="bns-2023/sec-317@2024-07-01",
        section_no="317",
        section_title="Stolen property",
        subject_area="criminal",
        kind="generic_act_section",
        as_at=date(2024, 7, 1),
        expected_text_sha256="de73ac89630cacec2ca77cab8cda271f293e694c30ff068de604412837a6a0f8",
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/4219/1/THE-INDIAN-PENAL-CODE-1860.pdf",
        source_sha256="ef8945c5d1b02904da67959e245b87bd5751ed5563d03ab0079758909f145309",
        source_bytes=842456,
        document_id="ipc-1860",
        title="Indian Penal Code 1860",
        anchor="ipc-1860/sec-378",
        section_no="378",
        section_title="Theft",
        subject_area="criminal",
        kind="ipc_section_378",
        as_at=date(1860, 10, 6),
        expected_text_sha256="e1fe0879d4dff4ebfb42053e1fa4680b2f0a0a1716f7dc43065e22118f556fce",
        allow_create=True,
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/4219/1/THE-INDIAN-PENAL-CODE-1860.pdf",
        source_sha256="ef8945c5d1b02904da67959e245b87bd5751ed5563d03ab0079758909f145309",
        source_bytes=842456,
        document_id="ipc-1860",
        title="Indian Penal Code 1860",
        anchor="ipc-1860/sec-379",
        section_no="379",
        section_title="Punishment for theft",
        subject_area="criminal",
        kind="generic_act_section",
        as_at=date(1860, 10, 6),
        expected_text_sha256="ca69a8c36adfc6c676dc7acf4aece389bf609699baf999874ecbed1ad0f99692",
        allow_create=True,
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/4219/1/THE-INDIAN-PENAL-CODE-1860.pdf",
        source_sha256="ef8945c5d1b02904da67959e245b87bd5751ed5563d03ab0079758909f145309",
        source_bytes=842456,
        document_id="ipc-1860",
        title="Indian Penal Code 1860",
        anchor="ipc-1860/sec-411",
        section_no="411",
        section_title="Dishonestly receiving stolen property",
        subject_area="criminal",
        kind="generic_act_section",
        as_at=date(1860, 10, 6),
        expected_text_sha256="0a52b1f9379995b20b303a6c4b1461d4352a04b85692b080b52e93faad7aa07f",
        allow_create=True,
    ),
    # The MSMED Act is already present in the legacy Act corpus, but its
    # source row was created without an artifact hash. Promote only the three
    # sections used by the delayed-payment workflow after checking the
    # repository-pinned India Code PDF; the remaining legacy chunks stay
    # ineligible until independently verified.
    RepairSpec(
        source_id=342,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2013/3/A2006-27.pdf",
        source_sha256="2ecd1527ad2f91b591c1e4f38ae4b0133e85eb8d4a47179274828b8879115697",
        source_bytes=242312,
        document_id="msmed-2006",
        title="Micro, Small and Medium Enterprises Development Act 2006",
        anchor="msmed-2006/sec-15",
        section_no="15",
        section_title="Liability of buyer to make payment",
        subject_area="civil_general",
        kind="generic_act_section",
        expected_text_sha256="ba1b53d56f51721ee7ba3990b375083c581854c2f5a20a3414c7b3f9fda6597d",
        local_artifact_path=str(ROOT / "data/raw/acts/msmed-2006__A2006-27.pdf"),
    ),
    RepairSpec(
        source_id=342,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2013/3/A2006-27.pdf",
        source_sha256="2ecd1527ad2f91b591c1e4f38ae4b0133e85eb8d4a47179274828b8879115697",
        source_bytes=242312,
        document_id="msmed-2006",
        title="Micro, Small and Medium Enterprises Development Act 2006",
        anchor="msmed-2006/sec-16",
        section_no="16",
        section_title="Date from which and rate at which interest is payable",
        subject_area="civil_general",
        kind="generic_act_section",
        expected_text_sha256="d47d029b5e3edef6fb130bd9efbabfbf8e1da217489d3afdee23042ae77ecb24",
        local_artifact_path=str(ROOT / "data/raw/acts/msmed-2006__A2006-27.pdf"),
    ),
    RepairSpec(
        source_id=342,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2013/3/A2006-27.pdf",
        source_sha256="2ecd1527ad2f91b591c1e4f38ae4b0133e85eb8d4a47179274828b8879115697",
        source_bytes=242312,
        document_id="msmed-2006",
        title="Micro, Small and Medium Enterprises Development Act 2006",
        anchor="msmed-2006/sec-18",
        section_no="18",
        section_title="Reference to Micro and Small EnterprisesFacilitation Council",
        subject_area="civil_general",
        kind="generic_act_section",
        expected_text_sha256="390c20827c28632c376bc695fc1bb824c5d05da8cc9f05b6bd2fb4b5f13d835e",
        local_artifact_path=str(ROOT / "data/raw/acts/msmed-2006__A2006-27.pdf"),
    ),
    # The MSME quality/acceptance route also needs the four Sale of Goods
    # sections named by its reviewed source pack. Keep this promotion
    # section-scoped; unrelated provisions remain fail-closed.
    RepairSpec(
        source_id=366,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf",
        source_sha256="069ff04276e3511062a4076c74de9971ca0e616b80eabc0849b4f379a04a5e82",
        source_bytes=377988,
        document_id="sale-of-goods-1930",
        title="Sale of Goods Act 1930",
        anchor="sale-of-goods-1930/sec-31",
        section_no="31",
        section_title="Duties, of seller and buyer",
        subject_area="business",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2390",),
        expected_text_sha256="eeeb6b9353f4c8f121ee0dbda26343ed5e6b0c3bb52f2ff11e54c339188bed61",
        local_artifact_path=str(ROOT / "data/raw/acts/sale-of-goods-1930__193003.pdf"),
    ),
    RepairSpec(
        source_id=366,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf",
        source_sha256="069ff04276e3511062a4076c74de9971ca0e616b80eabc0849b4f379a04a5e82",
        source_bytes=377988,
        document_id="sale-of-goods-1930",
        title="Sale of Goods Act 1930",
        anchor="sale-of-goods-1930/sec-32",
        section_no="32",
        section_title="Payment and delivery are concurrent conditions",
        subject_area="business",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2390",),
        expected_text_sha256="dc5cb0e531c48142c32f1a8ddf68053e64fcf7ef77b19feed9a8cdb3ff790b6c",
        local_artifact_path=str(ROOT / "data/raw/acts/sale-of-goods-1930__193003.pdf"),
    ),
    RepairSpec(
        source_id=366,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf",
        source_sha256="069ff04276e3511062a4076c74de9971ca0e616b80eabc0849b4f379a04a5e82",
        source_bytes=377988,
        document_id="sale-of-goods-1930",
        title="Sale of Goods Act 1930",
        anchor="sale-of-goods-1930/sec-55",
        section_no="55",
        section_title="Suit for price",
        subject_area="business",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2390",),
        expected_text_sha256="cfb773dc46f19ded5a208c112b87ec6d9388ee5de292e0d5413899d5b1b45a49",
        local_artifact_path=str(ROOT / "data/raw/acts/sale-of-goods-1930__193003.pdf"),
    ),
    RepairSpec(
        source_id=366,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf",
        source_sha256="069ff04276e3511062a4076c74de9971ca0e616b80eabc0849b4f379a04a5e82",
        source_bytes=377988,
        document_id="sale-of-goods-1930",
        title="Sale of Goods Act 1930",
        anchor="sale-of-goods-1930/sec-56",
        section_no="56",
        section_title="Damages for non-acceptance",
        subject_area="business",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2390",),
        expected_text_sha256="b0b0359e1fc7d8742f317d02219e50e8f96d58ed02c6e8571749d0f2d0f304d8",
        local_artifact_path=str(ROOT / "data/raw/acts/sale-of-goods-1930__193003.pdf"),
    ),
)

# High-volume released workflows previously pointed at these Acts, but the
# legacy rows were not eligible for production retrieval because their source
# artifact hash or exact section projection was missing. Resolve these specs
# by document identity (source_id=None), pin the first-party India Code PDF,
# and repair only the named section start. The rest of each legacy Act remains
# fail-closed until it receives the same evidence treatment.
_HIGH_VALUE_SPECS = (
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2160/1/engaadhaar.pdf",
        source_sha256="8bb18121dac4078072f3b38216548ba3ff33771fdbceb431cb5280afd0489ad2",
        source_bytes=318042,
        document_id="aadhaar-2016",
        title="Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
        anchor="aadhaar-2016/sec-31",
        section_no="31",
        section_title="Alteration of demographic information or biometric information",
        subject_area="constitutional",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2160",),
        expected_text_sha256="a57231c8479142c3a41a8d0ce222a445083aa5d56a65689140648230838c0443",
        local_artifact_path=str(ROOT / "data/raw/acts/aadhaar-2016__engaadhaar.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2033/1/200756.pdf",
        source_sha256="b6b06d2793a2b47799874f859d5949cdeadea7812bf7882fd9f879bd64e27a38",
        source_bytes=82532,
        document_id="senior-citizens-2007",
        title="TheMaintenanceandWelfareofParentsandSeniorCitizensAct,2007",
        anchor="senior-citizens-2007/sec-4",
        section_no="4",
        section_title="Maintenance of parents and senior citizens",
        subject_area="senior_citizen",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2033",),
        allow_create=True,
        promote_to_new_source=True,
        expected_text_sha256="1dced3929b25875430ca7d80b35e6fd96a92934e3fb0e2b57530c6d9d9a6b213",
        local_artifact_path=str(ROOT / "data/raw/acts/senior-citizens-2007__200756.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2033/1/200756.pdf",
        source_sha256="b6b06d2793a2b47799874f859d5949cdeadea7812bf7882fd9f879bd64e27a38",
        source_bytes=82532,
        document_id="senior-citizens-2007",
        title="TheMaintenanceandWelfareofParentsandSeniorCitizensAct,2007",
        anchor="senior-citizens-2007/sec-5",
        section_no="5",
        section_title="Application for maintenance",
        subject_area="senior_citizen",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2033",),
        allow_create=True,
        promote_to_new_source=True,
        expected_text_sha256="32103b56768ec437e509861d349cf5254efb478cf0f5a090bac17af65c44e073",
        local_artifact_path=str(ROOT / "data/raw/acts/senior-citizens-2007__200756.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2033/1/200756.pdf",
        source_sha256="b6b06d2793a2b47799874f859d5949cdeadea7812bf7882fd9f879bd64e27a38",
        source_bytes=82532,
        document_id="senior-citizens-2007",
        title="TheMaintenanceandWelfareofParentsandSeniorCitizensAct,2007",
        anchor="senior-citizens-2007/sec-9",
        section_no="9",
        section_title="Order for maintenance",
        subject_area="senior_citizen",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2033",),
        allow_create=True,
        promote_to_new_source=True,
        expected_text_sha256="9272703dea419c72281b8e3eb393506415033d82978d83ddb0f0daa2618690ea",
        local_artifact_path=str(ROOT / "data/raw/acts/senior-citizens-2007__200756.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2033/1/200756.pdf",
        source_sha256="b6b06d2793a2b47799874f859d5949cdeadea7812bf7882fd9f879bd64e27a38",
        source_bytes=82532,
        document_id="senior-citizens-2007",
        title="TheMaintenanceandWelfareofParentsandSeniorCitizensAct,2007",
        anchor="senior-citizens-2007/sec-23",
        section_no="23",
        section_title="Transfer of property to be void in certain circumstances",
        subject_area="senior_citizen",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2033",),
        allow_create=True,
        promote_to_new_source=True,
        expected_text_sha256="b70ab51dbc18c0125a6da030aea4c13c99a238a0da4d4c52a0802aa47f1e2948",
        local_artifact_path=str(ROOT / "data/raw/acts/senior-citizens-2007__200756.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/22091/1/a1972-39.pdf",
        source_sha256="51187c0c0b2ea49003be645b3bd8bba0e9b7b393a605ed71b325acf6af3fcda7",
        source_bytes=195218,
        document_id="gratuity-1972",
        title="Payment of Gratuity Act 1972",
        anchor="gratuity-1972/sec-4-a",
        section_no="4",
        section_title="Payment of gratuity",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/22091",),
        expected_text_sha256="5346a42affecccf0aa4b2d97ad98a86d13bc80f550c7ab6825fe688a3d67165d",
        local_artifact_path=str(ROOT / "data/raw/acts/gratuity-1972__a1972-39.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/22091/1/a1972-39.pdf",
        source_sha256="51187c0c0b2ea49003be645b3bd8bba0e9b7b393a605ed71b325acf6af3fcda7",
        source_bytes=195218,
        document_id="gratuity-1972",
        title="Payment of Gratuity Act 1972",
        anchor="gratuity-1972/sec-7-a",
        section_no="7",
        section_title="Determination of the amount of gratuity",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/22091",),
        expected_text_sha256="108dfb87cfe63b38f429281cebb4c535dbe78756b13744d08f266370451fbb6e",
        local_artifact_path=str(ROOT / "data/raw/acts/gratuity-1972__a1972-39.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/22091/1/a1972-39.pdf",
        source_sha256="51187c0c0b2ea49003be645b3bd8bba0e9b7b393a605ed71b325acf6af3fcda7",
        source_bytes=195218,
        document_id="gratuity-1972",
        title="Payment of Gratuity Act 1972",
        anchor="gratuity-1972/sec-8",
        section_no="8",
        section_title="Recovery of gratuity",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/22091",),
        expected_text_sha256="9ab024cd05fb2ffa37d150280eda8a4754b99a1747c1b9147856d038c9bdccb8",
        local_artifact_path=str(ROOT / "data/raw/acts/gratuity-1972__a1972-39.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2152/1/a195219.pdf",
        source_sha256="63b77d9a2804b6ed164e369d7553e7eb515172acb57e1b72ad0103ce6c0656dd",
        source_bytes=614832,
        document_id="epf-1952",
        title="Employees' Provident Funds and Miscellaneous Provisions Act 1952",
        anchor="epf-1952/sec-7A-a@2017-01-01",
        section_no="7A",
        section_title="Determination of moneys due from employers",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2152",),
        as_at=date(2017, 1, 1),
        allow_create=True,
        expected_text_sha256="76573ce6f002f28f6db434279ed37538abc04194b94a7990d147996a93d918f3",
        local_artifact_path=str(ROOT / "data/raw/acts/epf-1952__a195219.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2152/1/a195219.pdf",
        source_sha256="63b77d9a2804b6ed164e369d7553e7eb515172acb57e1b72ad0103ce6c0656dd",
        source_bytes=614832,
        document_id="epf-1952",
        title="Employees' Provident Funds and Miscellaneous Provisions Act 1952",
        anchor="epf-1952/sec-8@2017-01-01",
        section_no="8",
        section_title="Mode of recovery of moneys due from employers",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2152",),
        as_at=date(2017, 1, 1),
        allow_create=True,
        expected_text_sha256="d155f088cf63b293e89cda8b078f8af753564d117b9aa6c55f353b705bf20b1f",
        local_artifact_path=str(ROOT / "data/raw/acts/epf-1952__a195219.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2152/1/a195219.pdf",
        source_sha256="63b77d9a2804b6ed164e369d7553e7eb515172acb57e1b72ad0103ce6c0656dd",
        source_bytes=614832,
        document_id="epf-1952",
        title="Employees' Provident Funds and Miscellaneous Provisions Act 1952",
        anchor="epf-1952/sec-8A@2017-01-01",
        section_no="8A",
        section_title="Recovery of moneys by employers and contractors",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2152",),
        as_at=date(2017, 1, 1),
        allow_create=True,
        expected_text_sha256="a93464c61710396d4b81ecba064729e6cd3913110e4cf7866c98ea60dedcc615",
        local_artifact_path=str(ROOT / "data/raw/acts/epf-1952__a195219.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2152/1/a195219.pdf",
        source_sha256="63b77d9a2804b6ed164e369d7553e7eb515172acb57e1b72ad0103ce6c0656dd",
        source_bytes=614832,
        document_id="epf-1952",
        title="Employees' Provident Funds and Miscellaneous Provisions Act 1952",
        anchor="epf-1952/sec-14B@2017-01-01",
        section_no="14B",
        section_title="Power to recover damages",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/2152",),
        as_at=date(2017, 1, 1),
        allow_create=True,
        expected_text_sha256="80567b599a0942678a5beac96a8c84c9769e0e051fc5dfbc7db624c4d52c2afb",
        local_artifact_path=str(ROOT / "data/raw/acts/epf-1952__a195219.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20349/1/a1948-34.pdf",
        source_sha256="8175c6e93ef439bda2aaa77cea55e5f5af08d1493fde3c06d9b2c8f5cc1d3672",
        source_bytes=688084,
        document_id="esi-1948",
        title="Employees' State Insurance Act 1948",
        anchor="esi-1948/sec-40",
        section_no="40",
        section_title="Principal employer to pay contributions in the first instance",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/20349",),
        expected_text_sha256="fa4788ab69c359d4ca39900b03a78dfd361f96f281be461457f8c3f13df0a913",
        local_artifact_path=str(ROOT / "data/raw/acts/esi-1948__a1948-34.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20349/1/a1948-34.pdf",
        source_sha256="8175c6e93ef439bda2aaa77cea55e5f5af08d1493fde3c06d9b2c8f5cc1d3672",
        source_bytes=688084,
        document_id="esi-1948",
        title="Employees' State Insurance Act 1948",
        anchor="esi-1948/sec-46-a",
        section_no="46",
        section_title="Benefits",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/20349",),
        expected_text_sha256="342d7a135c6f0b783d008755128a8dfad15be379b416630ad5aaadd53e13b22a",
        local_artifact_path=str(ROOT / "data/raw/acts/esi-1948__a1948-34.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20349/1/a1948-34.pdf",
        source_sha256="8175c6e93ef439bda2aaa77cea55e5f5af08d1493fde3c06d9b2c8f5cc1d3672",
        source_bytes=688084,
        document_id="esi-1948",
        title="Employees' State Insurance Act 1948",
        anchor="esi-1948/sec-56",
        section_no="56",
        section_title="Medical benefit",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/20349",),
        expected_text_sha256="762fd0a67138037fc6d130f1aa80a5121f27d0d5d9edb5d9a1e97494f27529de",
        local_artifact_path=str(ROOT / "data/raw/acts/esi-1948__a1948-34.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20349/1/a1948-34.pdf",
        source_sha256="8175c6e93ef439bda2aaa77cea55e5f5af08d1493fde3c06d9b2c8f5cc1d3672",
        source_bytes=688084,
        document_id="esi-1948",
        title="Employees' State Insurance Act 1948",
        anchor="esi-1948/sec-58",
        section_no="58",
        section_title="Provision of medical treatment by State Government",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/20349",),
        expected_text_sha256="f69fb88ff4acfdadcf15531de82dc4659d3bbe3adbf3949e7a105aa6ff1e5d4a",
        local_artifact_path=str(ROOT / "data/raw/acts/esi-1948__a1948-34.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/16823/1/aA2020-36.pdf",
        source_sha256="53ad67f75fbc874fd837274e9e887fac7a21cc55c7454398b2cdb96046fd7967",
        source_bytes=1020695,
        document_id="social-security-code-2020",
        title="Code on Social Security 2020",
        anchor="social-security-code-2020/sec-112@2025-11-21",
        section_no="112",
        section_title="Helpline, facilitation centre, etc",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/16823",),
        as_at=date(2025, 11, 21),
        expected_text_sha256="ec82ff1aac0b1e6baceed227d89d2ebce70e18c73cd77ce6e3971cff304e76b1",
        local_artifact_path=str(ROOT / "data/raw/acts/social-security-code-2020__aA2020-36.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/16823/1/aA2020-36.pdf",
        source_sha256="53ad67f75fbc874fd837274e9e887fac7a21cc55c7454398b2cdb96046fd7967",
        source_bytes=1020695,
        document_id="social-security-code-2020",
        title="Code on Social Security 2020",
        anchor="social-security-code-2020/sec-113@2025-11-21",
        section_no="113",
        section_title="Registration of unorganized workers, gig workers and platform workers",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/16823",),
        as_at=date(2025, 11, 21),
        expected_text_sha256="dd7edf1e0f112691d535897c8ca4ad9d656ad2814f1cb8e6ed2b563d3c02ffb5",
        local_artifact_path=str(ROOT / "data/raw/acts/social-security-code-2020__aA2020-36.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/16823/1/aA2020-36.pdf",
        source_sha256="53ad67f75fbc874fd837274e9e887fac7a21cc55c7454398b2cdb96046fd7967",
        source_bytes=1020695,
        document_id="social-security-code-2020",
        title="Code on Social Security 2020",
        anchor="social-security-code-2020/sec-114-a@2025-11-21",
        section_no="114",
        section_title="Schemes for gig works and platform workers",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/16823",),
        as_at=date(2025, 11, 21),
        expected_text_sha256="93214fb9606b18f63459b2ea6a8771b1939bfb336d078e89715b3f9e91b95d1b",
        local_artifact_path=str(ROOT / "data/raw/acts/social-security-code-2020__aA2020-36.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/16823/1/aA2020-36.pdf",
        source_sha256="53ad67f75fbc874fd837274e9e887fac7a21cc55c7454398b2cdb96046fd7967",
        source_bytes=1020695,
        document_id="social-security-code-2020",
        title="Code on Social Security 2020",
        anchor="social-security-code-2020/sec-141@2025-11-21",
        section_no="141",
        section_title="Social Security Fund",
        subject_area="service_employment",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/16823",),
        as_at=date(2025, 11, 21),
        expected_text_sha256="81c68f2a4a0cc7a48ac26b352f009300686fdc6946b395775a0bd71cf7d87e18",
        local_artifact_path=str(ROOT / "data/raw/acts/social-security-code-2020__aA2020-36.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/11098/1/building-and-other-construction-workers-act-1996.pdf",
        source_sha256="55ef0ffe392f49882ee408cce039de8aff562f827af70df9a115af53699100fb",
        source_bytes=980075,
        document_id="bocw-1996",
        title="Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
        anchor="bocw-1996/sec-12@1996-01-01",
        section_no="12",
        section_title="Registration of building workers as beneficiaries:-(1) Every building worker who has completed",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1996, 1, 1),
        expected_text_sha256="7b2e12d33e3cc5ee9a4d0db4ea1d2504a3c85c41363a425667876bf7244d240c",
        local_artifact_path=str(ROOT / "data/raw/acts/bocw-1996__building-and-other-construction-workers-act-1996.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/11098/1/building-and-other-construction-workers-act-1996.pdf",
        source_sha256="55ef0ffe392f49882ee408cce039de8aff562f827af70df9a115af53699100fb",
        source_bytes=980075,
        document_id="bocw-1996",
        title="Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
        anchor="bocw-1996/sec-13@1996-01-01",
        section_no="13",
        section_title="Identity cards:-(1) The Board shall give to every beneficiary an identity card with his photograph",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1996, 1, 1),
        expected_text_sha256="a18ca0726ecfbb0363774d446fb6a7c40d2c5fb7f12f4d3e11d38034c32c66bf",
        local_artifact_path=str(ROOT / "data/raw/acts/bocw-1996__building-and-other-construction-workers-act-1996.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/11098/1/building-and-other-construction-workers-act-1996.pdf",
        source_sha256="55ef0ffe392f49882ee408cce039de8aff562f827af70df9a115af53699100fb",
        source_bytes=980075,
        document_id="bocw-1996",
        title="Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
        anchor="bocw-1996/sec-14@1996-01-01",
        section_no="14",
        section_title="Cessation as a beneficiary:-(1) A building worker who has been registered as a beneficiary under",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1996, 1, 1),
        expected_text_sha256="d0183622699cd7cdac13e01226cdf34071a263be79cafcc0dd539bd42f0d44ab",
        local_artifact_path=str(ROOT / "data/raw/acts/bocw-1996__building-and-other-construction-workers-act-1996.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/11098/1/building-and-other-construction-workers-act-1996.pdf",
        source_sha256="55ef0ffe392f49882ee408cce039de8aff562f827af70df9a115af53699100fb",
        source_bytes=980075,
        document_id="bocw-1996",
        title="Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
        anchor="bocw-1996/sec-22@1996-01-01",
        section_no="22",
        section_title="Functions of the Boards:-(1) The Board may",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1996, 1, 1),
        expected_text_sha256="eff008af72b198608eeb35c3d7f4dbb1a672a082991d97b06a9365484b556903",
        local_artifact_path=str(ROOT / "data/raw/acts/bocw-1996__building-and-other-construction-workers-act-1996.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/11098/1/building-and-other-construction-workers-act-1996.pdf",
        source_sha256="55ef0ffe392f49882ee408cce039de8aff562f827af70df9a115af53699100fb",
        source_bytes=980075,
        document_id="bocw-1996",
        title="Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act 1996",
        anchor="bocw-1996/sec-60@1996-01-01",
        section_no="60",
        section_title="Power of Central Government to give directions:-The Central Government may give directions to",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1996, 1, 1),
        expected_text_sha256="c8e6e7e88a4d99286efbd4387088c2a68f6c123aac6b32fb6774591c5d1ef828",
        local_artifact_path=str(ROOT / "data/raw/acts/bocw-1996__building-and-other-construction-workers-act-1996.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20347/1/a1923-08.pdf",
        source_sha256="5971ed922ffb5229a24e6ffe679d33695eb6164a084d7d217dc21c7cdbb39b1e",
        source_bytes=481577,
        document_id="employees-compensation-1923",
        title="Employees' Compensation Act 1923",
        anchor="employees-compensation-1923/sec-3-a@1961-01-01",
        section_no="3",
        section_title="Employer’s liability for compensation",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1961, 1, 1),
        expected_text_sha256="afa12f367fa3b53235880c1d96d79e28bdc486b134d0dd31550c52b37f7ae00e",
        local_artifact_path=str(ROOT / "data/raw/acts/employees-compensation-1923__a1923-08.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20347/1/a1923-08.pdf",
        source_sha256="5971ed922ffb5229a24e6ffe679d33695eb6164a084d7d217dc21c7cdbb39b1e",
        source_bytes=481577,
        document_id="employees-compensation-1923",
        title="Employees' Compensation Act 1923",
        anchor="employees-compensation-1923/sec-4@1961-01-01",
        section_no="4",
        section_title="Amount of compensation",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1961, 1, 1),
        expected_text_sha256="1268616f2c43ed988e4751200e2340f19670f3e563bea7deee96f670c874eb67",
        local_artifact_path=str(ROOT / "data/raw/acts/employees-compensation-1923__a1923-08.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/20347/1/a1923-08.pdf",
        source_sha256="5971ed922ffb5229a24e6ffe679d33695eb6164a084d7d217dc21c7cdbb39b1e",
        source_bytes=481577,
        document_id="employees-compensation-1923",
        title="Employees' Compensation Act 1923",
        anchor="employees-compensation-1923/sec-10-a@1961-01-01",
        section_no="10",
        section_title="Notice and claim",
        subject_area="service_employment",
        kind="generic_act_section",
        as_at=date(1961, 1, 1),
        expected_text_sha256="8d5aa613c83f7dc1c2c6afdb33e779da93640b2ec0219f737a58cec5edc126b9",
        local_artifact_path=str(ROOT / "data/raw/acts/employees-compensation-1923__a1923-08.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf",
        source_sha256="414fb1edd9b0f7fbc2839ad92fb2b29ebfa3b557e70e928ab4a535802199e3e7",
        source_bytes=450383,
        document_id="consumer-protection-2019",
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35@2021-09-17",
        section_no="35",
        section_title="Manner in which complaint shall be made",
        subject_area="consumer",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/15256",),
        as_at=date(2021, 9, 17),
        expected_text_sha256="9467377788f7a1df5bfe4c3ed39f9d08eca3b26a34ac8e4985f120bfa73b639f",
        local_artifact_path=str(ROOT / "data/raw/acts/consumer-protection-2019__eng201935.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf",
        source_sha256="414fb1edd9b0f7fbc2839ad92fb2b29ebfa3b557e70e928ab4a535802199e3e7",
        source_bytes=450383,
        document_id="consumer-protection-2019",
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-38-a@2021-09-17",
        section_no="38",
        section_title="Procedure on admission of complaint",
        subject_area="consumer",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/15256",),
        as_at=date(2021, 9, 17),
        expected_text_sha256="c8b4dd7e768e41cc3dfff2c86ed25b78045a230ccbadcf50075b7bf0f1f0b7aa",
        local_artifact_path=str(ROOT / "data/raw/acts/consumer-protection-2019__eng201935.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2121/1/A2013-30.pdf",
        source_sha256="e9dfc8dd1ade250262725225b226952cc2be7668d90914aefc4b0082be70743f",
        source_bytes=572058,
        document_id="rfctlarr-2013",
        title="Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
        anchor="rfctlarr-2013/sec-11",
        section_no="11",
        section_title="Publication of preliminary notification and power of officers",
        subject_area="property",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/12916",),
        expected_text_sha256="7287187e6749475b4d0fdaa9cfe37b8717d1f7dca570e47a4419500e20e2aa01",
        local_artifact_path=str(ROOT / "data/raw/acts/rfctlarr-2013__A2013-30.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2121/1/A2013-30.pdf",
        source_sha256="e9dfc8dd1ade250262725225b226952cc2be7668d90914aefc4b0082be70743f",
        source_bytes=572058,
        document_id="rfctlarr-2013",
        title="Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
        anchor="rfctlarr-2013/sec-24-a",
        section_no="24",
        section_title="Land acquisition process under Act No",
        subject_area="property",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/12916",),
        expected_text_sha256="569e8f8454d537afc7fb6e9f8d651f966db3a611cb54958b2755bc43afcfc754",
        local_artifact_path=str(ROOT / "data/raw/acts/rfctlarr-2013__A2013-30.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2121/1/A2013-30.pdf",
        source_sha256="e9dfc8dd1ade250262725225b226952cc2be7668d90914aefc4b0082be70743f",
        source_bytes=572058,
        document_id="rfctlarr-2013",
        title="Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
        anchor="rfctlarr-2013/sec-30",
        section_no="30",
        section_title="Award of solatium",
        subject_area="property",
        kind="generic_act_section",
        accepted_source_urls=("https://www.indiacode.nic.in/handle/123456789/12916",),
        expected_text_sha256="8eb7dbd267677ded017e8e6f31f18d6d516fdf48bdba28dc18c48ed815b9d75e",
        local_artifact_path=str(ROOT / "data/raw/acts/rfctlarr-2013__A2013-30.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2006/1/A2002-54.pdf",
        source_sha256="e7213c51ab3d7d24718f84c4278871eac231e6f0000631b6a1ae7a2544fe6019",
        source_bytes=446159,
        document_id="sarfaesi-2002",
        title="Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002",
        anchor="sarfaesi-2002/sec-13-a@1993-01-01",
        section_no="13",
        section_title="Enforcement of security interest",
        subject_area="banking_credit",
        kind="generic_act_section",
        as_at=date(1993, 1, 1),
        expected_text_sha256="d3fb8239d17c78fc1b1e19eff9b5b720615ba7b6d0bb2147d99218cf05575e0d",
        local_artifact_path=str(ROOT / "data/raw/acts/sarfaesi-2002__A2002-54.pdf"),
    ),
    RepairSpec(
        source_id=None,
        source_url="https://www.indiacode.nic.in/bitstream/123456789/2006/1/A2002-54.pdf",
        source_sha256="e7213c51ab3d7d24718f84c4278871eac231e6f0000631b6a1ae7a2544fe6019",
        source_bytes=446159,
        document_id="sarfaesi-2002",
        title="Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002",
        anchor="sarfaesi-2002/sec-17-a@1993-01-01",
        section_no="17",
        section_title="Application against measures to recover secured debts]",
        subject_area="banking_credit",
        kind="generic_act_section",
        as_at=date(1993, 1, 1),
        expected_text_sha256="23416762884e27339a3d58f96ec7ff93eaebdea34a3cf83099ec9113ea4f8a4e",
        local_artifact_path=str(ROOT / "data/raw/acts/sarfaesi-2002__A2002-54.pdf"),
    ),
)

SPECS = (*SPECS, *_HIGH_VALUE_SPECS)


def _fetch_pinned_pdf(spec: RepairSpec) -> bytes:
    if spec.local_artifact_path:
        path = Path(spec.local_artifact_path).resolve()
        if not path.is_file():
            raise RuntimeError(f"refusing {spec.document_id}: pinned local artifact is missing")
        data = path.read_bytes()
        if len(data) != spec.source_bytes or hashlib.sha256(data).hexdigest() != spec.source_sha256:
            raise RuntimeError(f"refusing {spec.document_id}: pinned local artifact hash/size mismatch")
        return data
    candidates = refetch_act_pdfs(spec.source_url)
    matches = [
        data
        for data, _status, _code, _url in candidates
        if len(data) == spec.source_bytes
        and hashlib.sha256(data).hexdigest() == spec.source_sha256
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id}: expected one pinned PDF, found {len(matches)}"
        )
    return matches[0]


def _court_fees_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    chunks = list(chunk_act(spec.document_id, text, act_title=spec.title))
    matches = [
        chunk
        for chunk in chunks
        if chunk.metadata.get("section_no") == spec.section_no
        and re.search(
            r"\AThe Court-Fees Act, 1870, Section 7\s+7\.\s+"
            r"Computation of fees payable in certain suits\.",
            chunk.text,
        )
        and re.search(r"(?:^|/)sec-7-a(?:@|$)", chunk.anchor)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing court-fees repair: expected one operative Section 7 start, found {len(matches)}"
        )
    return matches[0].text


def _constitution_article_46_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    matches = list(
        re.finditer(
            r"(?ims)^\s*46\.\s+Promotion of educational and economic interests of Scheduled\s+"
            r"Castes, Scheduled Tribes and other weaker sections\.\s*[—-]\s*"
            r"(?P<body>The State shall.*?)(?=^\s*47\.\s+Duty of the State to raise the level of nutrition)",
            text,
        )
    )
    candidates = [
        (
            "46. Promotion of educational and economic interests of Scheduled Castes, "
            "Scheduled Tribes and other weaker sections.—"
            + match.group("body").strip()
        )
        for match in matches
    ]
    candidates = [
        candidate
        for candidate in candidates
        if re.search(r"The\s+State\s+shall\s+promote", candidate, flags=re.IGNORECASE)
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"refusing constitution repair: expected one Article 46 body, found {len(candidates)}"
        )
    return f"Constitution of India, Article 46\n\n{candidates[0]}"


def _drugs_act_section_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    chunks = list(chunk_act(spec.document_id, text, act_title=spec.title))
    heading_pattern = re.compile(
        rf"\ADrugs and Cosmetics Act 1940,\s+Section {re.escape(spec.section_no)}\s+"
        rf"{re.escape(spec.section_no)}\.\s+{re.escape(spec.section_title)}(?:\s*[.—-]|\s|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    matches = [
        chunk
        for chunk in chunks
        if chunk.metadata.get("section_no") == spec.section_no
        and heading_pattern.search(chunk.text)
        and re.search(
            rf"(?:^|/)sec-{re.escape(spec.section_no)}-a(?:@|$)",
            chunk.anchor,
        )
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: expected one operative section start, found {len(matches)}"
        )
    return matches[0].text


def _drugs_act_section_27_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    matches = list(
        re.finditer(
            r"(?ims)^\s*(?:\d+\s*\[\s*)?27\.\s+Penalty\s+for\s+manufacture,\s+sale,\s+etc\.,?\s+"
            r"of\s+drugs\s+in\s+contravention\s+of\s+this\s+Chapter\.\s*[—-]\s*"
            r"(?P<body>Whoever.*?)(?=^\s*27A\.)",
            text,
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section 27: expected one official match, found {len(matches)}"
        )
    candidates = [
        "Drugs and Cosmetics Act 1940, Section 27\n\n" + match.group(0).strip()
        for match in matches
        if re.search(r"Whoever\s*,?\s*himself", match.group("body"), flags=re.IGNORECASE)
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section 27: expected one official body, found {len(candidates)}"
        )
    return candidates[0]


def _crpc_section_154_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    matches = list(
        re.finditer(
            r"(?ims)^154\.\s+Information\s+in\s+cognizable\s+cases\.\s*[—-]\s*"
            r"\(1\)\s+.*?(?=^\s*STATE\s+AMENDMENT\s*$)",
            text,
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section 154: expected one operative official match, found {len(matches)}"
        )
    body = re.sub(r"\s+", " ", matches[0].group(0)).strip()
    if not re.search(
        r"refusal .*?officer in charge .*?Superintendent of Police",
        body,
        flags=re.IGNORECASE,
    ):
        raise RuntimeError(
            f"refusing {spec.document_id} section 154: extracted body lacks the refusal/escalation clause"
        )
    return f"{spec.title}, Section {spec.section_no}\n\n{body}"


def _bnss_section_body(text: str, section_no: str, next_section_no: str) -> str:
    matches = list(
        re.finditer(
            rf"(?ims)^\s*{re.escape(section_no)}\.\s+\(1\)\s+.*?(?=^\s*{re.escape(next_section_no)}\.)",
            text,
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing bnss-2023 section {section_no}: expected one operative official section, found {len(matches)}"
        )
    body = matches[0].group(0).strip()
    if section_no == "173" and (
        "Local inquiry." in body or "THE GAZETTE OF INDIA EXTRAORDINARY" in body
    ):
        # The extracted Gazette page contains a marginal-note/contents column
        # between sub-section (1)(ii) and the continuation of Section 173.
        body, removed = re.subn(
            r"(?s)(signed within three days by the person giving it,)\s+.*?"
            r"(?=and the substance thereof shall be entered)",
            r"\1\n",
            body,
            count=1,
        )
        if removed != 1:
            raise RuntimeError(
                "refusing bnss-2023 section 173: page-column artifact boundary not found"
            )
    return body.strip()


def _bnss_section_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    if spec.section_no == "173-a":
        section_no, next_section_no = "173", "174"
    elif spec.section_no == "175":
        section_no, next_section_no = "175", "176"
    else:
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: unsupported section mapping"
        )
    body = _bnss_section_body(text, section_no, next_section_no)
    required_phrases = {
        "173": ("cognizable offence", "electronic communication", "Superintendent of Police"),
        "175": ("Any Magistrate", "order such an investigation"),
    }[section_no]
    if not all(phrase.lower() in body.lower() for phrase in required_phrases):
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: official section lacks required operative phrases"
        )
    return f"{spec.title}, Section {section_no}\n\n{body}"


def _bnss_paragraph_173_4_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    text, _pages = extract_pdf_text(pdf_bytes)
    section = _bnss_section_body(text, "173", "174")
    matches = list(
        re.finditer(
            r"(?ims)^\(4\)\s+Any person aggrieved.*\Z",
            section,
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} paragraph 173(4): expected one operative official paragraph, found {len(matches)}"
        )
    body = matches[0].group(0).strip()
    if not all(
        phrase.lower() in body.lower()
        for phrase in ("refusal", "Superintendent of Police", "Magistrate")
    ):
        raise RuntimeError(
            f"refusing {spec.document_id} paragraph 173(4): official paragraph lacks required operative phrases"
        )
    return f"{spec.title}, Section 173(4)\n\n{body}"


def _bnss_chunk_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    if spec.section_no == "173-c":
        return _bnss_paragraph_173_4_text(spec, pdf_bytes)
    return _bnss_section_text(spec, pdf_bytes)


def _anchor_without_snapshot(anchor: str) -> str:
    return re.sub(r"@\d{4}-\d{2}-\d{2}$", "", str(anchor or ""))


def _generic_act_section_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    """Extract one exact section-start chunk from a pinned Act artifact."""
    text, _pages = extract_pdf_text(pdf_bytes)
    chunks = list(chunk_act(spec.document_id, text, act_title=spec.title))
    target_anchor = _anchor_without_snapshot(spec.anchor)
    matches = [
        chunk
        for chunk in chunks
        if str(chunk.metadata.get("section_no") or "") == spec.section_no
        and _anchor_without_snapshot(chunk.anchor) == target_anchor
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: "
            f"expected one exact section chunk, found {len(matches)}"
        )
    extracted_title = str(matches[0].metadata.get("section_title") or "").strip()
    if extracted_title != spec.section_title:
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: "
            f"manifest title does not match extracted heading ({spec.section_title!r} != {extracted_title!r})"
        )
    extracted_text = matches[0].text
    if (
        spec.expected_text_sha256 is not None
        and hashlib.sha256(extracted_text.encode()).hexdigest()
        != spec.expected_text_sha256
    ):
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: extracted text hash changed"
        )
    return extracted_text


def _ipc_section_378_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    """Extract IPC 378 across the India Code PDF's page-layout artifacts."""
    text, _pages = extract_pdf_text(pdf_bytes)
    matches = list(
        re.finditer(
            r"(?ims)^378\.\s*Theft\s*\.-{1,2}.*?"
            r"(?=^379\.\s*Punishment\s+for\s+theft)",
            text,
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"refusing {spec.document_id} section 378: expected one bounded official section, found {len(matches)}"
        )
    raw = matches[0].group(0).strip()
    raw = re.sub(r"-{10,}", " ", raw)
    raw = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not all(
        phrase.lower() in raw.lower()
        for phrase in ("movable property", "without that person's consent", "commit theft")
    ):
        raise RuntimeError(
            "refusing ipc-1860 section 378: extracted body lacks required operative phrases"
        )
    return f"{spec.title}, Section {spec.section_no}\n\n{raw}"


def canonical_text(spec: RepairSpec, pdf_bytes: bytes) -> str:
    if spec.kind == "court_fees":
        return _court_fees_text(spec, pdf_bytes)
    if spec.kind == "constitution_article_46":
        return _constitution_article_46_text(spec, pdf_bytes)
    if spec.kind == "drugs_act_section":
        return _drugs_act_section_text(spec, pdf_bytes)
    if spec.kind == "drugs_act_section_27":
        return _drugs_act_section_27_text(spec, pdf_bytes)
    if spec.kind == "crpc_section_154":
        return _crpc_section_154_text(spec, pdf_bytes)
    if spec.kind == "bnss_chunk":
        return _bnss_chunk_text(spec, pdf_bytes)
    if spec.kind == "generic_act_section":
        return _generic_act_section_text(spec, pdf_bytes)
    if spec.kind == "ipc_section_378":
        return _ipc_section_378_text(spec, pdf_bytes)
    raise RuntimeError(f"unknown repair kind: {spec.kind}")


def _embed(text: str) -> tuple[str, str]:
    dense, sparse = get_embedder().encode_with_sparse([text])
    return embedding_to_halfvec_literal(dense[0]), sparse_to_jsonb(sparse[0])


async def _ensure_canonical_source(
    conn: asyncpg.Connection,
    spec: RepairSpec,
    *,
    predecessor_source_id: int,
) -> int:
    """Create or validate a new canonical source without rewriting its predecessor."""
    expected_url_hash = hashlib.sha256(spec.source_url.encode()).hexdigest()
    targets = await conn.fetch(
        """
        SELECT id, source_type, origin, url, canonical_url_hash,
               raw_sha256, raw_bytes_size, provenance_tier, metadata
        FROM sources
        WHERE canonical_url_hash=$1
        FOR UPDATE
        """,
        expected_url_hash,
    )
    if len(targets) > 1:
        raise RuntimeError(f"refusing {spec.document_id}: duplicate canonical source identities")
    target = targets[0] if targets else None
    if target is None:
        target_id = await conn.fetchval(
            """
            INSERT INTO sources (
                source_type, origin, url, canonical_url_hash, raw_sha256,
                raw_bytes_size, provenance_tier, metadata
            ) VALUES ('bare_act','indiacode',$1,$2,$3,$4,'canonical',$5::jsonb)
            RETURNING id
            """,
            spec.source_url,
            expected_url_hash,
            spec.source_sha256,
            spec.source_bytes,
            json.dumps(
                {
                    "canonical_pdf_hash_pinned": True,
                    "canonical_pdf_url": spec.source_url,
                    "replaces_unverified_source_id": predecessor_source_id,
                    "replaces_unverified_source_urls": list(spec.accepted_source_urls),
                    "predecessor_content_verified": False,
                    "source_transition": "independent_first_party_artifact_replacement",
                }
            ),
        )
        return int(target_id)
    if not _canonical_target_matches_artifact(target, spec):
        raise RuntimeError(f"refusing {spec.document_id}: canonical target source conflicts")
    raw_metadata = target["metadata"] or {}
    target_metadata = (
        json.loads(raw_metadata) if isinstance(raw_metadata, str) else dict(raw_metadata)
    )
    expected_transition = {
        "replaces_unverified_source_id": predecessor_source_id,
        "replaces_unverified_source_urls": list(spec.accepted_source_urls),
        "predecessor_content_verified": False,
        "source_transition": "independent_first_party_artifact_replacement",
    }
    if (
        not all(target_metadata.get(key) == value for key, value in expected_transition.items())
        or target["raw_bytes_size"] is None
    ):
        # A prior run may already have materialized this exact canonical PDF
        # under a different document alias. Reuse it only when the artifact
        # identity is exact; never merge merely because titles look similar.
        reuse_predecessor_ids = {
            int(value)
            for value in target_metadata.get("reused_predecessor_source_ids", [])
            if str(value).isdigit()
        }
        singular_predecessor = target_metadata.get("reused_predecessor_source_id")
        if str(singular_predecessor).isdigit():
            reuse_predecessor_ids.add(int(singular_predecessor))
        reuse_predecessor_ids.add(predecessor_source_id)
        updated = await conn.execute(
            """
            UPDATE sources
            SET raw_bytes_size=$1,
                metadata=COALESCE(metadata, '{}'::jsonb) || $2::jsonb
            WHERE id=$3
              AND raw_sha256=$4
              AND raw_bytes_size IS NOT DISTINCT FROM $5
              AND provenance_tier='canonical'
            """,
            spec.source_bytes,
            json.dumps({
                "canonical_source_reused": True,
                "reused_for_document_id": spec.document_id,
                # Preserve the first predecessor across every section in
                # this document batch; later calls may resolve the new
                # canonical source as their current document source.
                "reused_predecessor_source_id": target_metadata.get(
                    "reused_predecessor_source_id", predecessor_source_id
                ),
                "reused_predecessor_source_ids": sorted(reuse_predecessor_ids),
            }),
            target["id"],
            spec.source_sha256,
            target["raw_bytes_size"],
        )
        if updated != "UPDATE 1":
            raise RuntimeError(
                f"refusing {spec.document_id}: canonical target changed during reuse"
            )
    return int(target["id"])


def _expected_metadata_matches(existing: asyncpg.Record, expected: dict) -> bool:
    raw_metadata = existing["metadata"] or {}
    current = json.loads(raw_metadata) if isinstance(raw_metadata, str) else dict(raw_metadata)
    return all(current.get(key) == value for key, value in expected.items())


def _metadata_json(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or {})


def _metadata_cas_value(value: object) -> str | None:
    if value is None:
        return None
    return _metadata_json(value)


def _projection_metadata(spec: RepairSpec) -> dict[str, object]:
    if not spec.expected_text_sha256:
        raise RuntimeError(
            f"refusing {spec.document_id} section {spec.section_no}: exact text hash is required"
        )
    metadata: dict[str, object] = {
        "section_no": spec.section_no,
        "section_title": spec.section_title,
        "canonical_artifact_sha256": spec.source_sha256,
        "canonical_text_sha256": spec.expected_text_sha256,
        "canonical_repair": True,
        "provenance_verification_method": "refetch_hash_and_exact_section_extraction",
        "source_url": spec.source_url,
    }
    if spec.as_at is not None:
        metadata["consolidation_as_at"] = spec.as_at.isoformat()
    return metadata


def _canonical_target_matches_artifact(target: asyncpg.Record, spec: RepairSpec) -> bool:
    return (
        target["source_type"] == "bare_act"
        and target["origin"] == "indiacode"
        and target["url"] == spec.source_url
        and target["raw_sha256"] == spec.source_sha256
        and target["raw_bytes_size"] in (None, spec.source_bytes)
        and target["provenance_tier"] == "canonical"
    )


async def repair_spec(conn: asyncpg.Connection, spec: RepairSpec, *, dry_run: bool) -> dict:
    source_id = spec.source_id
    if source_id is None:
        source_candidates = await conn.fetch(
            """
            SELECT s.id
            FROM sources s
            JOIN documents d ON d.source_id = s.id
            WHERE d.doc_id = $1
            ORDER BY s.id
            """,
            spec.document_id,
        )
        if len(source_candidates) != 1:
            raise RuntimeError(
                f"refusing {spec.document_id}: expected one source linked by document identity, found {len(source_candidates)}"
            )
        source_id = int(source_candidates[0]["id"])
    source = await conn.fetchrow(
        """
        SELECT id, url, canonical_url_hash, raw_sha256, raw_bytes_size,
               source_type, provenance_tier
        FROM sources WHERE id=$1
        """,
        source_id,
    )
    accepted_source_urls = (spec.source_url, *spec.accepted_source_urls)
    accepted_url_hashes = {
        hashlib.sha256(url.encode()).hexdigest() for url in accepted_source_urls
    }
    if (
        source is None
        or source["url"] not in accepted_source_urls
        or source["source_type"] != "bare_act"
    ):
        raise RuntimeError(f"refusing {spec.document_id}: source identity mismatch")
    if (
        spec.promote_to_new_source
        and source["url"] != spec.source_url
        and (source["raw_sha256"] is not None or source["raw_bytes_size"] is not None)
    ):
        raise RuntimeError(
            f"refusing {spec.document_id}: predecessor artifact is known but not verified equivalent"
        )
    expected_url_hash = hashlib.sha256(spec.source_url.encode()).hexdigest()
    if source["canonical_url_hash"] not in (None, *accepted_url_hashes):
        raise RuntimeError(f"refusing {spec.document_id}: existing canonical URL hash conflicts")
    if source["raw_sha256"] not in (None, spec.source_sha256):
        raise RuntimeError(f"refusing {spec.document_id}: existing source hash conflicts")
    if source["raw_bytes_size"] not in (None, spec.source_bytes):
        raise RuntimeError(f"refusing {spec.document_id}: existing source size conflicts")

    documents = await conn.fetch(
        "SELECT id, title, source_id FROM documents WHERE doc_id=$1",
        spec.document_id,
    )
    if len(documents) > 1:
        raise RuntimeError(f"refusing {spec.document_id}: duplicate document identities")
    document = documents[0] if documents else None
    if document is None or document["title"] != spec.title:
        raise RuntimeError(f"refusing {spec.document_id}: document identity mismatch")
    if not spec.promote_to_new_source and document["source_id"] != source_id:
        raise RuntimeError(f"refusing {spec.document_id}: document source identity mismatch")

    pdf_bytes = _fetch_pinned_pdf(spec)
    text = sanitize_for_db(canonical_text(spec, pdf_bytes))
    dense, sparse = _embed(text)
    metadata = _projection_metadata(spec)

    async def apply_in_transaction() -> dict:
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"law-rag-stage37-source:{source_id}:{expected_url_hash}",
        )
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"law-rag-stage37-chunk:{spec.document_id}:{spec.anchor}",
        )
        current_source = await conn.fetchrow(
            """
            SELECT id, url, canonical_url_hash, raw_sha256, raw_bytes_size,
                   source_type, provenance_tier
            FROM sources WHERE id=$1
            FOR UPDATE
            """,
            source_id,
        )
        if current_source is None or any(
            current_source[key] != source[key]
            for key in (
                "url", "canonical_url_hash", "raw_sha256", "raw_bytes_size",
                "source_type", "provenance_tier",
            )
        ):
            raise RuntimeError(f"refusing {spec.document_id}: predecessor source changed during repair")

        current_documents = await conn.fetch(
            "SELECT id, title, source_id FROM documents WHERE doc_id=$1 FOR UPDATE",
            spec.document_id,
        )
        if len(current_documents) > 1:
            raise RuntimeError(f"refusing {spec.document_id}: duplicate document identities")
        current_document = current_documents[0] if current_documents else None
        if current_document is None or current_document["title"] != spec.title:
            raise RuntimeError(f"refusing {spec.document_id}: document changed during repair")
        if not spec.promote_to_new_source and current_document["source_id"] != source_id:
            raise RuntimeError(f"refusing {spec.document_id}: document source changed during repair")

        if spec.promote_to_new_source:
            canonical_source_id = await _ensure_canonical_source(
                conn,
                spec,
                predecessor_source_id=source_id,
            )
            document_update = await conn.execute(
                """
                UPDATE documents SET source_id=$1
                WHERE id=$2 AND source_id = ANY($3::bigint[])
                """,
                canonical_source_id,
                current_document["id"],
                [source_id, canonical_source_id],
            )
            if document_update != "UPDATE 1":
                raise RuntimeError(
                    f"refusing {spec.document_id}: document source compare-and-swap updated {document_update}"
                )
        else:
            source_update = await conn.execute(
                """
                UPDATE sources
                SET url=$1, canonical_url_hash=$2, raw_sha256=$3, raw_bytes_size=$4,
                    provenance_tier='canonical',
                    metadata=COALESCE(metadata, '{}'::jsonb) || $5::jsonb
                WHERE id=$6 AND url=$7
                  AND canonical_url_hash IS NOT DISTINCT FROM $8
                  AND raw_sha256 IS NOT DISTINCT FROM $9
                  AND raw_bytes_size IS NOT DISTINCT FROM $10
                    AND source_type=$11
                    AND provenance_tier IS NOT DISTINCT FROM $12
                """,
                spec.source_url,
                expected_url_hash,
                spec.source_sha256,
                spec.source_bytes,
                json.dumps(
                    {
                        "canonical_pdf_hash_pinned": True,
                        "canonical_pdf_url": spec.source_url,
                        "legacy_source_urls": list(spec.accepted_source_urls),
                    }
                ),
                source_id,
                source["url"],
                source["canonical_url_hash"],
                source["raw_sha256"],
                source["raw_bytes_size"],
                source["source_type"],
                source["provenance_tier"],
            )
            if source_update != "UPDATE 1":
                raise RuntimeError(
                    f"refusing {spec.document_id}: source compare-and-swap updated {source_update}"
                )

        rows = await conn.fetch(
            """
            SELECT id, text, provenance_verified, source_type, subject_area,
                   chunk_strategy, metadata, quarantined, as_at
            FROM chunks
            WHERE document_id=$1 AND anchor=$2 AND as_at IS NOT DISTINCT FROM $3
            ORDER BY id
            """,
            current_document["id"],
            spec.anchor,
            spec.as_at,
        )
        if len(rows) > 1:
            raise RuntimeError(
                f"refusing {spec.document_id}: duplicate live chunks for {spec.anchor}"
            )
        existing = rows[0] if rows else None
        target_text = text
        target_dense, target_sparse = dense, sparse
        if spec.expected_text_sha256 is not None:
            if (
                spec.expected_text_sha256 is None
                or hashlib.sha256(text.encode()).hexdigest()
                != spec.expected_text_sha256
            ):
                raise RuntimeError(
                    f"refusing {spec.document_id} section {spec.section_no}: fetched canonical text hash changed"
                )
            if existing is None and not spec.allow_create:
                raise RuntimeError(
                    f"refusing {spec.document_id} section {spec.section_no}: canonical projection is missing"
                )
            if existing is not None and (
                hashlib.sha256(existing["text"].encode()).hexdigest()
                != spec.expected_text_sha256
            ):
                raise RuntimeError(
                    f"refusing {spec.document_id} section {spec.section_no}: existing projection text hash changed"
                )
            # The fetched official text and the migration-declared hash must
            # agree; never preserve a stale projection after source changes.
            target_text = text
            target_dense, target_sparse = dense, sparse
        result = {
            "document_id": spec.document_id,
            "chunk_id": existing["id"] if existing else None,
            "anchor": spec.anchor,
            "text_chars": len(target_text),
            "action": "repair",
        }
        if existing and (
            existing["text"] == target_text
            and existing["provenance_verified"]
            and existing["source_type"] == "bare_act"
            and existing["subject_area"] == spec.subject_area
            and existing["chunk_strategy"] == "section"
            and not existing["quarantined"]
            and _expected_metadata_matches(existing, metadata)
        ):
            result["action"] = "no_op"
            return result

        if existing:
            chunk_update = await conn.execute(
                """
                UPDATE chunks
                SET source_type='bare_act', subject_area=$1, paragraph_no=NULL,
                    token_count=$2, text=$3, embedding=$4::halfvec,
                    embedding_sparse=$5::jsonb, chunk_strategy='section',
                    metadata=COALESCE(metadata, '{}'::jsonb) || $6::jsonb,
                    provenance_verified=true, provenance_verified_at=now(), quarantined=false
                WHERE id=$7 AND document_id=$8 AND anchor=$9
                  AND as_at IS NOT DISTINCT FROM $17
                  AND text IS NOT DISTINCT FROM $10
                  AND provenance_verified IS NOT DISTINCT FROM $11
                  AND source_type IS NOT DISTINCT FROM $12
                  AND subject_area IS NOT DISTINCT FROM $13
                  AND chunk_strategy IS NOT DISTINCT FROM $14
                  AND metadata IS NOT DISTINCT FROM $15::jsonb
                  AND quarantined IS NOT DISTINCT FROM $16
                """,
                spec.subject_area,
                len(text.split()),
                target_text,
                target_dense,
                target_sparse,
                json.dumps(metadata),
                existing["id"],
                current_document["id"],
                spec.anchor,
                existing["text"],
                existing["provenance_verified"],
                existing["source_type"],
                existing["subject_area"],
                existing["chunk_strategy"],
                _metadata_cas_value(existing["metadata"]),
                existing["quarantined"],
                spec.as_at,
            )
            if chunk_update != "UPDATE 1":
                raise RuntimeError(
                    f"refusing {spec.document_id}: chunk compare-and-swap updated {chunk_update}"
                )
        else:
            chunk_id = await conn.fetchval(
                """
                INSERT INTO chunks (
                    document_id, source_type, subject_area, anchor, paragraph_no,
                    token_count, text, embedding, embedding_sparse, chunk_strategy,
                    as_at, metadata, quarantined, provenance_verified, provenance_verified_at
                ) VALUES ($1,'bare_act',$2,$3,NULL,$4,$5,$6::halfvec,$7::jsonb,
                          'section',$8,$9::jsonb,false,true,now())
                RETURNING id
                """,
                current_document["id"],
                spec.subject_area,
                spec.anchor,
                len(target_text.split()),
                target_text,
                target_dense,
                target_sparse,
                spec.as_at,
                json.dumps(metadata),
            )
            result["chunk_id"] = chunk_id
        result["action"] = "repaired"
        return result

    if dry_run:
        rows = await conn.fetch(
            """
            SELECT id, text, provenance_verified, source_type, subject_area,
                   chunk_strategy, metadata, quarantined, as_at
            FROM chunks
            WHERE document_id=$1 AND anchor=$2 AND as_at IS NOT DISTINCT FROM $3
            ORDER BY id
            """,
            document["id"],
            spec.anchor,
            spec.as_at,
        )
        if len(rows) > 1:
            raise RuntimeError(
                f"refusing {spec.document_id}: duplicate live chunks for {spec.anchor}"
            )
        existing = rows[0] if rows else None
        if existing is None and not spec.allow_create:
            raise RuntimeError(
                f"refusing {spec.document_id} section {spec.section_no}: canonical projection is missing"
            )
        if existing is not None and (
            spec.expected_text_sha256 is not None
            and hashlib.sha256(existing["text"].encode()).hexdigest()
            != spec.expected_text_sha256
        ):
            raise RuntimeError(
                f"refusing {spec.document_id} section {spec.section_no}: existing projection text hash changed"
            )
        if spec.promote_to_new_source:
            targets = await conn.fetch(
                """
                SELECT id, source_type, origin, url, canonical_url_hash,
                       raw_sha256, raw_bytes_size, provenance_tier, metadata
                FROM sources WHERE canonical_url_hash=$1
                """,
                expected_url_hash,
            )
            if len(targets) > 1:
                raise RuntimeError(f"refusing {spec.document_id}: duplicate canonical source identities")
            if targets:
                target = targets[0]
                if not _canonical_target_matches_artifact(target, spec):
                    raise RuntimeError(f"refusing {spec.document_id}: canonical target source conflicts")
                if document["source_id"] not in (source_id, target["id"]):
                    raise RuntimeError(f"refusing {spec.document_id}: document source promotion conflict")
            elif document["source_id"] != source_id:
                raise RuntimeError(f"refusing {spec.document_id}: document source promotion conflict")
        return {
            "document_id": spec.document_id,
            "chunk_id": existing["id"] if existing else None,
            "anchor": spec.anchor,
            "text_chars": len(text),
            "action": "no_op"
            if existing
            and existing["text"] == text
            and existing["provenance_verified"]
            and existing["source_type"] == "bare_act"
            and existing["subject_area"] == spec.subject_area
            and existing["chunk_strategy"] == "section"
            and not existing["quarantined"]
            and _expected_metadata_matches(existing, metadata)
            else "create" if existing is None else "repair",
        }

    async with conn.transaction():
        return await apply_in_transaction()


async def run(
    *,
    dry_run: bool = False,
    only: str | None = None,
    high_value_only: bool = False,
) -> list[dict]:
    if not dry_run and only is None and not high_value_only:
        raise RuntimeError("refusing broad apply; select --high-value-only or one document")
    settings = get_settings()
    conn = await asyncpg.connect(settings.resolved_database_url_host_side)
    try:
        pool = _HIGH_VALUE_SPECS if high_value_only else SPECS
        specs = [spec for spec in pool if only is None or spec.document_id == only]
        if not specs:
            scope = "high-value" if high_value_only else "full"
            raise RuntimeError(f"no repair specs selected for {scope} scope")
        if dry_run:
            return [await repair_spec(conn, spec, dry_run=True) for spec in specs]
        async with conn.transaction():
            return [await repair_spec(conn, spec, dry_run=False) for spec in specs]
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=[spec.document_id for spec in SPECS])
    parser.add_argument(
        "--high-value-only",
        action="store_true",
        help="select only the reviewed high-value authority batch",
    )
    args = parser.parse_args()
    if not args.dry_run and args.only is None and not args.high_value_only:
        parser.error("refusing broad apply; pass --high-value-only or --only")
    for result in asyncio.run(
        run(
            dry_run=args.dry_run,
            only=args.only,
            high_value_only=args.high_value_only,
        )
    ):
        print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
