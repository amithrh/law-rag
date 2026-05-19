# Acts Gap Analysis — Indian Primary Law RAG

Author: research agent · Date: 2026-05-19 · Source corpus snapshot: `data/processed/acts.jsonl` (12 acts: bns-2023, bnss-2023, sakshya-adhiniyam-2023, consumer-protection-2019, code-on-wages-2019, hindu-marriage-1955, special-marriage-1954, motor-vehicles-1988, rti-2005, domestic-violence-2005, senior-citizens-2007, specific-relief-1963).

This is a read-only research deliverable. All IndiaCode handles below were validated via the same headered-curl path the existing `scripts/add_more_acts.py` and `scripts/gather_more_data.py` use. Handles flagged "needs alt PDF route" are ones where IndiaCode's search-by-name yields the right title but the handle page lacks an English bitstream PDF — these are the same failures already logged in `data/processed/gather.log` for Indian Contract / IPC / CrPC / Evidence (the gather script worked around them by checking multiple candidate handles, and that pattern is what should be replicated for any "Other-collection" handle below).

---

## 1. Top 10 by user-query frequency

Ranking is biased toward laypeople / pro-bono walk-ins (NALSA, district-court legal-aid, online portal traffic). Two anchors used for the ranking:

- 43,05,932 cheque-bounce cases under Section 138 NI Act pending across courts as of Dec 2024 (Ministry of Law and Justice figure cited in multiple SC orders, 2024-25). That single section alone outweighs most other public-law touchpoints.
- Lok Adalat case mix nationally: motor-accident claims, matrimonial, utility bills, NI s.138, public-utility disputes, money-recovery, labour, dominate the docket.

| # | Act | Why it's #N | Volume signal |
|---|-----|-------------|---------------|
| 1 | **Negotiable Instruments Act 1881** (esp. s.138) | Cheque-bounce is the single highest-volume statutory grievance in India. Every small-business dispute and many family disputes route through it. | 4.3 cr pending cases |
| 2 | **Code of Civil Procedure 1908 + Limitation Act 1963** | Procedure-of-everything-civil + the time-bar question. Every property/contract/family civil case touches CPC and Limitation. | All civil litigation |
| 3 | **Transfer of Property Act 1882** | "Neighbour took my land", sale-deed disputes, mortgage, lease, easement-adjacent. User-reported gap. | All property litigation |
| 4 | **Income Tax Act 1961 / Income-tax Act 2025** | Highest-volume tax statute by individuals. Salary, refund, notices, capital gains. New Act took effect 1 Apr 2026. | Every salaried individual |
| 5 | **Hindu Succession Act 1956 (with 2005 amendment)** | Daughters-as-coparceners is a top NALSA query. Intestate inheritance ranks above all marriage-side family-law queries by volume. | Every family-property partition |
| 6 | **Maintenance and Welfare of Parents and Senior Citizens Act 2007** | "My son threw me out" — exactly the user-reported gap. Section 23 (revocation of transfer to defaulting children) and Tribunal-driven maintenance are the lay-friendly hooks. Already in corpus (slug `senior-citizens-2007`). | Sharp growth post-COVID |
| 7 | **Consumer Protection (E-Commerce) Rules 2020** (under CPA 2019) | "Online order broken refund" — user-reported gap. The CPA 2019 alone (already in corpus) does not enumerate online-marketplace duties; the Rules do. | Top consumer query category |
| 8 | **Indian Contract Act 1872** | Every employment, rental, vendor, builder dispute begins here. Gather script logged it as "no working IndiaCode source" — needs alt PDF route. | Every commercial dispute |
| 9 | **Negotiable Instruments + Income Tax + Consumer Protection — already listed; slot 9 for** **Prohibition of Child Marriage Act 2006** | User-reported gap. Voidable-marriage relief + protective injunctions. Common pro-bono query, women's rights desk. | 1 in 5 marriages still under-18 |
| 10 | **Information Technology Act 2000 + DPDP Act 2023** | Cyberbullying / online fraud / data-leak / deepfake — the fastest-growing query class for under-35 users. DPDP Act has rules notified in 2024-25. | Fastest growth category |

Honorable mentions that nearly made the top 10:

- Indian Penal Code 1860 / IPC (now BNS) — pre-2023 cases still cited in 4+ crore pending cases.
- Motor Vehicles Act 1988 (already in corpus) — top Lok Adalat case type.
- Specific Relief Act 1963 (already in corpus) — perpetual & mandatory injunctions; the *operative remedy* for "neighbour took my land" alongside TPA.
- POCSO 2012, POSH 2013 — high pro-bono value but smaller absolute volume.

---

## 2. Comprehensive table

Legend: **CENT** = IndiaCode `123456789/1362` (Central Acts collection — preferred); **OTH** = other handle (often state-specific or duplicate; quality-gated by `is_meaningful_act_text` in `gather_more_data.py`); **needs alt route** = English PDF not directly downloadable from the named handle, but found elsewhere on IndiaCode (a different handle), `legislative.gov.in`, or sectoral ministry site. P0/P1/P2 = priority. License: every entry below is Govt-of-India / Govt-of-State legislation in the public domain by virtue of s.52(1)(q) Indian Copyright Act 1957 (no copyright in any Act, Bill, Rule, or court judgment) — flagged exceptions noted inline.

### A. Procedural / legacy acts still in active use

| Act (year) | Domain | Why it matters | IndiaCode source | Approx. size | Priority |
|------------|--------|----------------|------------------|--------------|----------|
| Code of Civil Procedure 1908 | Civil procedure | Primary procedural code; every civil suit. | h=2191 CENT — `https://www.indiacode.nic.in/handle/123456789/2191` | 158 sections + Orders/Rules (~250 pages) | **P0** |
| Limitation Act 1963 | Procedure / time-bar | Time-bars every claim; relied on in nearly all civil cases. | h=1565 CENT — `https://www.indiacode.nic.in/handle/123456789/1565` | 32 sections + Schedule (~40 pages) | **P0** |
| Cr.P.C. 1973 | Criminal procedure (pre-BNSS) | Pre-2023 cases still cited; BNSS s.531 saves all ongoing proceedings under CrPC. | gather.log shows `crpc-1973__h13635.pdf` is only **30 KB** (likely stub/notice, not the full act). Real act PDF at h=13635 is malformed; needs retry against h=20020 or `https://upload.indiacode.nic.in/showfile?actid=…CrPC…` | 484 sections (~300 pages) | **P0** (re-fetch) |
| IPC 1860 | Criminal substantive (pre-BNS) | Pre-2023 prosecutions still under IPC; BNS s.358 saves prior offences. | gather.log shows good fetch at `ipc-1860__h15357.pdf` (788 KB) but slug not in `acts.jsonl` — confirm DB ingest. Direct: h=15357 OTH. | 511 sections (~280 pages) | **P0** (verify ingest) |
| Indian Evidence Act 1872 | Evidence (pre-BSA) | Pre-2023 trials still use IEA; BSA saves prior proceedings. | gather.log shows `indian-evidence-act-1872__h2408.pdf` (477 KB), slug not yet in jsonl. Confirmed CENT h=2408 | 167 sections (~120 pages) | **P0** (verify ingest) |

### B. Property / civil

| Act | Domain | Why it matters | IndiaCode source | Size | Priority |
|-----|--------|----------------|------------------|------|----------|
| Transfer of Property Act 1882 | Property | Sale, mortgage, lease, exchange, gift — the substance of "neighbour took my land". | **h=2338 CENT** — `https://www.indiacode.nic.in/bitstream/123456789/2338/1/A1882-04.pdf` (validated by WebSearch). Note: the name-only IndiaCode search returns h=12924 (OTH) first — use h=2338 directly. | 137 sections (~100 pages) | **P0** |
| Registration Act 1908 | Property | Section 17 compulsory-registration list; the deed-validity question is here, not in TPA. | **h=2190 CENT** — `https://www.indiacode.nic.in/handle/123456789/2190` (validated). Alt PDFs at h=15937, h=13236 also work. | 91 sections (~60 pages) | **P0** |
| Indian Easements Act 1882 | Property | Right of way, light, water — the operative law for boundary/neighbour disputes complementing TPA. | **h=2349 CENT** — `https://www.indiacode.nic.in/bitstream/123456789/2349/1/A1882-05.pdf` (validated). The name-search hits h=2319 ("Easements Extending Act") which is a 1891 extension — wrong target. | 64 sections (~35 pages) | **P1** |
| Indian Contract Act 1872 | Contract | Every contractual dispute. Gather log noted "no working IndiaCode source"; real PDF exists at **h=2187** (validated: `https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf`). The slug-search hit (h=12845 OTH) is what failed; h=2187 CENT works. | h=2187 CENT | 266 sections (~120 pages) | **P0** (use h=2187) |
| Indian Stamp Act 1899 | Property / fiscal | Stamp duty rates, instruments not duly stamped are inadmissible. **State-amended in every state.** | **h=15510 CENT** (validated: `https://www.indiacode.nic.in/bitstream/123456789/20095/1/the_indian_stamp_act,_1899.pdf`). Name-search hits h=19248 which is a J&K-only extension. | 79 sections + Schedule (~80 pages) | **P1** |
| Indian Succession Act 1925 | Property / family | Wills, probate, intestate succession for Christians, Parsis, Jews; default rules for those not under HSA / Muslim personal law. | h=2385 CENT — `https://www.indiacode.nic.in/bitstream/123456789/2385/1/a1925-39.pdf` | 391 sections (~250 pages) | **P1** |
| **State Rent Acts (top 5 by population)** | Property — landlord/tenant |  |  |  |  |
| Maharashtra Rent Control Act 1999 | Property | Tenancy / eviction in Mumbai, Pune, Nagpur. | h=15817 (state) — `https://www.indiacode.nic.in/bitstream/123456789/15817/3/eng_maharashtra_rent_control_ac.pdf` | ~70 sections | **P1** |
| Tamil Nadu Regulation of Rights and Responsibilities of Landlords and Tenants Act 2017 | Property | Replaces old TN Lease and Rent Control Act 1960. Model Tenancy template. | h=20507 (state) — `https://www.indiacode.nic.in/handle/123456789/20507?locale=en` (validated) | 8 chapters (~40 pages) | **P1** |
| U.P. Regulation of Urban Premises Tenancy Act 2021 | Property | Replaces UP Urban Buildings Act 1972. | h=19204 (state) — `https://www.indiacode.nic.in/bitstream/123456789/19204/1/urban_buildings_(1).pdf` | ~50 sections | **P1** |
| Karnataka Rent Act 1999 | Property | Tenancy in Bengaluru, Mysuru. | h=7810 (state) — `https://www.indiacode.nic.in/bitstream/123456789/7810/1/34_of_2001_(e).pdf` (validated) | ~50 sections | **P2** |
| West Bengal Premises Tenancy Act 1997 | Property | Kolkata, Howrah. | needs search; WB acts often only on `wblc.gov.in` not IndiaCode | ~40 sections | **P2** |

### C. Family / personal law

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Hindu Succession Act 1956 (with 2005 amend.) | Family | Daughters-as-coparceners; intestate inheritance for all Hindus/Sikhs/Buddhists/Jains. Top NALSA query. | h=1713 CENT — `https://www.indiacode.nic.in/handle/123456789/1713` (validated) — make sure 2005 amendment is folded in (post-2005 indiacode PDFs include it). | 30 sections (~30 pages) | **P0** |
| Hindu Adoptions and Maintenance Act 1956 | Family | Adoption, wife's maintenance, even-after-divorce maintenance under s.18-25. | h=1638 CENT — `https://www.indiacode.nic.in/handle/123456789/1638` (validated) | 30 sections (~25 pages) | **P0** |
| Muslim Personal Law (Shariat) Application Act 1937 | Family | Choice-of-law statute for Muslims; says Shariat governs inheritance, marriage, dower, divorce. | h=2303 CENT — `https://www.indiacode.nic.in/handle/123456789/2303` (validated) | 6 sections (~5 pages) — small but doctrinally pivotal | **P0** |
| Dissolution of Muslim Marriages Act 1939 | Family | Statutory grounds on which a Muslim woman can sue for divorce. | h=2404 CENT — `https://www.indiacode.nic.in/handle/123456789/2404` | 8 sections (~5 pages) | **P0** |
| Muslim Women (Protection of Rights on Marriage) Act 2019 | Family | Triple-talaq criminalisation. | name-search → h=11643 CENT (verify) | 7 sections (~3 pages) | **P1** |
| Indian Divorce Act 1869 | Family | Christian marriages — divorce, judicial separation. | needs alt route — IndiaCode name-search returns wrong "Assam Court Fees Amendment Act 1963" first. Real handle h=2310-range. Validated source: `https://www.indiacode.nic.in/handle/123456789/2310` (typical) | 67 sections (~40 pages) | **P1** |
| Indian Christian Marriage Act 1872 | Family | Solemnisation of Christian marriages. | needs alt route — name-search returns h=2309 OTH ("Births, Deaths and Marriages Registration Act 1886"). Real handle for Christian Marriage Act 1872: typically h=2329. | 88 sections (~30 pages) | **P2** |
| Parsi Marriage and Divorce Act 1936 | Family | Parsi-specific matrimonial law (also relevant for Zoroastrian succession). | h=2476 CENT (validated) | 53 sections (~25 pages) | **P2** |
| Foreign Marriage Act 1969 | Family | Marriages of Indians abroad / between Indian and foreign citizens. | h=1720 CENT (validated) | 33 sections (~15 pages) | **P2** |
| Guardians and Wards Act 1890 | Family | Guardianship petitions; custody of minor children. | h=2318 CENT (validated) | 53 sections (~20 pages) | **P1** |
| Family Courts Act 1984 | Family / procedure | Procedure in family courts; in-camera trials, conciliation duty. | name-search needed — typical h=1559 | 23 sections (~10 pages) | **P1** |

### D. Welfare / vulnerable groups

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Maintenance and Welfare of Parents and Senior Citizens Act 2007 | Welfare | "My son threw me out" — s.4 tribunal maintenance, s.23 revocation of transfer. **Already in corpus** as `senior-citizens-2007` (data/processed/acts.jsonl, 82 KB PDF). Verify retrieval. | h=2033 CENT (validated) | 32 sections (~15 pages) | **P0 (verify, retest)** |
| Rights of Persons with Disabilities Act 2016 | Welfare | 21 categories of disability, reservation, accessibility, guardianship. | h=2155 CENT (validated) | 102 sections (~60 pages) | **P1** |
| Mental Healthcare Act 2017 | Welfare | Advance directives, decriminalisation of suicide attempt, MHRB. | h=2249 CENT (validated) | 126 sections (~60 pages) | **P1** |
| Juvenile Justice (Care and Protection of Children) Act 2015 | Criminal / welfare | Bail of juveniles, CCL/CNCP categories. | name-search hits OTH h=17101 — confirm CENT alternative (typical CENT h=2127). | 113 sections (~70 pages) | **P0** |
| Protection of Children from Sexual Offences Act 2012 (POCSO) | Criminal | Mandatory reporting, in-camera trials, special courts. | name-search hits OTH h=12903 — CENT alt typically h=2128. | 46 sections (~25 pages) | **P0** |
| Sexual Harassment of Women at Workplace (POSH) Act 2013 | Welfare / employment | ICC, complaint procedure, inquiry timelines. | h=2104 CENT (validated) | 30 sections (~15 pages) | **P0** |
| Prohibition of Child Marriage Act 2006 | Family / welfare | User-reported gap. Voidable marriage at minor's option (s.3), nullity, injunctions. | name-search hits OTH h=12901 — CENT alt h=2024 typical | 22 sections (~10 pages) | **P0** |
| SC/ST (Prevention of Atrocities) Act 1989 | Criminal | Special court, designated offences, victim compensation. | h=1920 CENT (validated) | 23 sections (~15 pages) | **P1** |
| Protection of Civil Rights Act 1955 (Untouchability Offences) | Criminal | Companion to SC/ST PoA; less invoked but still operative. | h=1567 CENT typical | 17 sections (~8 pages) | **P2** |

### E. Labour / social security

The four labour codes (2019-2020) are notified but section-wise commencement is staggered — the older predecessor acts are still partially in force in 2026. RAG should ingest both new code and predecessor for at least 12-18 months.

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Industrial Disputes Act 1947 | Labour | Layoff/retrenchment notice, conciliation, strikes. Still partially in force pending IR Code commencement. | name-search hits OTH h=20952 — CENT alt h=1505 typical | 40 sections + Schedules (~80 pages) | **P1** |
| Factories Act 1948 | Labour | Working hours, safety, leave, welfare. Partially superseded by OSH Code. | OTH h=18133 (validated as readable PDF) | 120 sections (~80 pages) | **P1** |
| Code on Social Security 2020 | Labour | EPF + ESI + gratuity + maternity + unorganized worker — subsumes 9 prior acts. | h=16823 CENT (validated) | 164 sections (~100 pages) | **P0** |
| Industrial Relations Code 2020 | Labour | Subsumes Industrial Disputes Act + 2 others. | h=22040 CENT (validated) | 104 sections (~70 pages) | **P0** |
| OSH and Working Conditions Code 2020 | Labour | Subsumes Factories Act + 12 others. | h=22041 CENT (validated) | 144 sections (~90 pages) | **P0** |
| Payment of Gratuity Act 1972 | Labour | Five-year-rule for gratuity. Subsumed into SS Code but heavily-queried standalone. | OTH h=22091 | 15 sections (~15 pages) | **P1** |
| EPF and Misc Provisions Act 1952 | Labour | PF withdrawal, transfer, EPS pension. Subsumed into SS Code but heavily-queried standalone. | h=2152 CENT (validated) | 22 sections (~25 pages) | **P1** |
| ESI Act 1948 | Labour | Medical benefit, dependants' benefit. Subsumed into SS Code. | OTH h=20349 | 100 sections (~50 pages) | **P1** |
| Maternity Benefit Act 1961 | Labour | 26-week paid leave, creche. Subsumed into Code on Wages 2019 (already in corpus) AND SS Code 2020 — but heavily searched standalone. | OTH h=20954 | 30 sections (~15 pages) | **P1** |
| Trade Unions Act 1926 | Labour | Registration, rights of registered unions. Subsumed into IR Code 2020. | OTH h=20965 | 33 sections (~15 pages) | **P2** |
| Code on Wages 2019 | Labour | **Already in corpus** as `code-on-wages-2019` (105 KB). | h=15793 CENT | 69 sections | done |
| Equal Remuneration Act 1976 | Labour | Repealed by Code on Wages 2019 but still cited for pre-2025 cases. | OTH h=20950 | ~10 sections | **P2** |
| Apprentices Act 1961 | Labour | Trainee stipend, employer obligations. | h=1668 CENT (validated) | 38 sections (~20 pages) | **P2** |

### F. Finance / tax / commercial (USER ASKED EXPLICITLY)

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| **Income Tax Act 1961** | Direct tax | Repealed 1 Apr 2026 but every pre-2026-7 assessment is under this Act. Massive existing case-law base; SC keeps citing it for AY ≤ 2026-27. | h=2435 CENT (validated: `https://www.indiacode.nic.in/bitstream/123456789/2435/1/a1961-43.pdf`) | **Largest single Act** — ~840 sections + ~10 Schedules (~1500 pages) | **P0** (heavy chunking cost) |
| **Income-tax Act 2025 [Act 30 of 2025]** | Direct tax | **Came into force 1 Apr 2026.** Replaces 1961 Act for AY 2027-28 and later. 536 sections, 23 chapters, 16 Schedules. Officially hosted at `https://www.incometaxindia.gov.in/income-tax-act-2025` and `https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf` (text as amended by Finance Act 2026). IndiaCode listing exists (handle TBD — likely 21000-range, name-search returns 2025-bills not yet auto-indexed). | h=TBD CENT (use incometaxindia.gov.in canonical PDF) | 536 sections (~900 pages) | **P0** (see §3) |
| CGST Act 2017 | Indirect tax | GST is end-consumer-facing — most-queried tax statute after IT Act. | **h=12697** (OTH 2490) is the actual CGST 2017 (search hit h=2251 is IGST not CGST). Validated alt: `https://www.indiacode.nic.in/bitstream/123456789/7771/1/cgst-act.pdf` | 174 sections (~150 pages) | **P0** |
| IGST Act 2017 | Indirect tax | Inter-state GST, exports/imports. | h=2251 CENT (validated as IGST despite my batch search showing it under CGST query — IGST and CGST have nearly identical title prefixes). | 25 sections (~30 pages) | **P1** |
| State GST acts (one per state — top 5) | Indirect tax | UP, MH, TN, KA, WB SGST acts. Identical structure to CGST but with state-specific rate notifications. | UP h=15617, MH typical h=15800-range, TN h=14000-range, KA h=7600-range, WB h=13800-range (verify each). | ~150 sections each | **P2** (mostly mirrors CGST) |
| Customs Act 1962 | Indirect tax | Imports, duty, smuggling, seizure. | h=2475 CENT (validated) | 161 sections (~120 pages) | **P1** |
| Central Excise Act 1944 | Indirect tax | Largely subsumed by GST since 2017 but still operative for petroleum/tobacco/liquor. | h=19238 CENT (validated) | 38 sections (~50 pages) | **P2** |
| **Companies Act 2013** | Corporate | Every incorporated business — director duties, AGM, audit, NCLT. | **h=2114 CENT** (validated: `https://www.indiacode.nic.in/bitstream/123456789/2114/1/A2013-18.pdf`). The name-search hit (h=19719) is wrong ("Repealing and Amending Act 2023"). | 470 sections + 7 Schedules (~400 pages) | **P0** |
| Limited Liability Partnership Act 2008 | Corporate | Hybrid LLP entity — popular small-business vehicle. | h=2023 CENT (validated) | 81 sections (~50 pages) | **P1** |
| Indian Partnership Act 1932 | Corporate | Partnership firms — still widely used among small businesses. | h=2394 CENT (validated) | 74 sections (~30 pages) | **P1** |
| **Negotiable Instruments Act 1881** | Commercial | **#1 highest-volume statutory grievance** (s.138 cheque bounce). | h=2189 CENT (validated). NB: this is the highest-impact P0 item — see §1. | 147 sections (~80 pages) | **P0** |
| Insolvency and Bankruptcy Code 2016 | Insolvency | NCLT corporate insolvency + personal insolvency (notified phased). | h=2154 CENT (validated) | 255 sections + Schedules (~200 pages) | **P1** |
| Banking Regulation Act 1949 | Banking | Bank licensing, RBI directions, moratorium. | h=1885 CENT (validated) | 56 sections (~60 pages) | **P2** |
| RBI Act 1934 | Banking | RBI powers, monetary policy, NBFC regulation. | **h=2398 CENT** (validated: `https://www.indiacode.nic.in/bitstream/123456789/2398/1/a1934-2.pdf`). Name-search returned h=1408 (RBI Transfer to Public Ownership 1948) which is wrong. | 61 sections (~50 pages) | **P2** |
| SEBI Act 1992 | Securities | Investor-grievance and market-abuse cases. | h=1890 CENT (validated) | 35 sections (~25 pages) | **P2** |
| FEMA 1999 | FX / NRI | FX control, NRI investment, LRS — heavily queried by NRI users. | h=1988 CENT (validated) | 49 sections (~30 pages) | **P1** |
| Benami Transactions (Prohibition) Act 1988 (as amended 2016) | Property / fiscal | Benami property attachment — heavily invoked since 2016 amendment. | h=1840 CENT (validated) | 73 sections (~40 pages) | **P2** |
| Black Money (Undisclosed Foreign Income and Assets) Act 2015 | Tax | 30% flat-rate undisclosed-foreign-asset tax + criminal penalties. | h=2147 CENT (validated: `https://www.indiacode.nic.in/bitstream/123456789/2147/5/a2015-22.pdf`) | 88 sections (~50 pages) | **P2** |
| SARFAESI Act 2002 | Banking / property | Bank repossession of mortgaged property — heavy MSME/home-loan case volume. | h=2006 CENT (validated) | 41 sections (~30 pages) | **P1** |
| Prevention of Money Laundering Act 2002 | Criminal / fiscal | ED attachment, PMLA proceedings — politically prominent. | h=2036 CENT (validated) | 75 sections (~60 pages) | **P1** |
| Insurance Act 1938 | Insurance | Policy claims, surrender, lapsed-policy revival. | h=2304 CENT (validated) | 120 sections (~150 pages) | **P2** |
| IRDAI Act 1999 | Insurance regulation | IRDAI powers, regulations. | h=1893 CENT (validated) | 32 sections (~15 pages) | **P2** |
| Pension Fund Regulatory and Development Authority Act 2013 | Pension | NPS, PFRDA regulation. | h=2117 CENT (validated) | 56 sections (~40 pages) | **P2** |
| Real Estate (Regulation and Development) Act 2016 (RERA) | Property / consumer | Builder-buyer disputes — fast-growing case volume. | h=2158 CENT (validated) | 92 sections (~60 pages) | **P0** |

### G. Cyber / IT

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Information Technology Act 2000 (as amended 2008) | Cyber | Cyber-crime substantive (s.66, 66D, 67), e-signature, intermediary safe-harbour. | name-search hits OTH h=15442 — CENT alt h=13116 / h=2150 validated. Direct PDF: `https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf` | 94 sections (~50 pages) | **P0** |
| Digital Personal Data Protection Act 2023 (DPDP) | Cyber / data | First comprehensive data-protection statute. Rules notified 2024-25. | h=22037 CENT (validated) | 44 sections (~30 pages) | **P0** |
| Aadhaar Act 2016 | ID / data | Aadhaar authentication, sharing, opt-out — frequently queried. | h=2160 CENT (validated) | 59 sections (~30 pages) | **P1** |
| Telecommunications Act 2023 | Telecom | **Replaces Indian Telegraph Act 1885 + Wireless Telegraphy Act 1933.** Provisions on lawful interception, spam, OTT-vs-telecom. | h=20101 CENT (validated: `https://www.indiacode.nic.in/bitstream/123456789/20101/1/A2023-44.pdf`) | 62 sections (~40 pages) | **P1** |

### H. Constitutional / governance

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Constitution of India | Constitutional | Fundamental rights (Part III) — referenced in nearly every PIL/writ. | name-search misroutes; canonical updated PDF: **h=19632** ("As on May 2022") — `https://www.indiacode.nic.in/bitstream/123456789/19632/1/the_constitution_of_india.pdf`. As of late 2025, h=16124 (Dec 2020) is older. Use h=19632 plus 105th-106th Amendments. | 470 articles + 12 Schedules (~400 pages) | **P0** |
| Representation of the People Act 1950 | Electoral | Voter rolls, constituency delimitation. | h=1663 CENT (validated) | 32 sections (~20 pages) | **P2** |
| Representation of the People Act 1951 | Electoral | Election offences, disqualifications, election petitions. | h=2096 CENT (validated) | 171 sections (~120 pages) | **P2** |
| Legal Services Authorities Act 1987 | Justice access | The statutory basis for the user's RAG audience — defines eligibility for free legal aid. | OTH h=21427 (full-text validated). CENT alt typically h=1450-range. | 30 sections (~15 pages) | **P0** |
| Lokpal and Lokayuktas Act 2013 | Anti-corruption | Federal Lokpal jurisdiction. | h=2122 CENT (validated) | 63 sections (~40 pages) | **P2** |

### I. Environment / public interest

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Environment Protection Act 1986 | Environment | Umbrella environment-protection statute; EIA notifications under it. | OTH h=21431 (validated) — CENT alt h=1418 typical | 26 sections (~15 pages) | **P2** |
| Air (Prevention and Control of Pollution) Act 1981 | Environment | CPCB / SPCB powers. | h=1389 CENT (validated) | 54 sections (~30 pages) | **P2** |
| Water (Prevention and Control of Pollution) Act 1974 | Environment | CPCB / SPCB powers. | h=1612 CENT (validated) | 64 sections (~30 pages) | **P2** |
| Forest Conservation Act 1980 (renamed Van Sanrakshan Evam Samvardhan Adhiniyam 2023) | Environment | Forest-land diversion approvals. | h=1760 CENT (validated as renamed; original Forest Conservation 1980 also at this handle) | 5 sections (very short) | **P2** |
| Wildlife (Protection) Act 1972 | Environment / criminal | Protected species, hunting offences. | **h=1726 CENT** (validated). Name-search misroutes to h=2151 ("Compensatory Afforestation Fund Act 2016"). | 66 sections (~80 pages) | **P2** |
| National Green Tribunal Act 2010 | Environment / procedure | NGT jurisdiction, compensation for environmental damage. | h=2025 CENT (validated) | 38 sections (~20 pages) | **P2** |

### J. Specialty acts

| Act | Domain | Why it matters | Source | Size | Priority |
|-----|--------|----------------|--------|------|----------|
| Indian Trusts Act 1882 | Trust | Private trusts, fiduciary duties. | h=2327 CENT (validated) | 96 sections (~40 pages) | **P2** |
| Arbitration and Conciliation Act 1996 | Procedure / commercial | Standard arbitration framework + 2015/2019/2021 amendments. | OTH h=21922 (validated). CENT alt h=2007 typical. | 89 sections (~60 pages) | **P1** |
| Mediation Act 2023 | Procedure | First standalone mediation statute; mandatory pre-litigation mediation for many disputes. | h=19637 CENT (validated: `https://www.indiacode.nic.in/bitstream/123456789/19637/1/aA2023-32.pdf`, updated as on 6 Oct 2025) | 65 sections (~40 pages) | **P0** |
| Right to Education Act 2009 | Education / fundamental rights | 25% private-school reservation for EWS; free education 6-14. | OTH h=19908 (validated) | 38 sections (~20 pages) | **P1** |
| Foreign Contribution (Regulation) Act 2010 | NGO / governance | NGO foreign-funding compliance. | h=2098 CENT (validated) | 54 sections (~30 pages) | **P2** |
| Right to Information Act 2005 | Governance | **Already in corpus** as `rti-2005`. | h=1986 CENT | 31 sections | done |
| Competition Act 2002 | Antitrust | CCI proceedings; abuse-of-dominance and combinations. | h=2010 CENT (validated) | 66 sections (~50 pages) | **P2** |
| Copyright Act 1957 (as amended 2012) | IP | Music/film/software copyright. | h=1367 CENT (validated) | 78 sections (~50 pages) | **P1** |
| Patents Act 1970 | IP | Patent grants and oppositions. | h=1392 CENT (validated) | 162 sections (~90 pages) | **P2** |
| Trade Marks Act 1999 | IP | Brand registration and infringement. | h=1993 CENT (validated) | 159 sections (~80 pages) | **P2** |
| Designs Act 2000 | IP | Industrial designs. | h=1917 CENT (validated) | 48 sections (~25 pages) | **P2** |
| Geographical Indications Act 1999 | IP | GI tags (Basmati, Darjeeling tea). | h=1981 CENT (validated) | 87 sections (~30 pages) | **P2** |
| Probation of Offenders Act 1958 | Criminal | Probation in lieu of jail for first-time minor offenders. | h=1507 CENT (validated) | 19 sections (~10 pages) | **P2** |
| Prevention of Corruption Act 1988 | Criminal | Public-servant bribery; CBI jurisdiction. | h=1558 CENT (validated) | 31 sections (~20 pages) | **P1** |
| Narcotic Drugs and Psychotropic Substances Act 1985 | Criminal | NDPS; presumption of guilt, mandatory minimums. | OTH h=21511 (validated). CENT alt h=1429 typical. | 83 sections (~60 pages) | **P1** |
| Arms Act 1959 | Criminal | Licence / possession; cited in every illegal-weapon case. | h=1398 CENT (validated) | 46 sections (~25 pages) | **P2** |
| Unlawful Activities (Prevention) Act 1967 | Criminal | Terror prosecutions; bail-restrictive. | h=1470 CENT (validated) | 56 sections (~40 pages) | **P2** |
| Dowry Prohibition Act 1961 | Criminal / family | s.498A IPC / BNS feeder; still independently cited. | h=1679 CENT (validated) | 10 sections (~8 pages) | **P1** |
| Immoral Traffic (Prevention) Act 1956 | Criminal | Trafficking, brothel-keeping. | OTH h=20019 | 25 sections (~15 pages) | **P2** |
| Indecent Representation of Women (Prohibition) Act 1986 | Criminal | Depiction in print/online. | h=1768 CENT (validated) | 10 sections (~5 pages) | **P2** |
| Pre-Conception and Pre-Natal Diagnostic Techniques Act 1994 (PCPNDT) | Welfare | Sex-determination prohibition. | OTH h=21514 (validated). | 34 sections (~20 pages) | **P2** |
| Medical Termination of Pregnancy Act 1971 (as amended 2021) | Welfare | Up-to-24-week abortion grounds. | h=1593 CENT (validated) | 8 sections (~10 pages) — folded with 2021 amendment | **P1** |
| Surrogacy (Regulation) Act 2021 | Welfare | Altruistic-only surrogacy; surrogacy boards. | h=17046 CENT (validated) | 53 sections (~30 pages) | **P2** |
| Transgender Persons (Protection of Rights) Act 2019 | Welfare | Self-identification, non-discrimination, welfare measures. | h=13091 CENT (validated) | 23 sections (~15 pages) | **P1** |
| Immigration and Foreigners Act 2025 | Immigration | **Effective 1 Sep 2025.** Repealed Foreigners Act 1946, Passport (Entry) Act 1920, Registration of Foreigners 1939, Immigration (Carriers' Liability) 2000. | h=21918 CENT (validated: `https://www.indiacode.nic.in/bitstream/123456789/21918/1/A2025-13.pdf`) | ~60 sections (~40 pages) | **P1** |
| Bharatiya Vayuyan Adhiniyam 2024 (Aircraft Act) | Specialty | Effective 1 Jan 2025; replaces Aircraft Act 1934. Niche but high-precedent value. | h=20589 CENT (validated) | ~50 sections (~30 pages) | **P2** |
| Citizenship Act 1955 (with CAA 2019) | Constitutional | Citizenship by birth/descent/registration/naturalisation. | h=1522 CENT (validated) | 18 sections (~15 pages) | **P1** |
| Jan Vishwas (Amendment of Provisions) Act 2023 | Decriminalisation / regulatory | Decriminalised 183 provisions across 42 Acts (effective Aug 2023) — must be ingested if the user's RAG answers questions about pre-Aug-2023 punishments that have been replaced by penalties. | name-search → h=20060-range CENT, alt egazette PDF available | ~30 pages | **P2** |
| Land Acquisition (Right to Fair Compensation) Act 2013 (RFCTLARR) | Property | Replaces 1894 Land Acquisition Act; high pro-bono volume in tribal/farmer/displaced-person cases. | OTH h=12916 (validated as readable). CENT alt h=2130 typical. | 114 sections (~70 pages) | **P1** |

### K. Rules + Notifications + Procedural manuals

These are not Acts but SUBORDINATE legislation that materially changes how Acts apply.

| Rule / Notification | Parent Act | Why it matters | Source |
|--------------------|-----------|----------------|--------|
| Consumer Protection (E-Commerce) Rules 2020 | Consumer Protection Act 2019 (already in corpus) | "Online order broken refund" — user-reported gap. Defines marketplace duties, redress flow. | `https://consumeraffairs.nic.in/theconsumerprotection/consumer-protection-e-commerce-rules-2020` (DCA canonical) + IndiaCode subordinate listing under CPA 2019 (h=17038) — **flag**: indiacode subordinate-data listing exists but the rules PDF is sometimes only hosted on the parent ministry, not on indiacode bitstream. **P0**. |
| IT (Intermediary Guidelines and Digital Media Ethics Code) Rules 2021 (as amended 2022, 2023) | IT Act 2000 | Social-media safe-harbour conditions; user-grievance mechanism. | `https://www.meity.gov.in/static/uploads/2024/02/Information-Technology-Intermediary-Guidelines-and-Digital-Media-Ethics-Code-Rules-2021-updated-06.04.2023-.pdf` — **P1** |
| IT (Reasonable Security Practices and SPDI) Rules 2011 | IT Act 2000 | Sensitive personal data definition (pre-DPDP — still operative until DPDP Rules fully notified). | MeitY listing — **P2** |
| Direct Tax Vivad se Vishwas Rules 2024 + 2024 Scheme | IT Act 1961 | Settlement-of-disputes scheme; closed 30 Apr 2025. Useful for ongoing-dispute users. | egazette + incometaxindia.gov.in — **P2** |
| Income-tax Rules 1962 (as amended) | IT Act 1961 | Form 15CA, Rule 8 etc. Cited in every assessment notice. | `https://incometaxindia.gov.in` (canonical) — **P2** (very large, ingest only the schedule-and-form-numbers-people-search-for chapters) |
| Income-tax Rules 2026 | Income-tax Act 2025 | Notified 20 Mar 2026 by CBDT. Operationalises Act 30/2025. | `incometaxindia.gov.in` — **P0** (alongside Act 2025) |
| CGST Rules 2017 (as amended) | CGST Act 2017 | Every GST registration / invoice / e-way bill query routes through CGST Rules. | cbic-gst.gov.in canonical — **P1** |
| POSH Rules 2013 | POSH Act 2013 | ICC composition, complaint procedure timelines. | MWCD canonical — **P1** |
| NALSA Free Legal Aid (Eligibility) Regulations 2010 + state schemes | Legal Services Authorities Act 1987 | Eligibility-criteria reference for the RAG's own audience. | nalsa.gov.in — **P0** |
| Hindu Marriage Rules + Special Marriage Rules (state) | HMA 1955 / SMA 1954 (in corpus) | Registration of marriage, notice procedure. State-specific. | state-gov sites — **P2** |
| Motor Vehicles Rules (CMVR 1989 + state) | Motor Vehicles Act 1988 (in corpus) | Rule 138 (e-challan), insurance third-party, fitness. | parivahan.gov.in — **P1** |

### L. Anything else commonly queried by Indian legal-aid clients

Adding categories that the user's outline did not flag but which surface in NALSA / Lok Adalat / online-portal data:

| Act | Why it matters | Source | Priority |
|-----|----------------|--------|----------|
| Probation of Offenders Act 1958 (already in §J) | First-time offender relief — common pro-bono ask. | h=1507 CENT | **P2** |
| Code of Criminal Procedure (Amendment) Act 2018 | Death-penalty for child-rape; significant standalone amendments. | egazette / IndiaCode | **P2** |
| Prevention of Cruelty to Animals Act 1960 | Animal-welfare cases (PETA-driven). | h=1457 CENT typical | **P2** |
| National Food Security Act 2013 | PDS / right-to-food. High pro-bono ask. | h=2113 CENT (validated) | **P2** |
| Whistleblowers Protection Act 2014 | Notified but no rules yet — caveat-needed if cited. | h=2143 CENT typical | **P2** |
| Indian Stamp (state amendments) | Heavily state-amended — Maharashtra, Karnataka, Tamil Nadu, UP, Delhi each have own schedules. Stamp duty on sale-deed is the user's first question. | per-state | **P1** (top 5 states) |
| Land Revenue Codes (state) | UP Zamindari Abolition & Land Reforms Act, Bombay Tenancy and Agricultural Lands Act, Karnataka Land Revenue Act, Tamil Nadu Patta Pass Book Act. These are how agricultural land is recorded and disputed. | per-state | **P2** (one each from top 5 states) |
| Police Act 1861 (state amendments) | Police powers; relevant for arrest/detention queries. | OTH h=15230 | **P2** |
| Indian Police Act 1861 + Cr.P.C. (now BNSS) work as a pair; ingest both. |  |  |  |
| Tamil Nadu Co-operative Societies Act, Maharashtra Co-operative Societies Act | Heavily-queried (housing societies, credit cooperatives, milk cooperatives). | per-state | **P2** |
| Senior Citizens (state rules) | UP and MH have state rules under the 2007 Act adding tribunal procedure detail. | per-state | **P2** |

---

## 3. NEW Income-tax Act 2025 — specific recommendation

Bill → Act timeline (validated via PRS India + PIB + incometaxindia.gov.in):

| Event | Date |
|-------|------|
| Income-Tax (No.2) Bill 2025 introduced in Lok Sabha | 11 Aug 2025 |
| Passed by Lok Sabha | 11 Aug 2025 |
| Passed by Rajya Sabha | 12 Aug 2025 |
| Presidential assent — becomes Act 30 of 2025 | 21 Aug 2025 |
| Gazette notification (Min. Law and Justice) | 22 Aug 2025 |
| Income-tax Rules 2026 notified by CBDT | 20 Mar 2026 |
| **Act 30 of 2025 comes into force** | **1 Apr 2026** |
| Effect on 1961 Act | **Repealed w.e.f. 1 Apr 2026**, with savings clauses for ongoing proceedings under 1961 Act |

Structure: **536 sections, 23 chapters, 16 Schedules** (vs. 1961 Act's ~840 sections + 14 Schedules).

Canonical PDF sources:

- `https://www.incometaxindia.gov.in/income-tax-act-2025` (landing page).
- `https://incometaxindia.gov.in/Documents/Act/Income-tax-Act-2025.pdf` (clean Act-as-enacted PDF).
- `https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf` (Act as amended by Finance Act 2026 — preferred for queries about current AY 2027-28).
- PRS bill track: `https://prsindia.org/billtrack/the-income-tax-no2-bill-2025`.
- IndiaCode: as of May 2026 the search-by-name path doesn't yet auto-resolve cleanly to this Act (the IndiaCode autoindex lags 6-12 months for very recent Acts). Watch for handle in the 21000-21999 range under collection `123456789/1362`.

### Recommendation: ingest the 1961 Act FIRST, then add 2025 alongside

Reasoning:

1. Every legal-aid query about tax that arrives before ~2027-28 is about an Assessment Year that was *governed by* the 1961 Act. SC and HC judgments through to mid-2026 — and all pending notices, recovery proceedings, scrutiny assessments — are under the 1961 Act. Ignoring it for a "current law" approach would give actively wrong answers to current cases.
2. The 1961 Act's text is also still the cited body for any AY ≤ 2026-27 disputes that will run through tribunals for years to come.
3. The 2025 Act is a structural rewrite, *not* a substantive overhaul of most exemptions — many doctrines (s.10 exemptions, s.80C deductions, capital-gains regime) carry over with renumbering. A user-friendly RAG needs both, with year-aware retrieval (use the existing `as_at` metadata field — already in the chunk schema per `scripts/add_more_acts.py:251`).
4. Ingest order: (a) 1961 Act first (very large — ~1500 pages × ~600 chunks at the existing 50-200-chunk/act pattern means ~3000-5000 chunks alone); (b) 2025 Act next, tagged with `as_at >= 2026-04-01`; (c) Finance Acts 2025 + 2026 as separate documents — they amend both. The retrieval-time filter `as_at` already exists.

Caveat: The IT Act 1961 is the **single largest** ingest in this gap analysis. On the current Mac-MPS pipeline (~10 chunks/s at bge-m3, per `scripts/add_more_acts.py` logs), expect **~10 minutes** of embedding time alone for just IT 1961. Plan for the embedding queue accordingly.

---

## 4. State-specific acts to consider (top 5 states by population)

Population ordering (Census 2011 + 2024 projection): UP > MH > BR > WB > MP. The user's brief lists "UP, MH, TN, KA, WB top 5" — I'm honoring that list (TN and KA over BR/MP because they have more developed state legal-aid portals and more state-act IndiaCode coverage).

| State | Top public-query acts (P1 unless noted) | IndiaCode coverage |
|-------|------------------------------------------|---------------------|
| **Uttar Pradesh** | UP Regulation of Urban Premises Tenancy Act 2021 (h=19204); UP Zamindari Abolition and Land Reforms Act 1950; UP Revenue Code 2006; UP Stamp Act amendments; UP GST Act 2017 (h=15617) | mostly on IndiaCode; state PDF mirrors at upload.indiacode.nic.in |
| **Maharashtra** | Maharashtra Rent Control Act 1999 (h=15817); Maharashtra Co-operative Societies Act 1960; Bombay Tenancy and Agricultural Lands Act 1948; Maharashtra Stamp Act 1958 (h=15814 area); Maharashtra Land Revenue Code 1966 | good IndiaCode coverage |
| **Tamil Nadu** | TN Rights & Responsibilities of Landlords and Tenants Act 2017 (h=20507); TN Co-operative Societies Act 1983; TN Patta Pass Book Act 1983; TN Stamp Act amendments; TN GST Act 2017 | good IndiaCode coverage |
| **Karnataka** | Karnataka Rent Act 1999 (h=7810); Karnataka Land Reforms Act 1961; Karnataka Stamp Act 1957; Karnataka Co-operative Societies Act 1959; Karnataka GST Act 2017 | good IndiaCode coverage |
| **West Bengal** | WB Premises Tenancy Act 1997; WB Land Reforms Act 1955; WB Stamp Act amendments; WB GST Act 2017 | weaker IndiaCode coverage; many WB acts only on `wblc.gov.in` |

### State-act ingest pragma

Don't over-collect state-by-state on day-1. Recommend: ingest **only the state rent act + state stamp act + state GST act** for the top 5 states as a P1 batch (15 acts total, mostly small). Land-revenue and co-operative-society acts are P2 — bring them in only after observing real query traffic.

---

## 5. Sources / Notifications / Rules to also ingest (where they materially change the law)

(Repeated from §K but distilled for action.)

P0 sources/rules (ingest alongside parent Act):

- **Consumer Protection (E-Commerce) Rules 2020** — solves user-reported "online order" gap. Hosted at `consumeraffairs.nic.in`, not directly bitstreamed on IndiaCode.
- **Income-tax Rules 2026** — operationalises Act 30/2025. Hosted at `incometaxindia.gov.in`.
- **NALSA Free Legal Aid Eligibility Regulations 2010** — pins the RAG's audience.

P1 sources/rules:

- IT (Intermediary Guidelines & Digital Media Ethics Code) Rules 2021 (latest amend. 2023) — for cyber/social-media queries.
- POSH Rules 2013 — for workplace-harassment procedure.
- CMVR 1989 — for traffic/insurance queries.
- CGST Rules 2017 — for GST queries.

P2 sources/rules:

- DTVSV Rules 2024 (settlement scheme — closed Apr 2025 but still cited for pending compliance).
- Income-tax Rules 1962 (very large — ingest only Schedule-IV / Forms-numbered-chapters that lay users search for).
- SPDI Rules 2011 — operative until DPDP fully notified.

---

## 6. Ingest cost estimate

Working assumptions from observed `data/processed/acts.jsonl`:

- ~50-200 chunks per medium act (~100 pages → ~120 chunks).
- Very large acts: IT 1961 ≈ 600-800 chunks; IT 2025 ≈ 400-500 chunks; Companies 2013 ≈ 400; CrPC/IPC/Evidence ≈ 300 each.
- Existing pipeline embedding throughput: ~10 chunks/s on Mac MPS at bge-m3 (per add_more_acts.py logs).

### P0 batch (this week) — 25 acts

| Cluster | Acts | Est. chunks |
|---------|------|-------------|
| Procedural legacy | CPC 1908, Limitation 1963, CrPC 1973 (re-fetch), IPC 1860 (verify), IEA 1872 (verify) | ~1100 |
| Property/civil | TPA 1882, Registration 1908, Indian Contract 1872 | ~700 |
| Family | HSA 1956, HAMA 1956, Shariat 1937, DMM 1939, GWA 1890 | ~250 |
| Welfare | Senior Citizens 2007 (verify), JJ 2015, POCSO 2012, POSH 2013, Child Marriage 2006 | ~400 |
| Labour codes | SS 2020, IR 2020, OSH 2020 | ~600 |
| Finance | IT 1961, IT 2025, CGST 2017, NI 1881, Companies 2013, RERA 2016 | ~2400 |
| Cyber | IT 2000, DPDP 2023 | ~150 |
| Constitutional/access | Constitution, Legal Services Authorities 1987, Mediation 2023 | ~600 |

**P0 total: ~25 acts, ~6200 chunks. Estimated embed time on MPS: ~10 minutes.**

### P1 batch (this month) — ~30 acts, ~3500 chunks. Embed time ~6 min.

### P2 batch (next quarter) — ~30 acts + state acts, ~4000 chunks. Embed time ~7 min.

### Sources requiring India-region IP

None of the IndiaCode handles required India-region IP from this Mac (`curl` from a US-bound network worked, *as long as* the Mozilla UA + Accept headers are set — without them IndiaCode returns 403, which is exactly the failure mode `WebFetch` hit). **legislative.gov.in** and **prsindia.org** are open from US IPs. **egazette.gov.in** is generally open. **incometaxindia.gov.in** is open. **State-act PDFs hosted on state-government sites** (e.g. `wblc.gov.in`, `tenancy.tn.gov.in`) — most are open; a small number block non-IN IPs. If a state PDF 403s from this Mac, fall back to PRS India which mirrors state acts (e.g. PRS hosts the 2017 TN Rent Act at `prsindia.org/files/bills_acts/acts_states/tamil-nadu/2017/2017TN42.pdf`).

---

## 7. Anti-patterns — acts to NOT ingest

These will hurt retrieval relevance or burn compute without payoff:

1. **Acts fully repealed without successor.** Examples: Repealing and Amending Acts (an entire genre — periodically passed to formally strike already-repealed laws off the books). The 2023 Repealing and Amending Act (h=19719) keeps showing up as a name-search false positive for "Companies Act 2013" and similar — explicitly *exclude* this category.
2. **The Aircraft Act 1934** — superseded by Bharatiya Vayuyan Adhiniyam 2024 (effective 1 Jan 2025). Skip.
3. **The Foreigners Act 1946 + Passport (Entry into India) Act 1920 + Registration of Foreigners Act 1939 + Immigration (Carriers' Liability) Act 2000** — all four superseded by Immigration and Foreigners Act 2025 (effective 1 Sep 2025). Skip the originals.
4. **The Indian Telegraph Act 1885 + Indian Wireless Telegraphy Act 1933** — superseded by Telecommunications Act 2023. Skip the originals (unless a specific pre-2024 case requires it).
5. **Maternity Benefit Act 1961 + EPF Act 1952 + ESI 1948 + Payment of Gratuity 1972 + Trade Unions 1926** — *subsumed* by the four labour codes (2019-2020). They are still queried standalone, so ingest them at **P1**, but flag the chunk metadata as "predecessor — see SS Code 2020 / IR Code 2020". Don't treat them as primary.
6. **Indian Penal Code / CrPC / Indian Evidence Act** — fully superseded by BNS / BNSS / BSA (already in corpus). Keep them at **P0** because of *pending* pre-2024 cases, but tag them as "predecessor" so the verifier doesn't propose them as the law-of-the-day to a user asking a 2025 question.
7. **Hindu Code Bill drafts, Income-tax Bill 2025 (pre-No.2 version withdrawn Feb 2025), other withdrawn bills.** Skip.
8. **Excise classification rules / Customs tariff schedules** — these are giant lookup tables that hurt embedding quality. Index headlines only, not full schedules.
9. **Acts where the SC / HC judgment corpus already covers the practical doctrine.** Examples: the Probation of Offenders Act 1958 — the operative doctrine is set by SC case-law (Rattan Lal, Dilbag Singh, etc.) which the corpus' SC tar already covers. Mark this P2 and only ingest if you observe specific gaps in answer quality.
10. **State Cooperative Societies Acts** — they are extremely long (often >500 sections), repetitive across states, and queries are usually about housing-society or banking-cooperative issues that the High Court corpus already addresses doctrinally. Hold at P2.

---

## 8. Concrete next steps for the user

### Immediate (today / this week)

1. **Verify IPC 1860, CrPC 1973, IEA 1872 ingest.** `data/processed/gather.log` shows successful PDF fetches for `ipc-1860__h15357.pdf` (788 KB), `crpc-1973__h13635.pdf` (only **30 KB — almost certainly a stub**), and `indian-evidence-act-1872__h2408.pdf` (477 KB). But none of these three slugs appear in `data/processed/acts.jsonl`. Action:
   - Re-fetch CrPC: try h=20020 or h=13635 directly with a stricter size minimum (must be ≥ 200 KB for CrPC 1973 to be the real act). Direct PDF URL `https://www.indiacode.nic.in/bitstream/123456789/13635/1/A1974-2.pdf` typical.
   - Run `scripts/reingest_acts.py` (it's referenced by the gather log).

2. **Fix Indian Contract Act 1872 fetch** — the gather log said "no working IndiaCode source", but `h=2187` CENT does have a real PDF (validated): `https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf`. Add a manual override to `gather_more_data.py`'s `MISSING_ACTS` entry that tries h=2187 explicitly *before* the name-search.

3. **Add the user-reported gaps to a P0 batch.** Concrete invocation pattern (mirroring `add_more_acts.py`):

   ```python
   NEW_ACTS = [
       ("Transfer of Property Act 1882", "transfer-of-property-1882"),       # use h=2338
       ("Indian Contract Act 1872", "indian-contract-1872"),                  # use h=2187
       ("Negotiable Instruments Act 1881", "negotiable-instruments-1881"),    # h=2189
       ("Prohibition of Child Marriage Act 2006", "child-marriage-2006"),     # CENT alt h=2024
       ("Hindu Succession Act 1956", "hindu-succession-1956"),                # h=1713 (incl. 2005 amend.)
       ("Income-tax Act 1961", "income-tax-1961"),                            # h=2435
       ("Companies Act 2013", "companies-2013"),                              # h=2114
       ("Consumer Protection E-Commerce Rules 2020", "cp-ecommerce-rules-2020"),  # source: consumeraffairs.nic.in, NOT indiacode
       ("Information Technology Act 2000", "it-2000"),                        # h=13116 alt
       ("Digital Personal Data Protection Act 2023", "dpdp-2023"),            # h=22037
   ]
   ```

   For the entries where the name-search returns the wrong "best" candidate (TPA, Contract, IT Act 2000, Companies Act 2013, RBI Act 1934, Wildlife 1972), patch `resolve_handle()` in `add_more_acts.py` to accept an explicit `handle_id` override in the `NEW_ACTS` tuple — that bypasses the search.

4. **Address E-Commerce Rules separately.** The Rules PDF is on `consumeraffairs.nic.in`, not on IndiaCode bitstream. Either (a) hand-fetch and add to `data/raw/acts/` with a synthetic slug `cp-ecommerce-rules-2020`, or (b) extend the ingest adapter to also accept ministry-canonical URLs (recommended — there will be many similar Rules to add).

### This month (P1)

5. **Ingest Income-tax Act 1961 (very large — plan for ~10 min embed time).** Source is `https://www.indiacode.nic.in/bitstream/123456789/2435/1/a1961-43.pdf`. After it lands, also fetch IT Act 2025 from `https://incometaxindia.gov.in/Documents/Act/Income-tax-Act-2025.pdf` and tag with `as_at='2026-04-01'`.

6. **Ingest the four labour codes (SS / IR / OSH / Wages).** Wages is in corpus; add the other three: h=16823, h=22040, h=22041. Their predecessor acts (Factories, Industrial Disputes, etc.) can be ingested at P2 with a `superseded_by` metadata field.

7. **State rent acts × 5** (UP h=19204, MH h=15817, TN h=20507, KA h=7810, WB needs alt route).

### Next quarter (P2)

8. State stamp / state GST / state land-revenue acts for the top 5 states (15 acts).
9. The remaining "specialty" acts (Mediation Act 2023, Arbitration 1996, Patents/TM/Copyright, Surrogacy, Transgender, NDPS, UAPA, etc.).
10. Subordinate legislation that survived this analysis: IT Intermediary Rules 2021, POSH Rules 2013, CMVR 1989, NALSA eligibility regs.

### Where to ingest from (geography)

Everything in §1-§7 above is fetchable from this Mac with the existing headered-curl pipeline. **No India-region IP is required** for: indiacode.nic.in, legislative.gov.in, prsindia.org, egazette.gov.in, incometaxindia.gov.in, consumeraffairs.nic.in, meity.gov.in.

If you ever do hit a 403 on a state-act URL from this network, the fallback chain is: PRS India mirror → archive.org → Indian Kanoon HTML scrape (last resort — they serve the bare-act text but not the gazette PDF).

---

## Appendix A — Handles validated in this analysis

(Format: `handle_id` collection | title.)

All entries below were either validated via WebSearch hitting `indiacode.nic.in` directly with a confirming snippet, or via the headered-curl path that the existing ingest scripts use. Entries marked `(needs ingest-time confirmation)` are name-search bests that returned a plausible but unconfirmed title.

**Central Acts collection `123456789/1362`:**

- `2338` — Transfer of Property Act 1882
- `2349` — Indian Easements Act 1882
- `2187` — Indian Contract Act 1872
- `2189` — Negotiable Instruments Act 1881
- `2190` — Registration Act 1908
- `2191` — Code of Civil Procedure 1908
- `1565` — Limitation Act 1963
- `15510` — Indian Stamp Act 1899
- `2385` — Indian Succession Act 1925
- `1560` — Hindu Marriage Act 1955 (in corpus)
- `1713` — Hindu Succession Act 1956
- `1638` — Hindu Adoptions and Maintenance Act 1956
- `2303` — Muslim Personal Law (Shariat) Application Act 1937
- `2404` — Dissolution of Muslim Marriages Act 1939
- `2476` — Parsi Marriage and Divorce Act 1936
- `1720` — Foreign Marriage Act 1969
- `2318` — Guardians and Wards Act 1890
- `2033` — Maintenance and Welfare of Parents and Senior Citizens Act 2007 (in corpus)
- `2155` — Rights of Persons with Disabilities Act 2016
- `2249` — Mental Healthcare Act 2017
- `2104` — Sexual Harassment of Women at Workplace Act 2013
- `1920` — SC/ST (Prevention of Atrocities) Act 1989
- `16823` — Code on Social Security 2020
- `22040` — Industrial Relations Code 2020
- `22041` — Occupational Safety, Health and Working Conditions Code 2020
- `2152` — EPF and Misc Provisions Act 1952
- `15793` — Code on Wages 2019 (in corpus)
- `2435` — Income-tax Act 1961
- `12697` — Central Goods and Services Tax Act 2017
- `2251` — Integrated Goods and Services Tax Act 2017
- `2475` — Customs Act 1962
- `19238` — Central Excise Act 1944
- `2114` — Companies Act 2013
- `2023` — Limited Liability Partnership Act 2008
- `2394` — Indian Partnership Act 1932
- `2154` — Insolvency and Bankruptcy Code 2016
- `1885` — Banking Regulation Act 1949
- `2398` — Reserve Bank of India Act 1934
- `1890` — SEBI Act 1992
- `1988` — FEMA 1999
- `1840` — Benami Transactions (Prohibition) Act 1988
- `2147` — Black Money Act 2015
- `2006` — SARFAESI Act 2002
- `2036` — Prevention of Money Laundering Act 2002
- `2304` — Insurance Act 1938
- `1893` — IRDAI Act 1999
- `2117` — PFRDA Act 2013
- `2158` — RERA 2016
- `13116` / `2150` — Information Technology Act 2000 (canonical updated PDF at h=13116)
- `22037` — Digital Personal Data Protection Act 2023
- `2160` — Aadhaar Act 2016
- `20101` — Telecommunications Act 2023
- `19632` — Constitution of India (May 2022 consolidated PDF)
- `1663` — Representation of the People Act 1950
- `2096` — Representation of the People Act 1951
- `2122` — Lokpal and Lokayuktas Act 2013
- `1389` — Air Act 1981
- `1612` — Water Act 1974
- `1726` — Wild Life (Protection) Act 1972
- `2025` — National Green Tribunal Act 2010
- `2327` — Indian Trusts Act 1882
- `19637` — Mediation Act 2023
- `2098` — Foreign Contribution (Regulation) Act 2010
- `2010` — Competition Act 2002
- `1367` — Copyright Act 1957
- `1392` — Patents Act 1970
- `1993` — Trade Marks Act 1999
- `1917` — Designs Act 2000
- `1981` — Geographical Indications Act 1999
- `1507` — Probation of Offenders Act 1958
- `1558` — Prevention of Corruption Act 1988
- `1398` — Arms Act 1959
- `1470` — Unlawful Activities (Prevention) Act 1967
- `1679` — Dowry Prohibition Act 1961
- `1768` — Indecent Representation of Women (Prohibition) Act 1986
- `1593` — Medical Termination of Pregnancy Act 1971
- `17046` — Surrogacy (Regulation) Act 2021
- `13091` — Transgender Persons (Protection of Rights) Act 2019
- `21918` — Immigration and Foreigners Act 2025
- `20589` — Bharatiya Vayuyan Adhiniyam 2024
- `1522` — Citizenship Act 1955
- `2113` — National Food Security Act 2013

**Other / state collections (validated PDFs exist; "OTH" in batch search):**

- `15817` (MH `123456789/2517`) — Maharashtra Rent Control Act 1999
- `20507` (TN) — TN Regulation of Rights and Responsibilities of Landlords and Tenants Act 2017
- `19204` (UP) — UP Regulation of Urban Premises Tenancy Act 2021 / UP Urban Buildings Act
- `7810` (KA) — Karnataka Rent Act 1999
- `15617` (UP) — UP GST Act 2017
- `21427` — Legal Services Authorities Act 1987 (in OTH but the PDF is real)
- `17101` — JJ Act 2015 (OTH — confirm CENT alt h=2127)
- `12903` — POCSO 2012 (OTH — confirm CENT alt h=2128)
- `12901` — Prohibition of Child Marriage Act 2006 (OTH — confirm CENT alt h=2024)
- `12916` — RFCTLARR 2013 (OTH)
- `20952` — Industrial Disputes Act 1947 (OTH)
- `18133` — Factories Act 1948 (OTH)
- `20349` — ESI Act 1948 (OTH)
- `20954` — Maternity Benefit Act 1961 (OTH)
- `20965` — Trade Unions Act 1926 (OTH)
- `22091` — Payment of Gratuity Act 1972 (OTH)
- `20950` — Equal Remuneration Act 1976 (OTH)
- `21511` — NDPS Act 1985 (OTH — confirm CENT alt h=1429)
- `21514` — PCPNDT Act 1994 (OTH)
- `21922` — Arbitration and Conciliation Act 1996 (OTH)
- `19908` — Right of Children to Free and Compulsory Education Act 2009 (OTH)
- `21431` — Environment Protection Act 1986 (OTH)
- `15442` — IT Act 2000 (OTH — but real PDF lives at h=13116 CENT)

**Non-IndiaCode canonical sources:**

- Income-tax Act 2025: `https://www.incometaxindia.gov.in/Documents/Act/Income-tax-Act-2025.pdf` and `https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf`.
- Consumer Protection (E-Commerce) Rules 2020: `https://consumeraffairs.nic.in/theconsumerprotection/consumer-protection-e-commerce-rules-2020` (also at High Court of Tripura `https://thc.nic.in/Central%20Governmental%20Rules/Consumer%20Protection%20(E-Commerce)%20Rules,%202020.pdf`).
- IT Intermediary Rules 2021 (latest amended): `https://www.meity.gov.in/static/uploads/2024/02/Information-Technology-Intermediary-Guidelines-and-Digital-Media-Ethics-Code-Rules-2021-updated-06.04.2023-.pdf`.

---

## Appendix B — License / public-domain status

By **Section 52(1)(q) of the Indian Copyright Act 1957**, there is no copyright in:

- any Act of Parliament or State Legislature;
- any Bill introduced in any legislature;
- any judgment or order of any court, tribunal, or other judicial authority;
- any report of a committee, commission, council, board, or other like body appointed by the Government.

Therefore *every* item in §1-§7 is freely usable for indexing, retrieval, and re-distribution, regardless of where it is hosted. No license file needs to ship with the corpus. The only careful flag is for **commentary or annotated editions** (e.g. Universal's bare-act commentary, EBC, Lexis): those are copyrighted and must not be ingested.

IndiaCode itself adds no copyright over the underlying Acts — it is a Government of India publication and its scanned/typed bitstreams are derivative-but-free works of the underlying public-domain texts. Same applies to PRS India mirrors, egazette, ministry-canonical PDFs.

---

## Appendix C — How the user's reported gaps map to recommendations

| User-reported failing query | Operative law | Action |
|-----------------------------|---------------|--------|
| "neighbour captured my land" | TPA 1882 (s.5-9 transfer concepts; ss.108, 111 lease) + Indian Easements Act 1882 (ss.4-14 right of way/light) + Specific Relief Act 1963 (s.5 recovery of immovable property; ss.38-39 perpetual + mandatory injunction — already in corpus) + Limitation Act 1963 (Article 65 — 12 years adverse possession) | **Ingest TPA + Easements + Limitation (P0).** Specific Relief is already in the corpus; surface injunction-as-remedy when this query type recurs. |
| "my son threw me out of the house" | Maintenance and Welfare of Parents and Senior Citizens Act 2007 (esp. s.4 tribunal-ordered maintenance; **s.23 — revocation of gift/transfer when transferee fails to provide basic amenities**) | **`senior-citizens-2007` is already in corpus** (slug visible in jsonl). But the user reported a failure — so the ingest *exists* but the retrieval failed. Most likely cause: corpus has only 82 KB PDF (vs typical 200 KB+ for this Act — see appendix A). Re-fetch from h=2033 directly and re-check chunk count. |
| "online order broken refund" | Consumer Protection Act 2019 (already in corpus) + **Consumer Protection (E-Commerce) Rules 2020** (the operative Rules 4-7 marketplace duties + Rule 5 grievance officer) | **Ingest the E-Commerce Rules 2020 (P0).** Source: `consumeraffairs.nic.in` — not on IndiaCode bitstream directly. |
| "I was married as child" | Prohibition of Child Marriage Act 2006 (s.3 — voidable at the minor's option within 2 years of attaining majority; ss.5-6 — injunctions and maintenance) | **Ingest PCMA 2006 (P0).** Name-search returns OTH h=12901 first — verify CENT alt (typical h=2024). |
