"""Tests for D1 (m11-rdf.ttl) against the pinned inputs and the reconciliation report.

Each test is an ASK query or a direct check. Any failure stops with a message;
a full pass prints one line per test and writes reports/tests.md.
"""
import json
import re

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, SKOS

from common import BUILD, EVS, M11, NCIT, OBO, REPORTS, ROOT, SECTION_CODELIST, evs_owl_bytes, evs_rows
from build_d1 import block_kind, element_pairs

CTS = Namespace("http://rdf.ich.org/ct/schema#")
MMS = Namespace("http://rdf.ich.org/mms#")
PREFIXES = """
PREFIX m11: <https://w3id.org/m11-rdf/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""

results = []


def check(name, ok, detail=""):
    if not ok:
        raise AssertionError(f"FAILED: {name}. {detail}")
    results.append(name)
    print("ok  ", name)


def ask_none(g, name, where):
    """The test passes when no solution exists for the pattern."""
    q = PREFIXES + "ASK { " + where + " }"
    check(name, not g.query(q).askAnswer, "ASK found a counter-example: " + where)


def local(iri):
    return str(iri)[len(str(M11)):]


def report_count(md, label):
    m = re.search(r"^\| " + re.escape(label) + r" \| (\d+) \|$", md, re.M)
    if not m:
        raise AssertionError(f"Reconciliation row not found: {label}")
    return int(m.group(1))


def main():
    g = Graph().parse(ROOT / "m11-rdf.ttl")
    md = (REPORTS / "reconciliation.md").read_text(encoding="utf-8")
    blocks = json.loads((BUILD / "ts_blocks.json").read_text(encoding="utf-8"))
    elements = set(g.subjects(RDF.type, M11.Element))
    sections = set(g.subjects(RDF.type, M11.Section))
    namespaces = set(g.subjects(RDF.type, M11.Namespace))
    value_lists = set(g.subjects(RDF.type, M11.ValueCodeList))
    specs = set(g.subjects(RDF.type, M11.Specification))

    # Counts equal the reconciliation report.
    check("element count = reconciliation", len(elements) == report_count(md, "distinct (namespace, concept) pairs = elements minted"))
    check("section count = reconciliation", len(sections) == report_count(md, "C217272 terms (sections)"))
    check("namespace count = reconciliation", len(namespaces) == report_count(md, "namespaces (arc .3)"))
    check("value code list count = reconciliation", len(value_lists) == report_count(md, "value code lists (arc .1)"))
    check("specification count = element blocks", len(specs) == report_count(md, "element blocks"))
    check("TS-only elements = elements labelled from the TS",
          len(set(g.subjects(M11.labelSource, M11.TechnicalSpecification))) == report_count(md, "TS only (minted, no EVS term)"))

    # Element identity.
    for e in elements:
        ns = list(g.objects(e, SKOS.inScheme))
        code = list(g.objects(e, M11.ichConceptCode))
        oid = list(g.objects(e, M11.ichNamespaceOid))
        if len(ns) != 1 or len(code) != 1 or len(oid) != 1:
            raise AssertionError(f"FAILED: element {e} needs exactly one namespace, concept code and namespace OID")
        if local(e) != f"{local(ns[0])}.{code[0]}":
            raise AssertionError(f"FAILED: {e} local name is not <namespace>.<concept code>")
        if (ns[0], RDF.type, M11.Namespace) not in g:
            raise AssertionError(f"FAILED: {e} is in a scheme that is not an M11 namespace")
        if oid[0] != g.value(ns[0], SKOS.notation):
            raise AssertionError(f"FAILED: {e} namespace OID differs from its namespace's OID")
    check("every element IRI = <namespace>.<concept code>, one namespace, OID = namespace OID", True)
    ask_none(g, "every element has exactly one prefLabel, pair basis and label source", """
        ?e a m11:Element .
        { FILTER NOT EXISTS { ?e skos:prefLabel ?l } } UNION
        { ?e skos:prefLabel ?a, ?b FILTER(?a != ?b) } UNION
        { FILTER NOT EXISTS { ?e m11:pairBasis ?p } } UNION
        { FILTER NOT EXISTS { ?e m11:labelSource ?s } }""")
    ask_none(g, "every element has at least one specification", """
        ?e a m11:Element FILTER NOT EXISTS { ?e m11:hasSpecification ?s }""")

    # The pair as stated in the TS (M5): recompute from the parsed blocks.
    namespace_by_oid = {str(g.value(n, SKOS.notation)): local(n) for n in namespaces}
    stated = set()
    for b in blocks:
        if block_kind(b) == "element":
            for ns, code, oid in element_pairs(b, namespace_by_oid):
                if oid:
                    stated.add(f"{ns}.{code}")
    by_basis = {local(e) for e in g.subjects(M11.pairBasis, M11.StatedInTS)}
    derived = {local(e) for e in g.subjects(M11.pairBasis, M11.DerivedFromSection)}
    check("elements with pair basis StatedInTS = pairs stated with OID in the TS", by_basis == stated,
          f"difference: {by_basis ^ stated}")
    check("derived pairs = concepts without OID in the reconciliation",
          len(derived) == report_count(md, "concepts without an OID in the TS (namespace derived from the ToC section)"))

    # NCIt references always as the D4 pair.
    for s in set(g.subjects(M11.concept, None)):
        codes_ncit = {str(o)[len(str(NCIT)):] for o in g.objects(s, M11.concept) if str(o).startswith(str(NCIT))}
        codes_obo = {str(o)[len(str(OBO)) + len("NCIT_"):] for o in g.objects(s, M11.concept) if str(o).startswith(str(OBO))}
        if len(codes_ncit) != 1 or codes_ncit != codes_obo:
            raise AssertionError(f"FAILED: {s} has an NCIt reference without its pair: {codes_ncit} / {codes_obo}")
    check("every NCIt reference has both forms (EVS identifier and OBO PURL), one concept each", True)
    ask_none(g, "no element, section or code list uses skos:exactMatch to an NCIt IRI", """
        ?s skos:exactMatch ?o FILTER(STRSTARTS(STR(?o), "http://ncicb.nci.nih.gov/") || STRSTARTS(STR(?o), "http://purl.obolibrary.org/"))""")

    # EVS: txt and OWL agree, and every exactMatch target exists in the OWL.
    owl = Graph().parse(data=evs_owl_bytes(), format="xml")
    owl_terms = set(owl.subjects(RDF.type, MMS.PermissibleValue)) | set(owl.subjects(RDF.type, MMS.EnumeratedValueDomain))
    rows = evs_rows()
    txt_iris = {EVS[f"{r['Codelist Code']}.{r['Code']}"] if r["Codelist Code"] else EVS[r["Code"]] for r in rows}
    check("EVS txt and OWL list the same terms and code lists", txt_iris == owl_terms, f"difference: {txt_iris ^ owl_terms}")
    for r in rows:
        iri = EVS[f"{r['Codelist Code']}.{r['Code']}"] if r["Codelist Code"] else EVS[r["Code"]]
        if str(owl.value(iri, CTS.ichPreferredTerm)) != r["ICH Preferred Term"] or str(owl.value(iri, CTS.ichDefinition)) != r["ICH Definition"]:
            raise AssertionError(f"FAILED: EVS txt and OWL differ for {iri}")
    check("EVS txt and OWL agree on every ICH preferred term and definition", True)
    targets = set(g.objects(None, SKOS.exactMatch))
    check("every skos:exactMatch target exists in the pinned EVS OWL", targets <= owl_terms, f"missing: {targets - owl_terms}")
    for e in elements:
        t = g.value(e, SKOS.exactMatch)
        if t is not None and str(g.value(e, SKOS.prefLabel)) != str(owl.value(t, CTS.ichPreferredTerm)):
            raise AssertionError(f"FAILED: {e} label differs from its EVS term")
    check("every element label with an EVS twin = the EVS ICH preferred term", True)

    # Specifications.
    ask_none(g, "every specification has exactly one section, conformance category, TS block and ToC reference", """
        ?s a m11:Specification .
        { FILTER NOT EXISTS { ?s m11:inSection ?x } } UNION { ?s m11:inSection ?a, ?b FILTER(?a != ?b) } UNION
        { FILTER NOT EXISTS { ?s m11:hasConformanceCategory ?x } } UNION { ?s m11:hasConformanceCategory ?a, ?b FILTER(?a != ?b) } UNION
        { FILTER NOT EXISTS { ?s m11:tsBlock ?x } } UNION { ?s m11:tsBlock ?a, ?b FILTER(?a != ?b) } UNION
        { FILTER NOT EXISTS { ?s m11:tocReference ?x } }""")
    ask_none(g, "no two specifications share a TS block number", """
        ?a m11:tsBlock ?n . ?b m11:tsBlock ?n FILTER(?a != ?b)""")
    ask_none(g, "every specification section is an m11:Section", """
        ?s m11:inSection ?x FILTER NOT EXISTS { ?x a m11:Section }""")
    ask_none(g, "every value code list is an M11 code list", """
        ?s m11:hasValueCodeList ?x FILTER NOT EXISTS { { ?x a m11:ValueCodeList } UNION { ?x a m11:Namespace } }""")
    differing = {(local(g.value(s, M11.hasValueCodeList)), str(o)) for s, o in g.subject_objects(M11.statedCodeListOid)
                 if str(o) != str(g.value(g.value(s, M11.hasValueCodeList), SKOS.notation))}
    check("stated code list OIDs differing from the OID Listing = reconciliation",
          len(differing) == report_count(md, "of which the OID differs from the OID Listing"), str(differing))

    # Sections.
    ask_none(g, "every section has exactly one prefLabel and is in C217272", """
        ?s a m11:Section .
        { FILTER NOT EXISTS { ?s skos:prefLabel ?l } } UNION { ?s skos:prefLabel ?a, ?b FILTER(?a != ?b) } UNION
        { FILTER NOT EXISTS { ?s skos:inScheme m11:""" + SECTION_CODELIST + """ } }""")
    ask_none(g, "every numbered section below the top level has exactly one broader section", """
        ?s m11:sectionNumber ?n FILTER(CONTAINS(?n, ".")) .
        { FILTER NOT EXISTS { ?s skos:broader ?b } } UNION { ?s skos:broader ?a, ?b FILTER(?a != ?b) }""")
    ask_none(g, "a broader section's number is the prefix of its narrower section's number", """
        ?s skos:broader ?b . ?s m11:sectionNumber ?n . ?b m11:sectionNumber ?m
        FILTER(!STRSTARTS(?n, CONCAT(?m, ".")))""")
    ask_none(g, "every namespace is linked to one top-level section", """
        ?n a m11:Namespace .
        { FILTER NOT EXISTS { ?n m11:forSection ?s } } UNION { ?n m11:forSection ?a, ?b FILTER(?a != ?b) } UNION
        { ?n m11:forSection ?s . ?s skos:broader ?x }""")

    # Code lists.
    ask_none(g, "every code list has exactly one OID", """
        { ?c a m11:Namespace } UNION { ?c a m11:ValueCodeList } .
        { FILTER NOT EXISTS { ?c skos:notation ?o } } UNION { ?c skos:notation ?a, ?b FILTER(?a != ?b) }""")

    # IRIs: no two minted local names differ only by case (GitHub Pages paths on macOS).
    minted = {local(s) for s in g.subjects() if isinstance(s, URIRef) and str(s).startswith(str(M11)) and local(s)}
    lowered = {}
    for name in minted:
        lowered.setdefault(name.lower(), []).append(name)
    clashes = [v for v in lowered.values() if len(v) > 1]
    check("no two minted local names differ only by case", not clashes, str(clashes))

    REPORTS.mkdir(exist_ok=True)
    lines = ["# D1 tests", "", "Generated by `scripts/test_d1.py`. Do not edit by hand. All passed.", ""]
    lines += [f"- {r}" for r in results]
    (REPORTS / "tests.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(len(results), "tests passed")


if __name__ == "__main__":
    main()
