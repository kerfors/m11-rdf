# m11-rdf

ICH M11 protocol elements and sections as linked data, with mapping
statements to [usdm-rdf](https://github.com/kerfors/usdm-rdf), the RDF/OWL
representation of CDISC USDM v4.

**Draft, not normative.** Not an ICH, CDISC or HL7 artifact, and not
endorsed or sponsored by them. Early work: the repository has its inputs
and fetch script; the graph is not built yet.

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
| D1 | Elements and sections: label, ICH definition, section, conformance, cardinality, data type, value code list, ICH OIDs on namespaces and code lists; a reconciliation table of the sources as build output | Not started |
| D2 | Mapping statements M11 element → usdm-rdf class or attribute, from the HL7 Clinical Study Protocol IG ballot and CDISC DDF-RA v4.0.0, neither primary, as an SSSOM mapping set | Not started |

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
| `downloads/MANIFEST.md` | Pinned inputs: file, source, terms, URL, SHA-256. Written by `scripts/fetch_inputs.py`. |
| `scripts/fetch_inputs.py` | Fetches the inputs into `downloads/`; stops on any checksum mismatch. |
| `docs/` | GitHub Pages site for the namespace. Generated; do not edit by hand. |
| `w3id/` | Copy of the w3id.org entry (`ids/m11-rdf/`): `.htaccess` and `README.md`. |

## Rebuild

```
python3 scripts/fetch_inputs.py
```

Requires Python 3 (standard library only, for now).

## Licence

Code under the MIT licence; generated content under CC BY 4.0, with the
attributions above. See `LICENSE`.
