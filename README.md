# m11-rdf

ICH M11 protocol elements and sections as linked data, with mapping
statements to [usdm-rdf](https://github.com/kerfors/usdm-rdf), the RDF/OWL
representation of CDISC USDM v4.

**Draft, not normative.** Not an ICH, CDISC or HL7 artifact, and not
endorsed or sponsored by them. Early work: D1 (elements, sections, code
lists) is built; D2 (mappings) is next.

Site: <https://w3id.org/m11-rdf/> (redirects to
<https://kerfors.github.io/m11-rdf/>), one page per IRI.

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
| D2 | Mapping statements M11 element → usdm-rdf class or attribute, from the HL7 Clinical Study Protocol IG ballot and CDISC DDF-RA v4.0.0, neither primary, as an SSSOM mapping set | Not started |
| D4 | How content (a USDM instance, a document section, a template field) points at the element it realises: [skeleton](notes/d4-skeleton.md) for discussion | Skeleton |

Conformance and cardinality belong to a Technical Specification block, not
to the element: the same element can be specified in several blocks (for
example Endpoint in 3.1.X, 3.2.X and 3.3.X) with different conformance. Each
block is one `m11:Specification` on the element.

The NCIt concept is linked with `m11:concept` (EVS identifier and OBO PURL),
not `skos:exactMatch`: one concept can be the concept of several elements.
Code lists get the IRI of their own C-code (`…/C217344`), carrying the ICH
OID.

Where the sources disagree, the rendering keeps each source's statement
and does not repair it. Findings about the disagreements, and about how
M11 lands in USDM, go to
[usdm-overlay](https://github.com/kerfors/usdm-overlay), not into this
repository. usdm-rdf is not changed.

## Sources and attribution

Inputs are pinned by URL and SHA-256 in `downloads/MANIFEST.md`.

- **ICH M11 Terminology**, NCI Enterprise Vocabulary Services (EVS),
  release 2025-12-19: terms and definitions. Licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); see the
  [EVS terms of use](https://evs.nci.nih.gov/ftp1/NCI_Thesaurus/ThesaurusTermsofUse.htm).
- **ICH M11 Technical Specification** (Step 4, 19 November 2025) and the
  **ICH M11 code lists and OID Listing** (Step 4 M11 Package 1.0, November
  2025; OID Listing dated 16 October 2025): element place, conformance,
  cardinality, data type and OIDs. Copyright © ICH, used under the
  [ICH Legal Mentions](https://www.ich.org/page/legal-mentions). This
  repository adapts that content: it renders it as RDF, joins it with the
  EVS terminology and records where the sources disagree. The adaptation is
  not endorsed or sponsored by ICH.
- **CDISC DDF-RA** v4.0.0, `Documents/Mappings/m11_mapping.xlsx` (D2).
  Content based on [DDF-RA (GitHub)](https://github.com/cdisc-org/DDF-RA)
  used under the [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
  license.
- **HL7 FHIR Clinical Study Protocol IG**, STU 1 ballot (May 2026),
  `M11 to FHIR Mapping 02.xlsx` (D2). Terms to be confirmed before D2 is
  published.
- **usdm-rdf** v0.7.1, `usdm_v4.ttl`: the targets of the mapping
  statements (D2).

## Files

| Path | What |
| --- | --- |
| `m11-rdf.ttl` | The graph (canonical Turtle). Generated by `scripts/build_d1.py`. |
| `vocabulary.ttl` | Classes and properties. Hand-maintained; merged into `m11-rdf.ttl`. |
| `reports/reconciliation.md`, `.csv` | How the Technical Specification blocks, EVS terms, sections, code lists and OIDs line up, and where they disagree. Every count in the docs comes from here or from the tests. Generated. |
| `reports/tests.md` | Tests passed in the last build. Generated by `scripts/test_d1.py`. |
| `notes/d4-skeleton.md` | D4 skeleton, for discussion. |
| `downloads/MANIFEST.md` | Pinned inputs: file, source, terms, URL, SHA-256. Written by `scripts/fetch_inputs.py`. |
| `scripts/` | `fetch_inputs.py`, `parse_ts.py` (Technical Specification Appendix 1), `build_d1.py`, `test_d1.py`, `build_site.py`, `common.py`. |
| `docs/` | GitHub Pages site for the namespace: one page per IRI, the graph in four serializations. Generated; do not edit by hand. |
| `w3id/` | Copy of the w3id.org entry (`ids/m11-rdf/`): `.htaccess` and `README.md`. |

## Rebuild

```
python3 scripts/fetch_inputs.py
python3 scripts/build_d1.py
python3 scripts/test_d1.py
python3 scripts/build_site.py
```

Requires Python 3, `rdflib` and `markdown`, and `pdftotext` (poppler). The
text extracted from the Technical Specification is pinned by SHA-256; the
build stops if a different poppler version produces different text.

## Licence

Code under the MIT licence; generated content under CC BY 4.0, with the
attributions above. See `LICENSE`.
