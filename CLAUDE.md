# Conventions for AI sessions in this repo

## Scope

A rendering of published ICH M11 sources as linked data (D1: elements and
sections) plus mapping statements from M11 elements to usdm-rdf IRIs (D2)
and the ICH M11 Template's headings and fields linked to the elements (D5).
Readings, findings and judgements go to usdm-overlay, not here. usdm-rdf is
not changed. Describe usdm-rdf as an RDF/OWL representation of USDM, not as
an "ontology". Resist scope creep: flag "let's also do X" before
implementing.

## Identity (fixed; ask before reopening)

- Namespace `https://w3id.org/m11-rdf/`, no version segment.
- Element local name = namespace codelist + "." + concept C-code, the pair
  as stated in the ICH M11 Technical Specification.
- Sections by their C217272 term. Nothing else is minted for headings.
- Template fields are blank nodes on their section; no IRIs.
- Lifecycle is not inferred from a diff: label, definition, conformance or
  cardinality changes keep the IRI; a membership change is a new element.

## Sources

- Precedence: Technical Specification for element existence, place,
  conformance, cardinality; EVS for terms and definitions; OID Listing for
  OIDs. Where they disagree, keep each statement and report it; do not
  repair.
- EVS content is CC BY 4.0, attributed to NCI EVS; do not call it
  "NCI Thesaurus". ICH content keeps the ICH copyright acknowledgement and
  is marked as a derived rendering, not endorsed by ICH.
- Public sources only. Nothing from internal or sponsor work.

## Data integrity

- Never fabricate, simulate or generate example data.
- Inputs come only from `downloads/`, pinned by URL and SHA-256 in
  `scripts/fetch_inputs.py`; a mismatch stops the build.
- Every count in the docs comes from a build output or a test, not by hand.
- Quote sources verbatim. Never paraphrase a definition into a quote.

## Code style

- Python 3, `rdflib`. 4-space indentation, no exceptions.
- Complete, copy-paste-ready code. No placeholders.
- Fail-fast. No defensive try/except, no silent auto-fixes.

## Code modification

- Fix only what was asked. Show a unified diff before editing and wait for
  approval.
- Never remove code that looks redundant.

## Git

Git operations are the owner's to run. Describe the commit; do not execute
it unless asked. Pushing is always the owner's.
