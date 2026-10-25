"""Build D1: ICH M11 elements, sections and code lists as RDF, plus the reconciliation table.

Inputs (pinned, checked): Technical Specification Appendix 1 (via parse_ts),
EVS ICH M11 Terminology txt, Genericode code lists and OID Listing.
Outputs: m11-rdf.ttl (vocabulary.ttl merged with the generated graph),
reports/reconciliation.md and reports/reconciliation.csv.

Precedence (DECISIONS M10): the Technical Specification states element
existence, place, conformance, cardinality; EVS states terms and definitions;
the OID Listing states OIDs. Disagreements are recorded, not repaired.
"""
import csv
import re
from collections import Counter, defaultdict

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from common import (EVS, M11, NCIT, OBO, OID_ROOT, REPORTS, ROOT, SECTION_CODELIST,
                    evs_rows, genericode_lists, oid_listing, ts_text)
from parse_ts import parse_blocks

VERSION = "0.4.0"
OID_DT = M11.ichOid
CONCEPT_RE = re.compile(r"(C\d+)\s*(?:ICH OID\s*([\d.]+))?")
CODELIST_RE = re.compile(r"Code ?List[^:]*?(C\d+)[^:]*?:?\s*ICH OID\s*([\d.]+)")
REPEAT_RE = re.compile(r"^(\d+(?:\.\d+)*)[. ]X\b")  # TS has "12 X where ..." once
NAMED_SECTIONS = {"title page": "Title Page", "amendment details": "Amendment Details"}


def block_kind(block):
    concept = block.get("business_rules", "").split("Concept:")[-1].strip()
    if CONCEPT_RE.search(concept) and re.search(r"C\d+", concept):
        return "element"
    if concept == "Heading":
        return "heading"
    return "other: " + concept


def element_pairs(block, namespace_by_oid):
    """(namespace code list, concept code, stated OID or None) for each concept in an element block."""
    concept = block["business_rules"].split("Concept:")[-1]
    return [(namespace_by_oid.get(oid), code, oid or None) for code, oid in CONCEPT_RE.findall(concept)]


def section_key(toc):
    """Map a ToC value to (C217272 key, repeat pattern or None). Keys are section numbers or names."""
    t = toc.strip()
    if t.lower() in NAMED_SECTIONS:
        return NAMED_SECTIONS[t.lower()], None
    m = REPEAT_RE.match(t)
    if m:
        return m.group(1), t
    if re.fullmatch(r"\d+(?:\.\d+)*", t):
        return t, None
    raise RuntimeError(f"Unplaceable ToC value: {toc!r}")


def conformance_category(text):
    first = re.match(r"(Required|Optional|Conditional)", text)
    if not first:
        raise RuntimeError(f"Unknown conformance: {text!r}")
    return M11[first.group(1)]


def ncit_pair(g, subject, code):
    g.add((subject, M11.concept, NCIT[code]))
    g.add((subject, M11.concept, OBO["NCIT_" + code]))


def main():
    blocks = parse_blocks(ts_text())
    rows = evs_rows()
    gc = genericode_lists()
    listing = oid_listing()

    # Code lists: the OID Listing is the authority for OIDs; Genericode must agree with it.
    if set(gc) != set(listing):
        raise RuntimeError(f"Genericode and OID Listing list different code lists: {set(gc) ^ set(listing)}")
    for code, info in gc.items():
        if info["oid"] != listing[code]:
            raise RuntimeError(f"Genericode OID for {code} differs from the OID Listing")
    namespace_by_oid = {oid: code for code, oid in listing.items() if oid.startswith(OID_ROOT + ".3.")}
    evs_lists = {r["Code"]: r for r in rows if r["Codelist Code"] == ""}
    if set(evs_lists) != set(listing):
        raise RuntimeError(f"EVS code lists differ from the OID Listing: {set(evs_lists) ^ set(listing)}")
    evs_terms = {(r["Codelist Code"], r["Code"]): r for r in rows if r["Codelist Code"]}

    # Sections: C217272 terms; key = section number stated in the term definition, or the section name.
    sections = {}
    other_standard = []
    for (cl, code), r in evs_terms.items():
        if cl != SECTION_CODELIST:
            continue
        m = re.match(r"Section (\d+(?:\.\d+)*) of the ICH (M\d+) Protocol standard", r["ICH Definition"])
        if m:
            key = m.group(1)
            if m.group(2) != "M11":
                other_standard.append((code, key, m.group(2)))
        else:
            m = re.match(r"(Title Page|Amendment Details) Section of the ICH M11 Protocol standard", r["ICH Definition"])
            if not m:
                raise RuntimeError(f"C217272 term {code} states no section: {r['ICH Definition']!r}")
            key = m.group(1)
        if key in sections:
            raise RuntimeError(f"Two C217272 terms for section {key}")
        sections[key] = code

    # Namespaces -> top-level section, from the code list name ("ICH M11 Section 3 Terminology").
    namespace_section = {}
    for oid, code in namespace_by_oid.items():
        name = evs_lists[code]["Codelist Name"]
        m = re.fullmatch(r"ICH M11 Section (\d+|Title Page|Amendment Details) Terminology", name)
        namespace_section[code] = sections[m.group(1)]

    # Elements from TS element blocks.
    kinds = Counter()
    specs = defaultdict(list)
    no_oid = []
    for b in blocks:
        kind = block_kind(b)
        kinds[kind] += 1
        if kind == "heading":
            key, _ = section_key(b["toc"])
            if key not in sections:
                raise RuntimeError(f"Heading block {b['block']} ToC {b['toc']!r} has no C217272 term")
        if kind != "element":
            continue
        key, pattern = section_key(b["toc"])
        if key not in sections:
            raise RuntimeError(f"Element block {b['block']} ToC {b['toc']!r} has no C217272 term")
        for ns, code, oid in element_pairs(b, namespace_by_oid):
            if oid is None:
                top = key.split(".")[0]
                ns = next(n for n, s in namespace_section.items() if s == sections[top])
                no_oid.append((b["block"], code, ns))
            elif ns is None:
                raise RuntimeError(f"Block {b['block']}: OID {oid} is not an M11 namespace")
            specs[(ns, code)].append((b, key, pattern))

    g = Graph()
    g.parse(ROOT / "vocabulary.ttl")
    for prefix, ns in [("m11", M11), ("evs", EVS), ("ncit", NCIT), ("obo", OBO), ("skos", SKOS),
                       ("dcterms", DCTERMS), ("owl", OWL)]:
        g.bind(prefix, ns)
    onto = URIRef(str(M11))
    g.add((onto, OWL.versionInfo, Literal("v" + VERSION)))
    g.add((onto, OWL.versionIRI, M11[VERSION]))

    # Code lists (39): namespaces (arc .3) and value code lists (arc .1).
    for code, oid in listing.items():
        s = M11[code]
        g.add((s, RDF.type, M11.Namespace if oid.startswith(OID_ROOT + ".3.") else M11.ValueCodeList))
        g.add((s, SKOS.prefLabel, Literal(evs_lists[code]["Codelist Name"], lang="en")))
        g.add((s, SKOS.notation, Literal(oid, datatype=OID_DT)))
        g.add((s, SKOS.exactMatch, EVS[code]))
        ncit_pair(g, s, code)
        if evs_lists[code]["ICH Definition"]:
            g.add((s, SKOS.definition, Literal(evs_lists[code]["ICH Definition"], lang="en")))
        if code in namespace_section:
            g.add((s, M11.forSection, M11[f"{SECTION_CODELIST}.{namespace_section[code]}"]))

    # Sections (C217272 terms) with hierarchy from the numbering.
    for key, code in sections.items():
        s = M11[f"{SECTION_CODELIST}.{code}"]
        r = evs_terms[(SECTION_CODELIST, code)]
        g.add((s, RDF.type, M11.Section))
        g.add((s, SKOS.inScheme, M11[SECTION_CODELIST]))
        g.add((s, SKOS.prefLabel, Literal(r["ICH Preferred Term"], lang="en")))
        g.add((s, SKOS.definition, Literal(r["ICH Definition"], lang="en")))
        g.add((s, SKOS.exactMatch, EVS[f"{SECTION_CODELIST}.{code}"]))
        ncit_pair(g, s, code)
        if re.fullmatch(r"\d+(?:\.\d+)*", key):
            g.add((s, M11.sectionNumber, Literal(key)))
            if "." in key:
                parent = key.rsplit(".", 1)[0]
                if parent not in sections:
                    raise RuntimeError(f"Section {key} has no parent section {parent}")
                g.add((s, SKOS.broader, M11[f"{SECTION_CODELIST}.{sections[parent]}"]))

    # Elements and their specifications (one per TS block; a block with alternative concepts is shared).
    spec_nodes = {}
    for (ns, code), occurrences in specs.items():
        e = M11[f"{ns}.{code}"]
        g.add((e, RDF.type, M11.Element))
        g.add((e, SKOS.inScheme, M11[ns]))
        g.add((e, M11.ichConceptCode, Literal(code)))
        g.add((e, M11.ichNamespaceOid, Literal(listing[ns], datatype=OID_DT)))
        stated = {oid for b, _, _ in occurrences for n, c, oid in element_pairs(b, namespace_by_oid) if c == code}
        g.add((e, M11.pairBasis, M11.DerivedFromSection if stated == {None} else M11.StatedInTS))
        ncit_pair(g, e, code)
        term = evs_terms.get((ns, code))
        if term:
            g.add((e, SKOS.prefLabel, Literal(term["ICH Preferred Term"], lang="en")))
            g.add((e, SKOS.definition, Literal(term["ICH Definition"], lang="en")))
            g.add((e, SKOS.exactMatch, EVS[f"{ns}.{code}"]))
            g.add((e, M11.labelSource, M11.EVSTerminology))
            for syn in [x.strip() for x in term["ICH Synonym(s)"].split(";") if x.strip()]:
                g.add((e, SKOS.altLabel, Literal(syn, lang="en")))
        else:
            label = re.sub(r"^[\[{<]+|[\]}>]+$", "", occurrences[0][0]["term"].strip())
            g.add((e, SKOS.prefLabel, Literal(label, lang="en")))
            g.add((e, M11.labelSource, M11.TechnicalSpecification))
        for b, key, pattern in occurrences:
            if b["block"] not in spec_nodes:
                n = BNode(f"spec{b['block']}")
                spec_nodes[b["block"]] = n
                g.add((n, RDF.type, M11.Specification))
                g.add((n, M11.tsBlock, Literal(b["block"], datatype=XSD.integer)))
                g.add((n, M11.tsTerm, Literal(b["term"])))
                g.add((n, M11.dataType, Literal(b["data_type"])))
                g.add((n, M11.dvh, Literal(b["dvh"])))
                g.add((n, M11.conformance, Literal(b["conformance"])))
                g.add((n, M11.hasConformanceCategory, conformance_category(b["conformance"])))
                g.add((n, M11.cardinality, Literal(b["cardinality"])))
                g.add((n, M11.tocReference, Literal(b["toc"])))
                g.add((n, M11.inSection, M11[f"{SECTION_CODELIST}.{sections[key]}"]))
                if pattern:
                    g.add((n, M11.repeatPattern, Literal(pattern)))
                g.add((n, M11.repeatReuse, Literal(b["repeat_reuse"])))
                for cl_code, cl_oid in CODELIST_RE.findall(b.get("value", "")):
                    g.add((n, M11.hasValueCodeList, M11[cl_code]))
                    g.add((n, M11.statedCodeListOid, Literal(cl_oid, datatype=OID_DT)))
            g.add((e, M11.hasSpecification, spec_nodes[b["block"]]))

    g.serialize(ROOT / "m11-rdf.ttl", format="turtle")
    gc_vs_evs = []
    for code, info in sorted(gc.items()):
        evs_codes = {c for (cl, c) in evs_terms if cl == code}
        for c in sorted(set(info["codes"]) - evs_codes):
            gc_vs_evs.append((code, c, "Genericode only"))
        for c in sorted(evs_codes - set(info["codes"])):
            gc_vs_evs.append((code, c, "EVS only"))
    write_reconciliation(blocks, kinds, specs, evs_terms, sections, listing, namespace_by_oid, no_oid, other_standard,
                         gc_vs_evs)
    print(len(g), "triples;", len(specs), "elements;", len(sections), "sections;", len(listing), "code lists")


def write_reconciliation(blocks, kinds, specs, evs_terms, sections, listing, namespace_by_oid, no_oid, other_standard,
                         gc_vs_evs):
    """Counts and per-item rows that every number in the docs must come from (DECISIONS M14)."""
    REPORTS.mkdir(exist_ok=True)
    section_members = {k for k in evs_terms if k[0] in namespace_by_oid.values()}
    ts_pairs = set(specs)
    heading_tocs = {section_key(b["toc"])[0] for b in blocks if block_kind(b) == "heading"}
    element_tocs = {section_key(b["toc"])[0] for b in blocks if block_kind(b) == "element"}
    stated_cl = Counter()
    for b in blocks:
        for cl_code, cl_oid in CODELIST_RE.findall(b.get("value", "")):
            stated_cl[(cl_code, cl_oid)] += 1
    rows = []
    for (ns, code) in sorted(ts_pairs | section_members):
        in_ts, in_evs = (ns, code) in ts_pairs, (ns, code) in section_members
        rows.append({
            "item": "element", "namespace": ns, "code": code,
            "ts_blocks": ";".join(str(b["block"]) for b, _, _ in specs.get((ns, code), [])),
            "in_ts": in_ts, "in_evs": in_evs,
            "minted": in_ts,
            "note": "" if in_ts and in_evs else ("TS only" if in_ts else "EVS only: reported, not minted"),
        })
    for (cl_code, cl_oid), n in sorted(stated_cl.items()):
        ok = listing.get(cl_code) == cl_oid
        rows.append({"item": "code list OID in TS", "namespace": cl_code, "code": cl_oid,
                     "ts_blocks": n, "in_ts": True, "in_evs": cl_code in listing, "minted": False,
                     "note": "" if ok else f"OID Listing: {listing.get(cl_code)}"})
    for block, code, ns in no_oid:
        rows.append({"item": "concept without OID in TS", "namespace": ns, "code": code, "ts_blocks": block,
                     "in_ts": True, "in_evs": (ns, code) in section_members, "minted": True,
                     "note": "namespace derived from the ToC section"})
    with open(REPORTS / "reconciliation.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    multi = {k: v for k, v in specs.items() if len(v) > 1}
    alt_blocks = [b["block"] for b in blocks if block_kind(b) == "element" and len(element_pairs(b, namespace_by_oid)) > 1]
    lines = [
        "# Reconciliation of the D1 sources",
        "",
        "Generated by `scripts/build_d1.py`. Do not edit by hand. Every count in the documentation comes from here or from `scripts/test_d1.py`.",
        "",
        "## Technical Specification, Appendix 1",
        "",
        "| Block kind | Blocks |",
        "| --- | --- |",
    ]
    lines += [f"| {k} | {v} |" for k, v in sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))]
    lines += [
        f"| **all** | **{len(blocks)}** |",
        "",
        "| Elements | Count |",
        "| --- | --- |",
        f"| element blocks | {kinds['element']} |",
        f"| element blocks with alternative concepts (one specification shared by the elements) | {len(alt_blocks)} |",
        f"| distinct (namespace, concept) pairs = elements minted | {len(specs)} |",
        f"| elements specified in more than one block | {len(multi)} |",
        f"| concepts without an OID in the TS (namespace derived from the ToC section) | {len(no_oid)} |",
        f"| blocks with a label printed differently in the PDF (read as the label) | {sum(1 for b in blocks if b.get('printed_label_variants'))} |",
        "",
        "## Elements against EVS section code lists",
        "",
        "| | Count |",
        "| --- | --- |",
        f"| EVS section code list members | {len(section_members)} |",
        f"| in both | {len(ts_pairs & section_members)} |",
        f"| TS only (minted, no EVS term) | {len(ts_pairs - section_members)} |",
        f"| EVS only (reported, not minted) | {len(section_members - ts_pairs)} |",
        "",
    ]
    lines += [f"- TS only: `{ns}.{c}`" for ns, c in sorted(ts_pairs - section_members)]
    lines += [f"- EVS only: `{ns}.{c}`" for ns, c in sorted(section_members - ts_pairs)]
    lines += [
        "",
        "## Sections",
        "",
        "| | Count |",
        "| --- | --- |",
        f"| C217272 terms (sections) | {len(sections)} |",
        f"| distinct sections referenced by heading blocks | {len(heading_tocs)} |",
        f"| distinct sections referenced by element blocks | {len(element_tocs)} |",
        f"| sections referenced by blocks without a C217272 term | {len((heading_tocs | element_tocs) - set(sections))} |",
        f"| C217272 definitions naming another standard than M11 (section number still stated, join kept) | {len(other_standard)} |",
        "",
    ]
    lines += [f"- `{c}` section {k}: definition says \"ICH {std} Protocol standard\"" for c, k, std in sorted(other_standard)]
    lines += [
        "",
        "## Code lists and OIDs",
        "",
        "| | Count |",
        "| --- | --- |",
        f"| code lists in the OID Listing (= Genericode = EVS) | {len(listing)} |",
        f"| namespaces (arc .3) | {len(namespace_by_oid)} |",
        f"| value code lists (arc .1) | {len(listing) - len(namespace_by_oid)} |",
        f"| code list members differing between Genericode and EVS | {len(gc_vs_evs)} |",
        f"| distinct (code list, OID) statements in the TS | {len(stated_cl)} |",
        f"| of which the OID differs from the OID Listing | {sum(1 for (c, o) in stated_cl if listing.get(c) != o)} |",
        "",
    ]
    lines += [f"- `{cl}.{c}`: {where}" for cl, c, where in gc_vs_evs]
    lines += [f"- TS states `{c}` with OID `{o}`; the OID Listing has `{listing.get(c)}`"
              for (c, o) in sorted(stated_cl) if listing.get(c) != o]
    (REPORTS / "reconciliation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
