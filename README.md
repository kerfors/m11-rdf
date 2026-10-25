# m11-rdf

ICH M11 protocol elements and sections as linked data, with mapping
statements to [usdm-rdf](https://github.com/kerfors/usdm-rdf), the RDF/OWL
representation of CDISC USDM v4.

**Draft, not normative.** Not an ICH, CDISC or HL7 artifact, and not
endorsed or sponsored by them. Early work: D1 (elements, sections, code
lists), D2 (mapping statements to USDM v4) and D5 (the ICH M11 Template,
linked to the elements) are built.

Site: <https://w3id.org/m11-rdf/> (redirects to
<https://kerfors.github.io/m11-rdf/>), one page per IRI.

Slides: [ICH M11 elements: a target to map to](https://w3id.org/m11-rdf/slides/)
(PDF, eight slides): what m11-rdf gives when mapping protocol content to
ICH M11 and USDM v4, what is left, and questions for USDM 4.1.

## Why

USDM v4 has identifiers for its classes and attributes (usdm-rdf), and the
publisher of a study mints identifiers for its instances. The level in
between, the protocol element ("Sponsor Approval Date" on the Title Page,
section 3.1 "Primary Objective(s) and Associated Estimand(s)"), has no
resolvable identifier. With one, a USDM instance, a document section or a
template field can say which M11 element it realises, and two mappings of
the same element can be compared by a query.

## Identity

- Namespace `https://w3id.org/m11-rdf/`, redirecting to the GitHub Pages
  site of this repository. No version segment; each release has a version
  IRI (`https://w3id.org/m11-rdf/0.1.0`).
- Element IRI: namespace codelist + `.` + concept C-code, for example
  `https://w3id.org/m11-rdf/C217356.C132352`. The pair is the one the ICH
  M11 Technical Specification states for the element. A C-code alone
  identifies a concept, not an element: the same concept can be an element
  in two sections.
- Each element has `skos:exactMatch` to the NCI EVS term IRI where EVS has
  the term, and its NCIt concept in the form usdm-rdf uses (EVS identifier
  and OBO PURL).
- Section IRI: the section's term in code list C217272 (Protocol Section
  Name and Number), for example `https://w3id.org/m11-rdf/C217272.C218527`.
- A change of label, definition, conformance or cardinality keeps the IRI.
  A change of namespace membership is a new element; the old IRI is
  deprecated. If ICH or CDISC mint official IRIs for M11 elements, the IRIs
  here get `owl:sameAs` to them and are deprecated.

## Planned content

| Part | What | Status |
| --- | --- | --- |
| D1 | Elements, sections and code lists. Element: label and ICH definition (EVS), namespace, the ICH pair (namespace OID + concept code), NCIt concept, and one specification per Technical Specification block (section, conformance, cardinality, data type, value code list, as printed). Section: C217272 term, number, hierarchy. Code list: ICH OID. A reconciliation table of the sources as build output. | Built (v0.1.0) |
| D2 | Mapping statements M11 element → usdm-rdf attribute, from the HL7 Clinical Study Protocol IG ballot and CDISC DDF-RA v4.0.0, neither primary, as an SSSOM mapping set | Built (v0.2.0) |
| D4 | How content (a USDM instance, a document section, a template field) points at the element it realises: [skeleton](notes/d4-skeleton.md) for discussion | Skeleton |
| D5 | The ICH M11 Template: each heading on its section, each field (insertion point or controlled-terminology pick) on its section, linked to the element it realises, with the Template's optional and conditional flags | Built (v0.3.0; v0.3.1: repeating headings) |

Conformance and cardinality belong to a Technical Specification block, not
to the element: the same element can be specified in several blocks (for
example Endpoint in 3.1.X, 3.2.X and 3.3.X) with different conformance. Each
block is one `m11:Specification` on the element.

The NCIt concept is linked with `m11:concept` (EVS identifier and OBO PURL),
not `skos:exactMatch`: one concept can be the concept of several elements.
Code lists get the IRI of their own C-code (`…/C217344`), carrying the ICH
OID.

## Mapping statements (D2)

`m11-usdm.sssom.tsv` (SSSOM/TSV) and `m11-usdm.sssom.ttl` (SSSOM/RDF) hold
one record per row of the two published M11 → USDM mappings whose M11 side
is identified and whose USDM target resolves. The link from element to USDM
attribute is the mapping publisher's; this repository adds only the
identification of the M11 side, recorded per record:

- `by-code`: the row's NCIt Code is the concept of one element. Where the
  code is the concept of elements in several namespaces, the row's section
  decides.
- `by-unique-name`: otherwise, the row's element name, normalised (case,
  punctuation, brackets, white space), equals the term of exactly one
  Technical Specification element block.

The USDM side is the row's Class and Attribute looked up in usdm-rdf: the
property of the class or of a superclass, by attribute name or by
`usdm:modelName` (the relationship role name, e.g. `previous` for
`previousId`). Target and
condition paths are kept as given. Nothing is repaired: rows that cannot be
identified, ambiguous rows and targets that do not resolve get no record and
are listed in `reports/d2-residue.csv`, input for usdm-overlay. Counts are in
`reports/d2-identification.md`.

Each record has an IRI, `https://w3id.org/m11-rdf/mapping/<source>/<row>`
(`hl7` or `cdisc`, spreadsheet row), and is an `owl:Axiom` in the whole
graph. The graph also has one `m11:mappedTo` triple per distinct element →
attribute pair. `m11:mappedTo` is an annotation property: an element points
at an OWL property without punning. The mapping justification is
`semapv:ManualMappingCuration` (the publisher's). Both mappings target USDM
v4.0.0.

Where the sources disagree, the rendering keeps each source's statement
and does not repair it. Findings about the disagreements, and about how
M11 lands in USDM, go to
[usdm-overlay](https://github.com/kerfors/usdm-overlay), not into this
repository. usdm-rdf is not changed.

## ICH M11 Template (D5)

The Template is the document an author fills in; the Technical
Specification describes its elements. D5 records, from the published
Template PDF (Step 4, 19 November 2025):

- each numbered heading on the C217272 section with that number
  (`m11:templateHeading`, page, optional, conditional), and Amendment
  Details on its section. Where the heading, without its repeat number
  `<#>`, is the Technical Specification term of an element,
  `m11:headingElement` names it (narrative elements: the text under the
  heading; "Primary Objective <#>": the element each numbered repeat is
  for, 3.1.X in the Technical Specification). The repeating heading 12.X
  has no section term and is not rendered; its fields are on section 12.
- each field, a text insertion point `<...>` or a controlled-terminology
  pick `[...]`, as a blank node on its section (`m11:TemplateField`): label
  as printed, kind, page, order, the section number as printed, and the
  Template's flags: optional (printed in blue) and conditional (in
  `{braces}`), its conventions in section 0.3. Fields have no IRIs: section
  and element do not identify a field, and an order number would change
  with the next Template version.
- `m11:realises` from a field to the element it is the field for, with how
  it was found: name source (`ts-term`, `evs-label`, `ts-heading-context`),
  match (`exact`, `verb-dropped`: one leading verb such as Enter or Select
  removed) and scope (`section`: the element's ToC reference;
  `namespace`: the element's namespace is for the field's top-level
  section). A name that only occurs in another section is not linked.

The PDF is tagged: headings come from its H1–H4 tags, text units from its
block tags, and the Template's conventions from the text colour (red =
instructional, not carried; blue = optional; black = universal, not
carried). The extraction (`build/template.json`) is pinned by SHA-256.
Fields without an element, links found via the namespace, field kinds that
differ from the Technical Specification's D/V/H, and elements without a
field are listed by category in `reports/d5-residue.csv`, input for
usdm-overlay. Counts are in `reports/d5-template.md`.

## Sources and attribution

Inputs are pinned by URL and SHA-256 in `downloads/MANIFEST.md`.

- **ICH M11 Terminology**, NCI Enterprise Vocabulary Services (EVS),
  release 2025-12-19: terms and definitions. Licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); see the
  [EVS terms of use](https://evs.nci.nih.gov/ftp1/NCI_Thesaurus/ThesaurusTermsofUse.htm).
- **ICH M11 Technical Specification** (Step 4, 19 November 2025) and the
  **ICH M11 code lists and OID Listing** (Step 4 M11 Package 1.0, November
  2025; OID Listing dated 16 October 2025): element place, conformance,
  cardinality, data type and OIDs. **ICH M11 Template** (Step 4,
  19 November 2025): headings and fields (D5); instructional and universal
  text is not carried. Copyright © ICH, used under the
  [ICH Legal Mentions](https://www.ich.org/page/legal-mentions). This
  repository adapts that content: it renders it as RDF, joins it with the
  EVS terminology, links the Template's headings and fields to the
  elements and records where the sources disagree. The adaptation is
  not endorsed or sponsored by ICH.
- **CDISC DDF-RA** v4.0.0, `Documents/Mappings/m11_mapping.xlsx` (D2).
  Content based on
  [DDF-RA (GitHub)](https://github.com/cdisc-org/DDF-RA) used under the
  [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) license.
- **HL7 FHIR Clinical Study Protocol IG**, STU 1 ballot (May 2026),
  `M11 to FHIR Mapping 02.xlsx` (D2). The IG is published under CC0
  (package licence `CC0-1.0`); its Licenses sheet states that the ICH
  content is used under the ICH licence and the CDISC content under
  CC BY 4.0.
- **usdm-rdf** v0.7.0, `usdm_v4.ttl`: the targets of the mapping
  statements (D2). Pinned at the release its `owl:versionIRI` names; the
  later tag v0.7.1 was docs-only and has the same file.
- **SSSOM** schema v1.1.0a5 (BSD 3-Clause): the D2 tests check the mapping
  set against it.

## Files

| Path | What |
| --- | --- |
| `m11-rdf.ttl` | The graph (canonical Turtle). Generated by `scripts/build_d1.py`, extended by `build_d2.py` and `build_d5.py`. |
| `vocabulary.ttl` | Classes and properties. Hand-maintained; merged into `m11-rdf.ttl`. |
| `m11-usdm.sssom.tsv`, `.ttl` | D2 mapping set, SSSOM/TSV and SSSOM/RDF. Generated by `scripts/build_d2.py`, which also adds the records to `m11-rdf.ttl`. |
| `reports/d2-identification.md`, `.csv` | D2: how each mapping row was identified and resolved, counts, and the two mappings compared. Generated. |
| `reports/d2-residue.csv` | D2: rows without a record and flagged records, by category. Input for usdm-overlay. Generated. |
| `reports/reconciliation.md`, `.csv` | How the Technical Specification blocks, EVS terms, sections, code lists and OIDs line up, and where they disagree. Every count in the docs comes from here or from the tests. Generated. |
| `reports/d5-template.md`, `reports/d5-fields.csv` | D5: counts (headings, fields, links by basis, field kind against D/V/H, Template optionality against TS conformance) and every field with its element. Generated. |
| `reports/d5-residue.csv` | D5: fields without an element, links via the namespace, kind differences and elements without a field, by category. Input for usdm-overlay. Generated. |
| `reports/tests.md`, `reports/tests-d2.md`, `reports/tests-d5.md` | Tests passed in the last build. Generated by `scripts/test_d1.py`, `scripts/test_d2.py` and `scripts/test_d5.py`. |
| `notes/d4-skeleton.md` | D4 skeleton, for discussion. |
| `site/slides/m11-elements-slides.html` | Slides source. Hand-maintained; rendered by `scripts/render_slides.py` to `site/ich-m11-elements-mapping-target.pdf`, which `build_site.py` copies to `docs/slides/`. |
| `downloads/MANIFEST.md` | Pinned inputs: file, source, terms, URL, SHA-256. Written by `scripts/fetch_inputs.py`. |
| `scripts/` | `fetch_inputs.py`, `parse_ts.py` (Technical Specification Appendix 1), `parse_template.py` (Template headings and fields), `build_d1.py`, `build_d2.py`, `build_d5.py`, `test_d1.py`, `test_d2.py`, `test_d5.py`, `build_site.py`, `render_slides.py` (slides to PDF; not part of the rebuild), `common.py`. |
| `docs/` | GitHub Pages site for the namespace: one page per IRI, the graph in four serializations. Generated; do not edit by hand. |
| `w3id/` | Copy of the w3id.org entry (`ids/m11-rdf/`): `.htaccess` and `README.md`. |

## Rebuild

```
python3 scripts/fetch_inputs.py
python3 scripts/parse_ts.py
python3 scripts/build_d1.py
python3 scripts/build_d2.py
python3 scripts/parse_template.py
python3 scripts/build_d5.py
python3 scripts/test_d1.py
python3 scripts/test_d2.py
python3 scripts/test_d5.py
python3 scripts/build_site.py
```

`build_d2.py` adds the mapping records to `m11-rdf.ttl` and stops if they
are already there: run `build_d1.py` first. `build_d5.py` likewise adds the
Template data and stops if it is already there: run `build_d1.py` and
`build_d2.py` first.

Requires Python 3, `rdflib`, `markdown`, `openpyxl`, `pyyaml` and
`pymupdf`, and `pdftotext` (poppler). The text extracted from the
Technical Specification and the extraction of the Template are pinned by
SHA-256; the build stops if a different poppler, PyMuPDF or MuPDF version
produces different output (the Template extraction was pinned with
PyMuPDF 2.0, MuPDF 1.28.5).

After editing the slides: `python3 scripts/render_slides.py`, then
`build_site.py`. Needs Playwright with Chromium and network access to
Google Fonts; set `PLAYWRIGHT_CHROMIUM` to use another browser executable.

## Licence

Code under the MIT licence; generated content under CC BY 4.0, with the
attributions above. See `LICENSE`.
