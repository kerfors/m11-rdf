"""Tests for D5 (the ICH M11 Template headings and fields in m11-rdf.ttl).

Checks the extraction against its pinned hash and the Template PDF, the graph
against build/template.json and D1, every link to an element against its
recorded basis, and the counts in reports/d5-template.md. Any failure stops
with a message; a full pass prints one line per test and writes
reports/tests-d5.md.
"""
import csv
import hashlib
import json
import re
from collections import Counter

import pymupdf
from rdflib import BNode, Graph
from rdflib.namespace import RDF, SKOS

from build_d2 import norm
from build_d5 import D1, KIND, TIERS, heading_before, in_section, label_name, local, top
from common import BUILD, M11, REPORTS, ROOT, TEMPLATE_JSON_SHA256, TEMPLATE_PDF, checked

results = []


def check(name, ok, detail=""):
    if not ok:
        raise AssertionError(f"FAILED: {name}. {detail}")
    results.append(name)
    print("ok  ", name)


def report_count(md, label):
    m = re.search(r"^\| " + re.escape(label) + r" \| (\d+) \|$", md, re.M)
    if not m:
        raise AssertionError(f"Report row not found: {label}")
    return int(m.group(1))


def one_space(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    raw = (BUILD / "template.json").read_bytes()
    check("build/template.json has the pinned SHA-256", hashlib.sha256(raw).hexdigest() == TEMPLATE_JSON_SHA256)
    tpl = json.loads(raw)
    g = Graph().parse(ROOT / "m11-rdf.ttl")
    d1 = D1(g)
    blocks = {b["block"]: b for b in json.loads((BUILD / "ts_blocks.json").read_text(encoding="utf-8"))}
    md = (REPORTS / "d5-template.md").read_text(encoding="utf-8")

    # Headings and sections.
    numbered = [h for h in tpl["headings"] if h["number"][0].isdigit() and "X" not in h["number"].split(".")]
    secnums = {k for k in d1.sections if k[0].isdigit()}
    check("numbered Template headings = numbered C217272 sections, one to one",
          sorted(h["number"] for h in numbered) == sorted(secnums) and len(numbered) == len(secnums))
    check("Amendment Details heading found exactly once",
          sum(1 for h in tpl["headings"] if h["number"] == "Amendment Details") == 1)
    check("every heading is the H tag of its numbering depth, or Amendment Details as P",
          all((h["tag"] == "P") == (h["number"] == "Amendment Details") and
              (h["tag"] == "P" or int(h["tag"][1]) == len(h["number"].split("."))) for h in tpl["headings"]))
    with_heading = {s for s in g.subjects(M11.templateHeading, None)}
    check("every rendered heading is on its section with the title as extracted",
          all([str(x) for x in g.objects(d1.sections[h["number"]], M11.templateHeading)] == [h["title"]]
              for h in tpl["headings"] if "X" not in h["number"].split(".")) and
          len(with_heading) == len(tpl["headings"]) - sum(1 for h in tpl["headings"] if "X" in h["number"].split(".")))
    for s, e in g.subject_objects(M11.headingElement):
        scope = str(g.value(s, M11.placeScope))
        key = str(g.value(s, M11.sectionNumber) or g.value(s, SKOS.prefLabel))
        ok = any(norm(t) == norm(str(g.value(s, M11.templateHeading))) and
                 (in_section(key, p) if scope == "section" else d1.namespace_top(e) == top(key))
                 for _, t, _, _, p in d1.specs[e])
        if not ok:
            raise AssertionError(f"FAILED: heading element {local(s)} -> {local(e)} does not hold under {scope}")
    check("every heading element: heading = TS term of the element, in the recorded scope", True)

    # Fields: graph = extraction.
    nodes = sorted(g.subjects(RDF.type, M11.TemplateField), key=lambda n: int(g.value(n, M11.templateOrder)))
    check("one Template field node per extracted field", len(nodes) == len(tpl["fields"]))
    check("every field node is a blank node on exactly one section",
          all(isinstance(n, BNode) and len(list(g.subjects(M11.hasTemplateField, n))) == 1 for n in nodes))
    single = [M11.fieldLabel, M11.fieldKind, M11.templateSectionNumber, M11.templatePage, M11.templateOrder,
              M11.templateOptional, M11.templateConditional]
    check("every field has exactly one label, kind, section number, page, order, optional and conditional",
          all(len(list(g.objects(n, p))) == 1 for n in nodes for p in single))
    for n, f in zip(nodes, tpl["fields"]):
        got = (str(g.value(n, M11.fieldLabel)), g.value(n, M11.fieldKind), str(g.value(n, M11.templateSectionNumber)),
               int(g.value(n, M11.templatePage)), int(g.value(n, M11.templateOrder)),
               g.value(n, M11.templateOptional).toPython(), g.value(n, M11.templateConditional).toPython())
        want = (f["label"], KIND[f["kind"]], f["section"], f["page"], f["order"], f["optional"], f["conditional"])
        if got != want:
            raise AssertionError(f"FAILED: field {f['order']}: {got} != {want}")
        sec = g.value(predicate=M11.hasTemplateField, object=n)
        key = f["section"][:-2] if f["section"].endswith(".X") else f["section"]
        if sec != d1.sections[key]:
            raise AssertionError(f"FAILED: field {f['order']} on {local(sec)}, expected section {key}")
    check("every field node carries the extracted values and is on the section of its heading", True)

    # Fields against the PDF.
    doc = pymupdf.open(checked(TEMPLATE_PDF))
    page_text = {i + 1: one_space(p.get_text()) for i, p in enumerate(doc)}
    missing = [f["order"] for f in tpl["fields"] if f["label"] not in page_text[f["page"]] and
               f["label"].replace(" ", "") not in page_text[f["page"]].replace(" ", "")]
    check("every field label occurs in the text of its PDF page (spaces ignored where the PDF splits words)",
          not missing, str(missing))
    check("field kinds agree with the brackets printed on the page",
          all(("<" + f["label"].split(" ")[0]) in page_text[f["page"]].replace("< ", "<") if f["kind"] == "insert" else
              ("[" + f["label"].split(" ")[0]) in page_text[f["page"]].replace("[ ", "[") for f in tpl["fields"]))

    # Links.
    links = [(n, g.value(n, M11.realises)) for n in nodes if g.value(n, M11.realises) is not None]
    for n, e in links:
        label = str(g.value(n, M11.fieldLabel))
        tsec = str(g.value(n, M11.templateSectionNumber))
        src, match, scope = (str(g.value(n, p)) for p in (M11.nameSource, M11.nameMatch, M11.placeScope))
        name = label_name(label, match)
        if src == "ts-term" or src == "ts-heading-context":
            ok = name is not None and any(norm(t) == name and (in_section(tsec, p) if scope == "section" else d1.namespace_top(e) == top(tsec))
                                          for _, t, _, _, p in d1.specs[e])
        else:
            ok = name is not None and e in d1.evs_label and norm(d1.evs_label[e]) == name and \
                 any(in_section(tsec, p) for _, _, _, _, p in d1.specs[e])
        if src == "ts-heading-context":
            f = tpl["fields"][int(g.value(n, M11.templateOrder)) - 1]
            ok = ok and any(heading_before(blocks, b) and norm(heading_before(blocks, b)["term"]) == norm(f["row_first_cell"])
                            for b, _, _, _, p in d1.specs[e] if in_section(tsec, p))
        if not ok:
            raise AssertionError(f"FAILED: field {g.value(n, M11.templateOrder)} -> {local(e)} does not hold under {src}/{match}/{scope}")
    check("every realises link holds under its recorded name source, match and scope", True)
    check("every realises link has exactly one name source, match and scope from the defined values",
          all([str(x) for x in g.objects(n, M11.nameSource)] in (["ts-term"], ["evs-label"], ["ts-heading-context"]) and
              [str(x) for x in g.objects(n, M11.nameMatch)] in (["exact"], ["verb-dropped"]) and
              [str(x) for x in g.objects(n, M11.placeScope)] in (["section"], ["namespace"]) for n, _ in links))
    check("no field without an element carries a name source, match or scope",
          all(not list(g.objects(n, p)) for n in nodes if g.value(n, M11.realises) is None
              for p in (M11.nameSource, M11.nameMatch, M11.placeScope)))
    check("no link to an element outside the field's section and namespace",
          all(any(in_section(str(g.value(n, M11.templateSectionNumber)), p) for _, _, _, _, p in d1.specs[e]) or
              d1.namespace_top(e) == top(str(g.value(n, M11.templateSectionNumber))) for n, e in links))
    check("realises only points at D1 elements", all(e in d1.specs for _, e in links))

    # Residue and report.
    with open(REPORTS / "d5-residue.csv", encoding="utf-8") as f:
        residue = list(csv.DictReader(f))
    unlinked = [n for n in nodes if g.value(n, M11.realises) is None]
    no_el = [r for r in residue if r["what"] == "field without an element"]
    check("every field without an element is in the residue once", len(no_el) == len(unlinked))
    check("no field in the residue is unexplained", all(r["category"] != "unexplained" for r in no_el),
          str([r["text"] for r in no_el if r["category"] == "unexplained"]))
    reached = {e for _, e in links} | set(g.objects(None, M11.headingElement))
    check("D1 elements not reached = residue rows",
          sorted(local(e) for e in d1.elements if e not in reached) ==
          sorted(r["detail"] for r in residue if r["what"] == "D1 element not reached"))
    with open(REPORTS / "d5-fields.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    check("d5-fields.csv has one row per field with the graph's element",
          len(rows) == len(nodes) and all(r["element"] == (local(g.value(n, M11.realises)) if g.value(n, M11.realises) else "")
                                          for r, n in zip(rows, nodes)))
    check("report: fields = graph", report_count(md, "fields") == len(nodes))
    check("report: fields that realise an element = graph", report_count(md, "fields that realise an element") == len(links))
    check("report: elements reached = graph", report_count(md, "elements reached") == len(reached))
    check("report: numbered headings with a C217272 section = graph",
          report_count(md, "numbered headings with a C217272 section") ==
          sum(1 for s in with_heading if g.value(s, M11.sectionNumber) is not None))
    check("report: link counts per basis add up to the linked fields",
          sum(report_count(md, f"realises, {s} / {m} / {sc}") for s, m, sc in
              {(str(g.value(n, M11.nameSource)), str(g.value(n, M11.nameMatch)), str(g.value(n, M11.placeScope))) for n, _ in links})
          == len(links))
    check("report: optional and conditional fields = graph",
          report_count(md, "fields optional (blue)") == sum(g.value(n, M11.templateOptional).toPython() for n in nodes) and
          report_count(md, "fields conditional") == sum(g.value(n, M11.templateConditional).toPython() for n in nodes))
    check("blank nodes in m11-rdf.ttl: one per specification and one per Template field",
          {x for t in g for x in t if isinstance(x, BNode)} ==
          set(g.subjects(RDF.type, M11.Specification)) | set(nodes))

    REPORTS.mkdir(exist_ok=True)
    lines = ["# D5 tests", "", "Generated by `scripts/test_d5.py`. Do not edit by hand. All passed.", ""]
    lines += [f"- {x}" for x in results]
    (REPORTS / "tests-d5.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(len(results), "tests passed")


if __name__ == "__main__":
    main()
