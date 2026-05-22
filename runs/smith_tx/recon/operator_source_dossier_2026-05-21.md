# Operator Source Dossier — Smith County, TX (smith_tx)

**Provenance / status — framework metadata, NOT part of the dossier:**

- Captured: 2026-05-21
- Source: operator manual wide recon, supplied verbatim by the operator.
- Status: **UNVERIFIED INPUT.** None of the 36 sources below has been
  empirically probed (HTTP status, access classification, stdlib
  reachability) or §13-classified (PRIMARY / SUPPORTING / ENRICHMENT).
  This dossier is the INPUT to a wide Phase 0 re-recon scheduled for the
  post-v5.4.0 resume. It has NOT been written into
  `config/counties/smith_tx.json` and the §16 Source-of-Record Matrix has
  NOT been rebuilt from it. URLs in the dossier body and in its reference
  list partially diverge (e.g. the Foreclosures and Delinquent-Tax-Sales
  page numbers, the Smith CAD search host) — those discrepancies are
  preserved as-is and are for the empirical re-recon to resolve.
- See `runs/smith_tx/recon/RECON_REOPEN_PENDING.md` for the re-recon plan.

--- BEGIN OPERATOR DOSSIER (VERBATIM) ---

Here is the **Smith County / Tyler, Texas foreclosure lead source map** with the actual working portals and direct pages.

Key distinction:

**Tax foreclosure auctions** are officially online through Smith County’s auction portal.

**Mortgage / deed of trust foreclosures** are not primarily run by the Clerk as an online auction. The Clerk posts the foreclosure notices. Sales are held at the Smith County Courthouse unless a third party like Auction.com or Xome is handling remote bidding on a specific trustee sale. Smith County says foreclosure notices must be filed with the County Clerk 21 days before the sale, and sales are held the first Tuesday of the month between 10 AM and 4 PM at the courthouse sale area. ([smith-county.com][1])

---

# 1. Official online auction portals

## 1. Smith County official tax foreclosure auction portal

[https://smith.texas.sheriffsaleauctions.com](https://smith.texas.sheriffsaleauctions.com)

Use this for **official online tax foreclosure auctions** in Smith County. Smith County directly says bidders must register here before auction day. This is the closest thing to the official online auction portal for Smith County foreclosure property. ([smith-county.com][2])

Small note: this portal blocked my browser fetch, but Smith County links it directly from both the Sheriff Sale page and the Delinquent Tax Sales page.

---

## 2. Smith County Sheriff Sale Auctions page

[https://www.smith-county.com/354/Sheriff-Sale-Auctions](https://www.smith-county.com/354/Sheriff-Sale-Auctions)

This is the county’s official instruction page for sheriff sale auctions. It points bidders to the official online tax foreclosure auction portal and explains bidder registration requirements. ([smith-county.com][2])

---

## 3. Smith County Delinquent Tax Sales page

[https://www.smith-county.com/358/Delinquent-Tax-Sales](https://www.smith-county.com/358/Delinquent-Tax-Sales)

This is the official county tax sale process page. It explains that Smith County does **not** sell tax lien certificates, that investors purchase properties at tax sales, and that official tax foreclosure sales are handled through the Smith County online auction portal. ([smith-county.com][3])

---

# 2. Official foreclosure notice and clerk portals

## 4. Smith County Clerk Foreclosures page

[https://www.smith-county.com/298/Foreclosures](https://www.smith-county.com/298/Foreclosures)

This is the official county page for trustee foreclosure notices. It explains that notices are filed with the County Clerk, posted at least 21 days before sale, and sold at public auction on the west steps of the courthouse. The page also tells you to review foreclosure postings through the county clerk’s public search system. ([smith-county.com][1])

---

## 5. Smith County Official Public Records Search

[https://smith.tx.publicsearch.us/](https://smith.tx.publicsearch.us/)

This is the county’s official public records search. Use this for clerk records, deeds, deed of trust records, substitute trustee filings, foreclosure notices, liens, judgments, and title documents. The portal supports grantor, grantee, subdivision, document type, document number, date range, index search, and OCR full text search. ([smith.tx.publicsearch.us][4])

Search terms to use:

`NOTICE OF SUBSTITUTE TRUSTEE SALE`
`NOTICE OF TRUSTEE SALE`
`FORECLOSURE SALE`
`SUBSTITUTE TRUSTEE`
`APPOINTMENT OF SUBSTITUTE TRUSTEE`
`DEED OF TRUST`
`TRUSTEE DEED`
`LIS PENDENS`

---

## 6. Smith County Official Records Advanced Search

[https://smith.tx.publicsearch.us/search/advanced](https://smith.tx.publicsearch.us/search/advanced)

This is the better portal for serious lead pulling. It lets you search by department, including **Property Records** and **Foreclosures**, then filter by party name, recorded date, document type, document number, book, volume, page, and legal description. ([smith.tx.publicsearch.us][5])

Best use:

Select **Foreclosures**
Choose the sale month or last 30 to 60 days
Search by trustee, borrower, lender, or document type
Download the notice and extract property address, legal description, debt info, and sale date

---

## 7. Smith County Property Alerts

[https://smith.tx.publicsearch.us/property-alert](https://smith.tx.publicsearch.us/property-alert)

This is useful for monitoring owner names, entity names, buyer names, or target keywords. The system sends alerts when a matching name or keyword appears in a real property filing. ([smith.tx.publicsearch.us][6])

Use this for:

Investor watchlist
Owner distress monitoring
Entity monitoring
Lien release alerts
Foreclosure notice alerts
Substitute trustee alerts

---

## 8. Smith County Official Public Records page

[https://www.smith-county.com/293/Official-Public-Records](https://www.smith-county.com/293/Official-Public-Records)

This is the county page that confirms the official public records search portal and links to foreclosure record access. Use this when validating that `smith.tx.publicsearch.us` is the official county clerk search portal. ([smith-county.com][7])

---

# 3. Court case and lawsuit portals

## 9. Smith County Judicial Records Smart Search

[https://portal.smith-county.com/Public/Home/Dashboard/29](https://portal.smith-county.com/Public/Home/Dashboard/29)

Use this to search court cases, judgments, parties, and related lawsuit records. This matters because tax foreclosure lawsuits, debt cases, title disputes, probate conflicts, and judgment records can all lead to foreclosure or distressed title opportunities. ([portal.smith-county.com][8])

Search by:

Borrower name
Owner name
Lender name
Case number
Judgment
Tax suit
Bankruptcy related party
Estate name

---

## 10. Smith County Hearing Search

[https://portal.smith-county.com/Public/Home/Dashboard/26](https://portal.smith-county.com/Public/Home/Dashboard/26)

Use this to search hearing dates by case number, party, attorney, judicial officer, courtroom, date range, and case type. Good for tracking tax suits, civil cases, probate disputes, and cases moving toward judgment. ([portal.smith-county.com][9])

---

## 11. Smith County District Clerk page

[https://www.smith-county.com/269/District-Clerk](https://www.smith-county.com/269/District-Clerk)

This page confirms the District Clerk is the record office for district court proceedings and certain civil cases, including real estate lawsuits and tax collection cases. It also links to the county judicial search system. ([smith-county.com][10])

---

## 12. Smith County Probate page

[https://www.smith-county.com/290/Probate](https://www.smith-county.com/290/Probate)

Use this for probate lead research. Probate becomes important when a foreclosure notice has a deceased owner, estate, heirs, or title chain issues. The page links to online case data and explains that probate indexes are available online. ([smith-county.com][11])

---

## 13. Smith County Excess Proceeds report

[https://www.smith-county.com/DocumentCenter/View/2032](https://www.smith-county.com/DocumentCenter/View/2032)

This is a direct PDF for **Registry and Trust Accounts With Balances, Excess Proceeds**. It can surface surplus funds, tax sale overages, and parties connected to prior foreclosure or tax sale activity. The report includes case numbers, party names, case descriptions, and balances. ([smith-county.com][12])

---

# 4. Tax, ownership, and parcel research portals

## 14. Smith County Tax Office Property Search

[https://publictax.smith-county.com/search](https://publictax.smith-county.com/search)

Use this to search property taxes by account number, owner name, mailing address, owner ID, property address, appraisal district number, statement number, or legal description. It also allows paid and unpaid tax filtering. ([publictax.smith-county.com][13])

Use this for:

Unpaid taxes
Tax balances
Owner mailing address
Property address
Tax account matching
Pre foreclosure distress signals

---

## 15. Smith County Tax Office main tax portal

[https://publictax.smith-county.com/](https://publictax.smith-county.com/)

This is the county tax portal landing inside the actual tax system, not the county homepage. It gives access to property search, tax payment, and tax related lookup tools. ([publictax.smith-county.com][14])

---

## 16. Smith County Appraisal District Property Search

[https://smithcad-search.gsacorp.io/search](https://smithcad-search.gsacorp.io/search)

Use this to search parcels, owners, site addresses, property IDs, tax districts, property use, and appraisal records. This is one of the best places to verify owner, situs, value, legal description, and parcel status. ([smithcad.org][15])

---

## 17. Smith County Appraisal District Map Search

[https://smithcad-search.gsacorp.io/map/](https://smithcad-search.gsacorp.io/map/)

Use this for map based parcel research, parcel summaries, tax collector links, Google Maps links, and real estate tax links. ([smithcad-search.gsacorp.io][16])

---

## 18. Smith CAD mapping page

[https://www.smithcad.org/mapping.html](https://www.smithcad.org/mapping.html)

This page confirms that Smith CAD maintains property tax ownership records, address records, and cadastral maps. Use it as the official source behind the mapping system. ([smithcad.org][17])

---

# 5. Legal notice and publication portals

## 19. Texas Public Notices search

[https://www.texaspublicnotices.com/](https://www.texaspublicnotices.com/)

This is the statewide legal notice search portal. It lets you search public notices by keyword, county, newspaper, and date range. Texas Public Notices says notices required to be published in newspapers are also uploaded here and are free to access. ([Texas Public Notices][18])

Search terms:

`Smith County foreclosure`
`Tyler substitute trustee`
`notice of trustee sale`
`notice of substitute trustee sale`
`Smith County tax sale`
`Smith County sheriff sale`
`Tyler Morning Telegraph foreclosure`

---

## 20. Tyler Morning Telegraph legal notices

[https://classifieds.etxclassifieds.com/tyler/category/announcements-legals/legal-notices](https://classifieds.etxclassifieds.com/tyler/category/announcements-legals/legal-notices)

This is the local newspaper legal notice page. I would use this as a backup to Texas Public Notices because the page can block some browser sessions, but it is still the direct local classified/legal notices source for Tyler area notices. Search results show Smith County notice of sale content appearing there. ([classifieds.etxclassifieds.com][19])

---

## 21. Smith County Legal News foreclosure page

[https://www.smithcountylegalnews.com/foreclosures.html](https://www.smithcountylegalnews.com/foreclosures.html)

This is a third party local legal news source, but it is very relevant. It says it publishes Smith County foreclosure lists weekly, including trustee name, property address, legal description, deed of trust file number, filing date, current owner, and original principal amount. It also references tax sale notices and other county records. ([Smith County Legal News Service][20])

Use this as a paid/local shortcut, then verify everything inside the official clerk portal.

---

# 6. Tax sale law firm and resale portals

## 22. Perdue Brandon Tax Sales Map

[https://epsilon.pbfcm.com/TaxSalesMap/](https://epsilon.pbfcm.com/TaxSalesMap/)

This is a tax sale map/search tool from Perdue Brandon. It supports filters for state, sale type, sale status, county, case number, and sale date. Use this for Tyler ISD or Perdue handled tax foreclosure matters. ([epsilon.pbfcm.com][21])

---

## 23. Perdue Brandon tax sale page

[https://www.pbfcm.com/taxsale.html](https://www.pbfcm.com/taxsale.html)

This page hosts upcoming tax sale information by county PDF. It warns that lists can change frequently, which is normal for tax sale lists because properties can be redeemed or removed before sale. ([pbfcm.com][22])

---

## 24. Perdue Brandon tax resale page

[https://www.pbfcm.com/taxresale.html](https://www.pbfcm.com/taxresale.html)

Use this for **struck off** properties that did not sell at tax sale and may be available as tax resale inventory. ([pbfcm.com][23])

---

## 25. Smith County / Tyler ISD struck off tax resale PDF

[https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf](https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf)

This is a direct Smith County tax resale PDF. It lists struck off properties, case numbers, account numbers, property descriptions, minimum bid, adjudged value, and tax value. The document says buyers must do their own research and check Smith CAD and County Clerk records for liens and title issues. ([pbfcm.com][24])

---

## 26. Linebarger tax sale property search

[https://taxsales.lgbs.com/](https://taxsales.lgbs.com/)

This is Linebarger’s tax sale property search portal. Smith County’s official delinquent tax sale page says Linebarger represents Smith County and most taxing units except Tyler ISD. Use this to monitor tax sale properties handled by Linebarger, then cross check with Smith County, CAD, and clerk records. ([smith-county.com][3])

---

## 27. MVBA tax sales calendar

[https://mvbalaw.com/tax-sales/month-sales/](https://mvbalaw.com/tax-sales/month-sales/)

This is another tax sale calendar source. I found Smith County related auction references connected to the sheriff sale auction system, including Gladewater ISD Smith County property references. Use this as a secondary tax sale radar. ([mvba Law][25])

---

# 7. Third party foreclosure auction and REO portals

## 28. Auction.com Smith County foreclosure search

[https://www.auction.com/residential/texas/smith-county](https://www.auction.com/residential/texas/smith-county)

Use this for third party foreclosure, bank owned, and trustee sale inventory in Smith County. Auction.com search results show Smith County foreclosure listings with courthouse sale location and some in person plus remote bidding language. Always verify the notice inside Smith County Clerk records. ([Auction.com][26])

---

## 29. Xome Tyler foreclosure trustee auction search

[https://www.xome.com/auctions/foreclosure-trustee/TX/Tyler](https://www.xome.com/auctions/foreclosure-trustee/TX/Tyler)

Use this to monitor Xome trustee foreclosure inventory in Tyler. At the time of search, the Tyler foreclosure trustee page showed zero active foreclosure auction properties, but it is still the correct city level watchlist page. Xome also has Smith County property level auction pages that reference courthouse foreclosure sale process. ([Xome][27])

---

## 30. Hubzu Smith County foreclosure example

[https://www.hubzu.com/foreclosure-home/93517697730-1430-S-GLENWOOD-BLVD-Tyler-TX-75701](https://www.hubzu.com/foreclosure-home/93517697730-1430-S-GLENWOOD-BLVD-Tyler-TX-75701)

This is a Hubzu property level foreclosure lead in Tyler. Important note: the Hubzu result itself says the foreclosure sale is **not conducted by Hubzu or Altisource**, and points to the Smith County Courthouse sale process. Treat Hubzu as a lead source, not the official auction authority. ([Hubzu][28])

---

## 31. TexasFile Smith County Clerk records search

[https://www.texasfile.com/search/texas/smith/](https://www.texasfile.com/search/texas/smith/)

This is a third party clerk record search portal. Use it as a backup when the official clerk portal is slow or when you want another index for deed, lien, and recorded document research. It is not the official source of truth, but it can be useful for fast title searches. ([Texas File][29])

---

# 8. City of Tyler code, permit, and violation portals

These are not foreclosure auction portals, but they are strong distress lead sources for Tyler properties.

## 32. City of Tyler eTRAKiT main search portal

[https://trakit.cityoftyler.net/eTRAKiT/](https://trakit.cityoftyler.net/eTRAKiT/)

This portal has searches for permits, projects, properties, code cases, violations, and public issues. Use it for code distress, vacant property signals, substandard structure issues, permit activity, and nuisance patterns. ([Trakit][30])

---

## 33. City of Tyler permit search

[https://trakit.cityoftyler.net/eTRAKiT/Search/permit.aspx](https://trakit.cityoftyler.net/eTRAKiT/Search/permit.aspx)

Use this to search permit activity by address, permit number, or property. Good for signs of repairs, failed projects, flips, and owner distress. ([Trakit][31])

---

## 34. City of Tyler violation / case search

[https://trakit.cityoftyler.net/eTRAKiT/Search/case.aspx](https://trakit.cityoftyler.net/eTRAKiT/Search/case.aspx)

Use this for code enforcement cases and property violations. It allows searching by case number, site address, case info, contacts, fees, inspections, chronology, and violations. ([Trakit][32])

---

## 35. City of Tyler CRM issue search

[https://trakit.cityoftyler.net/eTRAKiT/CRM/search.aspx](https://trakit.cityoftyler.net/eTRAKiT/CRM/search.aspx)

Use this for public complaints and reported issues. It can help find nuisance properties, illegal dumping, high grass, abandoned properties, and neighborhood complaints. ([Trakit][33])

---

## 36. City of Tyler Code Enforcement page

[https://www.cityoftyler.org/government/departments/code-enforcement](https://www.cityoftyler.org/government/departments/code-enforcement)

This confirms the types of cases Tyler code enforcement handles, including high weeds, illegal dumping, zoning issues, junked vehicles, substandard structures, outdoor storage, and other nuisance cases. ([City of Tyler][34])

---

# Best workflow for Smith County

For **tax foreclosure leads**:

1. Start with:
   [https://www.smith-county.com/358/Delinquent-Tax-Sales](https://www.smith-county.com/358/Delinquent-Tax-Sales)

2. Register and monitor:
   [https://smith.texas.sheriffsaleauctions.com](https://smith.texas.sheriffsaleauctions.com)

3. Cross check with:
   [https://taxsales.lgbs.com/](https://taxsales.lgbs.com/)
   [https://epsilon.pbfcm.com/TaxSalesMap/](https://epsilon.pbfcm.com/TaxSalesMap/)
   [https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf](https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf)

4. Verify owner, taxes, parcel, and title through:
   [https://publictax.smith-county.com/search](https://publictax.smith-county.com/search)
   [https://smithcad-search.gsacorp.io/search](https://smithcad-search.gsacorp.io/search)
   [https://smith.tx.publicsearch.us/search/advanced](https://smith.tx.publicsearch.us/search/advanced)

For **mortgage / trustee foreclosure leads**:

1. Start with Clerk Foreclosures:
   [https://www.smith-county.com/298/Foreclosures](https://www.smith-county.com/298/Foreclosures)

2. Search the actual foreclosure records here:
   [https://smith.tx.publicsearch.us/search/advanced](https://smith.tx.publicsearch.us/search/advanced)

3. Cross check legal notices here:
   [https://www.texaspublicnotices.com/](https://www.texaspublicnotices.com/)
   [https://classifieds.etxclassifieds.com/tyler/category/announcements-legals/legal-notices](https://classifieds.etxclassifieds.com/tyler/category/announcements-legals/legal-notices)
   [https://www.smithcountylegalnews.com/foreclosures.html](https://www.smithcountylegalnews.com/foreclosures.html)

4. Watch third party auction portals here:
   [https://www.auction.com/residential/texas/smith-county](https://www.auction.com/residential/texas/smith-county)
   [https://www.xome.com/auctions/foreclosure-trustee/TX/Tyler](https://www.xome.com/auctions/foreclosure-trustee/TX/Tyler)
   [https://www.hubzu.com/foreclosure-home/93517697730-1430-S-GLENWOOD-BLVD-Tyler-TX-75701](https://www.hubzu.com/foreclosure-home/93517697730-1430-S-GLENWOOD-BLVD-Tyler-TX-75701)

5. Verify lawsuits, judgments, probate, and hearings here:
   [https://portal.smith-county.com/Public/Home/Dashboard/29](https://portal.smith-county.com/Public/Home/Dashboard/29)
   [https://portal.smith-county.com/Public/Home/Dashboard/26](https://portal.smith-county.com/Public/Home/Dashboard/26)
   [https://www.smith-county.com/290/Probate](https://www.smith-county.com/290/Probate)

The official source of truth is still the **Smith County Clerk public records system** and the **Smith County tax sale portal**. The third party sites are radar. They can help you find deals faster, but every lead should be verified against the Clerk, Tax Office, CAD, and court search before you touch it.

[1]: https://www.smith-county.com/459/Foreclosure-Sale-Notices "Foreclosures | Smith County, TX"
[2]: https://www.smith-county.com/354/Sheriff-Sale-Auctions "Sheriff Sale Auctions | Smith County, TX"
[3]: https://www.smith-county.com/458/Delinquent-Tax-Sale-Notices "Delinquent Tax Sales | Smith County, TX"
[4]: https://smith.tx.publicsearch.us/ "Official Record Search - Quick Search - Smith County, Texas County Clerk"
[5]: https://smith.tx.publicsearch.us/search/advanced "Official Record Search - Advanced Search - Smith County, Texas County Clerk"
[6]: https://smith.tx.publicsearch.us/property-alert "Property Alert"
[7]: https://www.smith-county.com/293/Official-Public-Records "Official Public Records | Smith County, TX"
[8]: https://portal.smith-county.com/Public/Home/Dashboard/29 "Smart Search - Tyler Odyssey Portal"
[9]: https://portal.smith-county.com/Public/Home/Dashboard/26 "Search Hearings - Tyler Odyssey Portal"
[10]: https://www.smith-county.com/269/District-Clerk "District Clerk | Smith County, TX"
[11]: https://www.smith-county.com/290/Probate "Probate | Smith County, TX"
[12]: https://www.smith-county.com/DocumentCenter/View/2032 "District Clerk September 2025 Registry & Trust Accounts with Balances"
[13]: https://publictax.smith-county.com/search "Smith County"
[14]: https://publictax.smith-county.com/ "Smith County"
[15]: https://www.smithcad.org/Search/PropertySearch.html "Records Search 
 \- Smith County Appraisal District"
[16]: https://smithcad-search.gsacorp.io/map/ "Smith County GIS"
[17]: https://www.smithcad.org/mapping.html "Smith CAD"
[18]: https://www.texaspublicnotices.com/ "
    Public Notices Texas State | Texas State Press Association
"
[19]: https://classifieds.etxclassifieds.com/tyler/category/announcements-legals/legal-notices?utm_source=chatgpt.com "Tyler Morning Telegraph Classifieds Marketplace - Announcements/Legals - Legal Notices"
[20]: https://www.smithcountylegalnews.com/foreclosures.html "Foreclosure Sales in Smith County TX for Real Estate"
[21]: https://epsilon.pbfcm.com/TaxSalesMap/ "
    Perdue Brandon - Tax Forclosure Sale/Resale Map
"
[22]: https://www.pbfcm.com/taxsale.html "PBFCM - Tax Sales"
[23]: https://www.pbfcm.com/taxresale.html "PBFCM - Tax Resales"
[24]: https://www.pbfcm.com/docs/taxdocs/resales/smithcountytaxresale.pdf "January 18, 1999"
[25]: https://mvbalaw.com/tax-sales/month-sales/?utm_source=chatgpt.com "Texas Tax Sales | Monthly Updates | MVBA"
[26]: https://www.auction.com/residential/texas/smith-county?utm_source=chatgpt.com "Foreclosure and Bank Owned Auctions in Smith County, TX"
[27]: https://www.xome.com/auctions/foreclosure-trustee/TX/Tyler?utm_source=chatgpt.com "Tyler, TX Foreclosure Homes For Sale - Xome Auctions"
[28]: https://www.hubzu.com/foreclosure-home/93517697730-1430-S-GLENWOOD-BLVD-Tyler-TX-75701?utm_source=chatgpt.com "Foreclosure Home | 1430 S GLENWOOD BLVD , Tyler, TX 75701 | Property Details | Hubzu"
[29]: https://www.texasfile.com/search/texas/smith/?utm_source=chatgpt.com "Smith County Clerk Records Search | TexasFile"
[30]: https://trakit.cityoftyler.net/eTRAKiT/ "eTRAKiT"
[31]: https://trakit.cityoftyler.net/eTRAKiT/Search/permit.aspx "eTRAKiT"
[32]: https://trakit.cityoftyler.net/eTRAKiT/Search/case.aspx "eTRAKiT"
[33]: https://trakit.cityoftyler.net/eTRAKiT/CRM/search.aspx "eTRAKiT"
[34]: https://www.cityoftyler.org/government/departments/code-enforcement "Code Enforcement | Tyler, TX"

--- END OPERATOR DOSSIER ---
