"""Tests for D2 (m11-usdm.sssom.tsv, m11-usdm.sssom.ttl; m11-rdf.ttl holds no mapping statements).

Checks the mapping set against the pinned SSSOM schema, the D1 graph,
usdm-rdf v0.7.0, the two pinned mapping spreadsheets and
reports/d2-identification.md. Any failure stops with a message; a full pass
prints one line per test and writes reports/tests-d2.md.
"""
import csv
import re
from collections import Counter, defaultdict

import openpyxl
import yaml
from rdflib import Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from common import M11, REPORTS, ROOT, checked
from build_d2 import (COLUMNS, MAP, PREDICATE, SCHEMA, SET_FILE, SET_ID, SOURCES, SSSOM, URL,
                      USDM, USDM_TTL, norm, one_line, schema_slot_uris)

results = []


def check(name, ok, detail=""):
    if not ok:
        raise AssertionError(f"FAILED: {name}. {detail}")
    results.append(name)
    print("ok  ", name)


def report_row(md, label):
    m = re.search(r"^\| " + re.escape(label) + r" \| (\d+) \| (\d+) \|$", md, re.M)
    if not m:
        raise AssertionError(f"Report row not found: {label}")
    return {SOURCES[0]["key"]: int(m.group(1)), SOURCES[1]["key"]: int(m.group(2))}


def report_count(md, label):
    m = re.search(r"^\| " + re.escape(label) + r" \| (\d+) \|$", md, re.M)
    if not m:
        raise AssertionError(f"Report row not found: {label}")
    return int(m.group(1))


def read_tsv():
    text = (ROOT / SET_FILE).read_text(encoding="utf-8")
    head = "\n".join(l[1:] for l in text.split("\n") if l.startswith("#"))
    body = [l for l in text.split("\n") if l and not l.startswith("#")]
    meta = yaml.safe_load(head)
    rows = list(csv.DictReader(body, delimiter="\t"))
    return meta, body[0].split("\t"), rows


def expand(c, curie_map):
    p, l = c.split(":", 1)
    if p not in curie_map:
        raise AssertionError(f"FAILED: prefix {p} of {c} not in the curie_map")
    return URIRef(curie_map[p] + l)


def main():
    schema = yaml.safe_load(checked(SCHEMA).read_text(encoding="utf-8"))
    meta, header, rows = read_tsv()
    md = (REPORTS / "d2-identification.md").read_text(encoding="utf-8")
    cm = meta["curie_map"]

    # SSSOM schema conformance.
    mapping_slots = set(schema["classes"]["mapping"]["slots"])
    set_slots = set(schema["classes"]["mapping set"]["slots"])
    ext_names = {e["slot_name"] for e in meta["extension_definitions"]}
    check("every TSV column is a mapping slot of the pinned SSSOM schema or a declared extension slot",
          set(header) <= mapping_slots | ext_names, str(set(header) - mapping_slots - ext_names))
    check("no extension slot name shadows a standard slot", not (ext_names & (mapping_slots | set_slots)))
    check("every metadata key is a mapping set slot of the pinned SSSOM schema",
          set(meta) <= set_slots, str(set(meta) - set_slots))
    required = {n for n, s in schema["slots"].items() if s.get("required")}
    check("required mapping slots present in every row",
          all(r[c] for r in rows for c in required & mapping_slots), str(required & mapping_slots))
    check("required mapping set slots present",
          all(meta.get(c) for c in required & set_slots), str(required & set_slots))
    pattern = schema["slots"]["mapping_justification"]["pattern"]
    check("every mapping_justification matches the SEMAPV pattern of the schema",
          all(re.fullmatch(pattern, r["mapping_justification"]) for r in rows))
    types = set(schema["enums"]["entity_type_enum"]["permissible_values"])
    check("subject_type and object_type values are in entity_type_enum",
          all(r["subject_type"] in types and r["object_type"] in types for r in rows))
    check("sssom_version is in sssom_version_enum", meta["sssom_version"] in schema["enums"]["sssom_version_enum"]["permissible_values"])
    refs = [n for n, s in schema["slots"].items() if s.get("range") == "EntityReference" and n in header]
    for r in rows:
        for c in refs:
            expand(r[c], cm)
    check("every EntityReference cell is a CURIE with a declared prefix", True, str(refs))
    check("record_id is unique and present in every row", len({r["record_id"] for r in rows}) == len(rows) and all(r["record_id"] for r in rows))
    for e in meta["extension_definitions"]:
        expand(e["property"], cm)
    check("every extension slot property is declared in the curie_map", True)

    # Rows and counts against the sources and the report.
    src_rows = {}
    for s in SOURCES:
        ws = openpyxl.load_workbook(checked(s["file"]), read_only=True)["Mapping"]
        sheet = list(ws.iter_rows(values_only=True))
        col = {k: i for i, k in enumerate(sheet[1]) if k}
        src_rows[s["key"]] = {n: {c: (str(r[col[c]]).strip() if r[col[c]] is not None else "") for c in COLUMNS}
                              for n, r in enumerate(sheet[2:], start=3) if not all(x is None for x in r)}
    per_source = Counter(r["record_id"].split(":", 1)[1].split("/")[0] for r in rows)
    check("mapping rows per source = report", report_row(md, "mapping rows") == {k: len(v) for k, v in src_rows.items()})
    check("statements per source = report", report_row(md, "statements") == dict(per_source))
    check("statements + rows without a statement = mapping rows per source",
          all(report_row(md, "statements")[k] + report_row(md, "rows without a statement")[k] == len(src_rows[k]) for k in src_rows))
    with open(REPORTS / "d2-identification.csv", encoding="utf-8") as f:
        ident = list(csv.DictReader(f))
    check("d2-identification.csv has one line per mapping row", len(ident) == sum(len(v) for v in src_rows.values()))
    with open(REPORTS / "d2-residue.csv", encoding="utf-8") as f:
        residue = list(csv.DictReader(f))
    flagged = report_row(md, "statements flagged")
    check("d2-residue.csv = rows without a statement + flagged statements",
          len(residue) == sum(report_row(md, "rows without a statement").values()) + sum(flagged.values()))
    check("no row is both a statement and a residue row without a flag",
          not any(x["status"] == "statement" and not x["flags"] for x in residue))

    # Each record against its source row.
    for r in rows:
        src, n = r["record_id"].split(":", 1)[1].split("/")
        row = src_rows[src][int(n)]
        if r["source_row"] != n:
            raise AssertionError(f"FAILED: {r['record_id']} source_row {r['source_row']}")
        if (r["stated_class"], r["stated_attribute"]) != (row["Class"], row["Attribute"]):
            raise AssertionError(f"FAILED: {r['record_id']} class/attribute differ from the source row")
        if (r["target_path"], r["condition_path"]) != (one_line(row["Target Path"]), one_line(row["Condition Path"])):
            raise AssertionError(f"FAILED: {r['record_id']} paths differ from the source row")
        if r["source_section"] != (row["Section Number"] or row["Section Title"]):
            raise AssertionError(f"FAILED: {r['record_id']} source_section differs")
        if r["match_string"] != (row["NCIt Code"] if r["subject_identification"] == "by-code" else row["ElementName"]):
            raise AssertionError(f"FAILED: {r['record_id']} match_string differs from the source row")
    check("every record's row, section, class, attribute, paths and match string = its source row", True)

    # Subject against D1.
    g = Graph().parse(ROOT / "m11-rdf.ttl")
    elements = set(g.subjects(RDF.type, M11.Element))
    check("every subject is a D1 element", all(expand(r["subject_id"], cm) in elements for r in rows))
    check("every subject_label = the element's prefLabel",
          all(str(g.value(expand(r["subject_id"], cm), SKOS.prefLabel)) == r["subject_label"] for r in rows))
    for r in [r for r in rows if r["subject_identification"] == "by-code"]:
        if str(g.value(expand(r["subject_id"], cm), M11.ichConceptCode)) != r["match_string"]:
            raise AssertionError(f"FAILED: {r['record_id']} code is not the subject's concept code")
    check("by-code: the match string is the subject's concept code", True)
    terms = defaultdict(set)
    for e in elements:
        for s in g.objects(e, M11.hasSpecification):
            terms[norm(str(g.value(s, M11.tsTerm)))].add((int(g.value(s, M11.tsBlock)), e))
    for r in [r for r in rows if r["subject_identification"] == "by-unique-name"]:
        hits = terms[norm(r["match_string"])]
        if len(hits) != 1 or next(iter(hits))[1] != expand(r["subject_id"], cm):
            raise AssertionError(f"FAILED: {r['record_id']} name is not unique on one block of the subject: {hits}")
    check("by-unique-name: the normalised name is the term of exactly one element block, a block of the subject", True)
    check("identification methods are by-code or by-unique-name only",
          {r["subject_identification"] for r in rows} <= {"by-code", "by-unique-name"})

    # Object against usdm-rdf.
    u = Graph().parse(checked(USDM_TTL))
    kinds = {OWL.ObjectProperty: "owl object property", OWL.DatatypeProperty: "owl data property"}
    for r in rows:
        o = expand(r["object_id"], cm)
        k = [kinds[t] for t in u.objects(o, RDF.type) if t in kinds]
        if k != [r["object_type"]]:
            raise AssertionError(f"FAILED: {r['record_id']} object {o} is not a usdm-rdf {r['object_type']}")
        defining, key = str(o)[len(str(USDM)):].rsplit("-", 1)
        if r["stated_attribute"] not in (key, str(u.value(o, USDM.modelName))):
            raise AssertionError(f"FAILED: {r['record_id']} {r['stated_attribute']} is neither {key} nor the modelName of {o}")
        if u.value(o, RDFS.domain) != USDM[defining]:
            raise AssertionError(f"FAILED: {r['record_id']} domain of {o} is not {defining}")
        if not u.query("ASK { ?c rdfs:subClassOf* ?d }", initBindings={"c": USDM[r["stated_class"]], "d": USDM[defining]},
                       initNs={"rdfs": RDFS}).askAnswer:
            raise AssertionError(f"FAILED: {r['record_id']} {defining} is not {r['stated_class']} or a superclass of it")
        if r["object_label"] != str(o)[len(str(USDM)):]:
            raise AssertionError(f"FAILED: {r['record_id']} object_label")
    check("every object is a usdm-rdf property of the stated type, declared on the stated class or a superclass, "
          "named by the stated attribute or its usdm:modelName", True)

    # SSSOM/RDF agrees with the TSV.
    slot = schema_slot_uris()
    s = Graph().parse(ROOT / "m11-usdm.sssom.ttl")
    ext_prop = {e["slot_name"]: expand(e["property"], cm) for e in meta["extension_definitions"]}
    for graph, name in [(s, "m11-usdm.sssom.ttl")]:
        recs = set(graph.objects(URIRef(SET_ID), slot["mappings"]))
        check(f"{name}: the records = the TSV records", recs == {expand(r["record_id"], cm) for r in rows})
        for r in rows:
            i = expand(r["record_id"], cm)
            for c, p in [("subject_id", slot["subject_id"]), ("predicate_id", slot["predicate_id"]),
                         ("object_id", slot["object_id"]), ("mapping_justification", slot["mapping_justification"])]:
                if list(graph.objects(i, p)) != [expand(r[c], cm)]:
                    raise AssertionError(f"FAILED: {name} {i} {c}")
            for c, p in ext_prop.items():
                vals = [str(v) for v in graph.objects(i, p)]
                if vals != [r[c]]:
                    raise AssertionError(f"FAILED: {name} {i} {c}: {vals} != {r[c]}")
            if (i, RDF.type, OWL.Axiom) not in graph:
                raise AssertionError(f"FAILED: {name} {i} is not an owl:Axiom")
        check(f"{name}: every record has the TSV subject, predicate, object, justification and extension values", True)
    pairs = {(expand(r["subject_id"], cm), expand(r["object_id"], cm)) for r in rows}
    check("m11-usdm.sssom.ttl: direct m11:mappedTo triples = the distinct record pairs",
          set(s.subject_objects(PREDICATE)) == pairs)
    check("m11-usdm.sssom.ttl: m11:mappedTo declared owl:AnnotationProperty, as in m11-rdf.ttl",
          (PREDICATE, RDF.type, OWL.AnnotationProperty) in s and (PREDICATE, RDF.type, OWL.AnnotationProperty) in g)

    # The M11 graph holds no mapping statements; it points at the set without naming a version.
    onto = URIRef(str(M11))
    check("m11-rdf.ttl: no owl:Axiom, no m11:mappedTo, no sssom:MappingSet, no dcterms:hasPart",
          (None, RDF.type, OWL.Axiom) not in g and (None, PREDICATE, None) not in g
          and (None, RDF.type, SSSOM.MappingSet) not in g and (None, DCTERMS.hasPart, None) not in g)
    check("m11-rdf.ttl: rdfs:seeAlso the unversioned mapping_set_id", (onto, RDFS.seeAlso, URIRef(SET_ID)) in g)
    sheets = {URIRef(URL[x["file"]]) for x in SOURCES}
    check("the mapping spreadsheets are see_also of the set, not dcterms:source of m11-rdf.ttl",
          sheets <= set(s.objects(URIRef(SET_ID), RDFS.seeAlso)) and not sheets & set(g.objects(onto, DCTERMS.source)))
    check("record IRIs are <namespace>mapping/<source>/<row>",
          all(str(expand(r["record_id"], cm)) == f"{MAP}{r['record_id'].split(':', 1)[1]}" and
              re.fullmatch(r"(hl7|cdisc)/\d+", r["record_id"].split(":", 1)[1]) for r in rows))

    # The comparison in the report.
    per = defaultdict(lambda: defaultdict(set))
    for r in rows:
        per[r["subject_id"]][r["record_id"].split(":", 1)[1].split("/")[0]].add(r["object_id"])
    a, b = SOURCES[0]["key"], SOURCES[1]["key"]
    both = [e for e in per if per[e][a] and per[e][b]]
    check("elements with statements from both = report", len(both) == report_count(md, "elements with statements from both"))
    check("of which the same USDM targets = report",
          sum(per[e][a] == per[e][b] for e in both) == report_count(md, "of which the same USDM targets"))
    check("D1 elements without a statement = report",
          len(elements) - len(per) == report_count(md, "D1 elements without a statement"))

    REPORTS.mkdir(exist_ok=True)
    lines = ["# D2 tests", "", "Generated by `scripts/test_d2.py`. Do not edit by hand. All passed.", ""]
    lines += [f"- {x}" for x in results]
    (REPORTS / "tests-d2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(len(results), "tests passed")


if __name__ == "__main__":
    main()
