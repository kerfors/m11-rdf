"""Build D5: the headings and fields of the ICH M11 Template, linked to D1.

Inputs: build/template.json (parse_template.py, pinned extraction of the
Template PDF), build/ts_blocks.json (parse_ts.py) and m11-rdf.ttl as written
by build_d2.py (run build_d1.py and build_d2.py first).

Headings: each numbered Template heading is recorded on the C217272 section
with that number (m11:templateHeading, page, optional, conditional);
Amendment Details on its section by name. A heading whose title, without the
repeat number <#>, equals the Technical Specification term of an element
(normalised as in D2) gets m11:headingElement, looked for in the section,
then in the namespace for the top-level section. The repeating heading 12.X has no C217272 term and is not
rendered (DECISIONS M7); its fields are on section 12.

Fields: one blank node per field on its section, with label, kind, page,
order, the section number as printed, and the optional and conditional flags.
A field realises an element when its label equals a name of exactly one
element, tried in this order, first hit decides:
  1. TS term, exact, section       2. TS term, verb-dropped, section
  3. TS term, exact, namespace     4. TS term, verb-dropped, namespace
  5. EVS label, exact, section     6. EVS label, verb-dropped, section
"section": an element block whose ToC reference is the field's section (X and
# read as any number); "namespace": the element's namespace is for the
field's top-level section (m11:forSection); "verb-dropped": one leading verb
of a fixed list removed; EVS label: the element's preferred term where it
comes from EVS. When a tier finds several elements, the one whose block
follows a TS heading block equal to the first cell of the field's table row
is taken (ts-heading-context); otherwise the field realises none. A name that
only occurs in another section is reported, not linked.

Outputs: m11-rdf.ttl (D1 and D2 plus D5), reports/d5-template.md,
reports/d5-fields.csv, reports/d5-residue.csv (input for usdm-overlay).
"""
import csv
import json
import re
from collections import Counter, defaultdict

from rdflib import BNode, Graph, Literal
from rdflib.namespace import RDF, SKOS, XSD

from build_d2 import norm
from common import BUILD, M11, REPORTS, ROOT

VERB = re.compile(r"^(enter|select|insert|specify|provide|add|describe|state|list)\s+", re.I)
NAMED = {"title page": "Title Page", "amendment details": "Amendment Details", "table of contents": "Table of Contents"}
TIERS = [("ts-term", "exact", "section"), ("ts-term", "verb-dropped", "section"),
         ("ts-term", "exact", "namespace"), ("ts-term", "verb-dropped", "namespace"),
         ("evs-label", "exact", "section"), ("evs-label", "verb-dropped", "section")]
KIND = {"insert": M11.TextInsertion, "pick": M11.ControlledTerminology}
BRACKETS = re.compile(r"<[^<>]+>|\[[^\[\]]+\]")


def local(iri):
    return str(iri)[len(str(M11)):]


def place(toc):
    """ToC reference -> place: a section name, or a number with X/# segments ("12 X where ..." -> 12.X)."""
    t = toc.strip()
    if t.lower() in NAMED:
        return NAMED[t.lower()]
    m = re.match(r"\d+(?:[. ](?:\d+|X|#))*", t)
    if not m:
        raise RuntimeError(f"Unplaceable ToC reference: {toc!r}")
    return m.group(0).replace(" ", ".")


def in_section(tsec, p):
    """Template section (number as printed, or name) against a TS place; X and # read as any number."""
    if not tsec[0].isdigit() or not p[0].isdigit():
        return tsec == p
    a, b = tsec.split("."), p.split(".")
    return len(a) == len(b) and all(x == y or y in ("X", "#") or x == "X" for x, y in zip(a, b))


def top(tsec):
    return tsec.split(".")[0] if tsec[0].isdigit() else tsec


def label_name(label, match):
    """Normalised field label for a match mode; None when verb-dropped does not apply."""
    if match == "exact":
        return norm(label)
    if not VERB.match(label):
        return None
    return norm(VERB.sub("", label))


def bracket_kind(term):
    found = BRACKETS.findall(term)
    if len(found) != 1:
        return "none" if not found else "several"
    return "insert" if found[0].startswith("<") else "pick"


class D1:
    def __init__(self, g):
        self.g = g
        self.sections = {}
        for s in g.subjects(RDF.type, M11.Section):
            num = g.value(s, M11.sectionNumber)
            self.sections[str(num) if num is not None else str(g.value(s, SKOS.prefLabel))] = s
        self.ns_top = {}
        for n in g.subjects(RDF.type, M11.Namespace):
            sec = g.value(n, M11.forSection)
            num = g.value(sec, M11.sectionNumber)
            self.ns_top[n] = str(num) if num is not None else str(g.value(sec, SKOS.prefLabel))
        self.elements = sorted(g.subjects(RDF.type, M11.Element), key=str)
        self.specs = {}      # element -> [(block, term, dvh, conformance category, place)]
        self.evs_label = {}
        self.block_elements = defaultdict(set)
        for e in self.elements:
            rows = []
            for s in g.objects(e, M11.hasSpecification):
                b = int(g.value(s, M11.tsBlock))
                rows.append((b, str(g.value(s, M11.tsTerm)), str(g.value(s, M11.dvh)),
                             local(g.value(s, M11.hasConformanceCategory)), place(str(g.value(s, M11.tocReference)))))
                self.block_elements[b].add(e)
            self.specs[e] = sorted(rows)
            if g.value(e, M11.labelSource) == M11.EVSTerminology:
                self.evs_label[e] = str(g.value(e, SKOS.prefLabel))

    def namespace_top(self, e):
        return self.ns_top[self.g.value(e, SKOS.inScheme)]

    def find(self, name, source, scope, tsec):
        out = set()
        for e in self.elements:
            if source == "ts-term":
                for b, term, _, _, p in self.specs[e]:
                    if norm(term) == name and (in_section(tsec, p) if scope == "section" else self.namespace_top(e) == top(tsec)):
                        out.add(e)
            elif e in self.evs_label and norm(self.evs_label[e]) == name and any(in_section(tsec, p) for _, _, _, _, p in self.specs[e]):
                out.add(e)
        return sorted(out, key=str)

    def anywhere(self, name):
        return sorted({e for e in self.elements for _, term, _, _, _ in self.specs[e] if norm(term) == name}, key=str)


def heading_before(blocks, b):
    """The Technical Specification heading block (D/V/H = H) nearest before block b."""
    i = b - 1
    while i >= 1 and blocks[i]["dvh"] != "H":
        i -= 1
    return blocks[i] if i >= 1 else None


def link_field(f, d1, blocks):
    for source, match, scope in TIERS:
        name = label_name(f["label"], match)
        if name is None:
            continue
        hits = d1.find(name, source, scope, f["section"])
        if not hits:
            continue
        if len(hits) == 1:
            return {"element": hits[0], "source": source, "match": match, "scope": scope, "candidates": hits}
        ctx = [e for e in hits if f["row_first_cell"] and any(
            heading_before(blocks, b) and norm(heading_before(blocks, b)["term"]) == norm(f["row_first_cell"])
            for b, _, _, _, p in d1.specs[e] if in_section(f["section"], p))]
        if len(ctx) == 1:
            return {"element": ctx[0], "source": "ts-heading-context", "match": match, "scope": scope, "candidates": hits}
        return {"element": None, "source": source, "match": match, "scope": scope, "candidates": hits}
    return {"element": None, "source": "", "match": "", "scope": "", "candidates": []}


def residue_category(f, d1, blocks):
    """Category of a field that realises no element, by rules on the TS blocks in the field's place."""
    n = label_name(f["label"], "verb-dropped") or norm(f["label"])
    unit = " " + norm(f["unit_text"]) + " "
    for strict in (True, False):
        for i in sorted(blocks):
            b = blocks[i]
            els = sorted(d1.block_elements.get(i, ()), key=str)
            if not (in_section(f["section"], place(b["toc"])) or any(d1.namespace_top(e) == top(f["section"]) for e in els)):
                continue
            bt = norm(b["term"])
            if bt == n and not els:
                return "TS block without an element", f"block {i}"
            if n and (" " + n + " ") in (" " + bt + " ") and ((" " + bt + " ") in unit or not strict):
                if els:
                    return "part of an element's TS term", f"block {i}: " + ";".join(local(e) for e in els)
                return "part of a TS block term without an element", f"block {i}"
    squash = n.replace(" ", "")
    for i in sorted(d1.block_elements):
        if in_section(f["section"], place(blocks[i]["toc"])) and norm(blocks[i]["term"]).replace(" ", "") == squash:
            return "spelling (hyphen or space)", f"block {i}: " + ";".join(local(e) for e in sorted(d1.block_elements[i], key=str))
    return "unexplained", ""


def kind_group(f, e, d1):
    specs = d1.specs[e]
    dvhs = {d for _, _, d, _, _ in specs}
    if (f["kind"] == "insert" and dvhs == {"D"}) or (f["kind"] == "pick" and dvhs == {"V"}):
        return ""
    if any(len(d1.block_elements[b]) > 1 or bracket_kind(t) == "several" for b, t, _, _, _ in specs):
        return "combined TS block (one D/V/H for several fields)"
    if len(dvhs) > 1 or any(len(re.findall(r"\b[DVH]\b", d)) > 1 for d in dvhs):
        return "TS gives several D/V/H"
    kinds = {bracket_kind(t) for _, t, _, _, _ in specs}
    if kinds != {f["kind"]}:
        return "Template bracket differs from TS term"
    return "TS term bracket differs from TS D/V/H"


def section_of(tsec, d1):
    key = tsec[:-2] if tsec.endswith(".X") else tsec
    return d1.sections[key]


def relabel(g):
    """Copy of g with blank nodes labelled spec<TS block> and field<Template order>."""
    label = {s: BNode(f"spec{g.value(s, M11.tsBlock)}") for s in g.subjects(RDF.type, M11.Specification)}
    label.update({f: BNode(f"field{g.value(f, M11.templateOrder)}") for f in g.subjects(RDF.type, M11.TemplateField)})
    if len(set(label.values())) != len(label) or any(isinstance(x, BNode) and x not in label for t in g for x in t):
        raise RuntimeError("Blank nodes other than one per specification and one per Template field")
    out = Graph()
    for prefix, ns in g.namespaces():
        out.bind(prefix, ns)
    for s, p, o in g:
        out.add((label.get(s, s), p, label.get(o, o)))
    return out


def main():
    g = Graph().parse(ROOT / "m11-rdf.ttl")
    if (None, RDF.type, M11.TemplateField) in g or (None, M11.templateHeading, None) in g:
        raise RuntimeError("m11-rdf.ttl already holds Template data; run build_d1.py and build_d2.py first")
    tpl = json.loads((BUILD / "template.json").read_text(encoding="utf-8"))
    blocks = {b["block"]: b for b in json.loads((BUILD / "ts_blocks.json").read_text(encoding="utf-8"))}
    d1 = D1(g)

    # Headings.
    heads = []
    for h in tpl["headings"]:
        if "X" in h["number"].split("."):
            heads.append({**h, "section": None, "element": None, "scope": ""})
            continue
        if h["number"] not in d1.sections:
            raise RuntimeError(f"Template heading {h['number']} has no C217272 section")
        hit, scope = None, ""
        for sc in ("section", "namespace"):
            found = d1.find(norm(h["title"].replace("<#>", "")), "ts-term", sc, h["number"])
            if len(found) > 1:
                raise RuntimeError(f"Heading {h['number']} equals the TS term of several elements: {found}")
            if found:
                hit, scope = found[0], sc
                break
        heads.append({**h, "section": d1.sections[h["number"]], "element": hit, "scope": scope})
    numbered = [h for h in heads if h["section"] is not None and h["number"][0].isdigit()]
    if len({h["number"] for h in numbered}) != len(numbered):
        raise RuntimeError("Two Template headings with one number")

    # Fields.
    fields = []
    for f in tpl["fields"]:
        x = {**f, **link_field(f, d1, blocks), "section_iri": section_of(f["section"], d1)}
        x["other"] = []
        if x["element"] is None and not x["candidates"]:
            name_e, name_v = label_name(f["label"], "exact"), label_name(f["label"], "verb-dropped")
            x["other"] = d1.anywhere(name_e) or (d1.anywhere(name_v) if name_v else [])
        x["residue"], x["residue_ref"] = (residue_category(f, d1, blocks) if x["element"] is None else ("", ""))
        if x["element"] is None and x["candidates"]:
            x["residue"], x["residue_ref"] = "same name on several elements", ";".join(local(e) for e in x["candidates"])
        fields.append(x)

    # Graph.
    for h in heads:
        if h["section"] is None:
            continue
        s = h["section"]
        g.add((s, M11.templateHeading, Literal(h["title"])))
        g.add((s, M11.templatePage, Literal(h["page"], datatype=XSD.integer)))
        g.add((s, M11.templateOptional, Literal(h["optional"])))
        g.add((s, M11.templateConditional, Literal(h["conditional"])))
        if h["element"] is not None:
            g.add((s, M11.headingElement, h["element"]))
            g.add((s, M11.placeScope, Literal(h["scope"])))
    for x in fields:
        n = BNode(f"field{x['order']}")
        g.add((x["section_iri"], M11.hasTemplateField, n))
        g.add((n, RDF.type, M11.TemplateField))
        g.add((n, M11.fieldLabel, Literal(x["label"])))
        g.add((n, M11.fieldKind, KIND[x["kind"]]))
        g.add((n, M11.templateSectionNumber, Literal(x["section"])))
        g.add((n, M11.templatePage, Literal(x["page"], datatype=XSD.integer)))
        g.add((n, M11.templateOrder, Literal(x["order"], datatype=XSD.integer)))
        g.add((n, M11.templateOptional, Literal(x["optional"])))
        g.add((n, M11.templateConditional, Literal(x["conditional"])))
        if x["element"] is not None:
            g.add((n, M11.realises, x["element"]))
            g.add((n, M11.nameSource, Literal(x["source"])))
            g.add((n, M11.nameMatch, Literal(x["match"])))
            g.add((n, M11.placeScope, Literal(x["scope"])))
    relabel(g).serialize(ROOT / "m11-rdf.ttl", format="turtle")

    write_reports(tpl, heads, fields, d1)
    linked = [x for x in fields if x["element"] is not None]
    reached = {x["element"] for x in linked} | {h["element"] for h in heads if h["element"] is not None}
    print(len(numbered), "numbered headings;", len(fields), "fields;", len(linked), "realise an element;",
          len(reached), "of", len(d1.elements), "elements reached")


def write_reports(tpl, heads, fields, d1):
    REPORTS.mkdir(exist_ok=True)
    linked = [x for x in fields if x["element"] is not None]
    by_field = {x["element"] for x in linked}
    by_heading = {h["element"] for h in heads if h["element"] is not None}
    reached = by_field | by_heading
    rendered = [h for h in heads if h["section"] is not None]
    numbered_sections = {k for k in d1.sections if k[0].isdigit()}
    numbered = {h["number"] for h in rendered if h["number"][0].isdigit()}

    with open(REPORTS / "d5-fields.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["order", "page", "section_number", "section", "kind", "label", "optional", "conditional", "element",
                    "name_source", "name_match", "place_scope", "candidates", "residue_category"])
        for x in fields:
            w.writerow([x["order"], x["page"], x["section"], local(x["section_iri"]), x["kind"], x["label"],
                        str(x["optional"]).lower(), str(x["conditional"]).lower(),
                        local(x["element"]) if x["element"] is not None else "", x["source"] if x["element"] is not None else "",
                        x["match"] if x["element"] is not None else "", x["scope"] if x["element"] is not None else "",
                        ";".join(local(e) for e in x["candidates"]), x["residue"]])

    residue = []
    for x in fields:
        if x["element"] is None:
            residue.append(["field without an element", x["residue"], x["section"], x["page"], x["label"], x["residue_ref"]])
        if x["other"]:
            residue.append(["name only in another section (not linked)", "name only in another section", x["section"],
                            x["page"], x["label"], ";".join(local(e) for e in x["other"])])
        if x["element"] is not None and x["scope"] == "namespace":
            toc = "; ".join(sorted({p for _, _, _, _, p in d1.specs[x["element"]]}))
            residue.append(["field linked via namespace", "Template place differs from the TS ToC reference", x["section"],
                            x["page"], x["label"], f"{local(x['element'])} (TS ToC {toc})"])
    for h in heads:
        if h["element"] is not None and h["scope"] == "namespace":
            toc = "; ".join(sorted({p for _, _, _, _, p in d1.specs[h["element"]]}))
            residue.append(["heading linked via namespace", "Template place differs from the TS ToC reference", h["number"],
                            h["page"], h["title"], f"{local(h['element'])} (TS ToC {toc})"])
        if h["section"] is None:
            residue.append(["heading not rendered", "repeating heading without a C217272 term", h["number"], h["page"],
                            h["title"], ""])
    kinds = Counter()
    for x in linked:
        grp = kind_group(x, x["element"], d1)
        kinds[grp or "agree"] += 1
        if grp:
            residue.append(["kind differs from TS D/V/H", grp, x["section"], x["page"], x["label"],
                            f"{local(x['element'])} (D/V/H {', '.join(sorted({d for _, _, d, _, _ in d1.specs[x['element']]}))}; "
                            f"TS term {' | '.join(t for _, t, _, _, _ in d1.specs[x['element']])})"])
    in_residue = defaultdict(list)
    for r in residue:
        if r[0] == "field without an element":
            for e in re.findall(r"C\d+\.C\d+", r[5]):
                in_residue[e].append(r[1])
    for e in d1.elements:
        if e not in reached:
            cats = sorted(set(in_residue.get(local(e), [])))
            residue.append(["D1 element not reached", "only in residue: " + "; ".join(cats) if cats else "no Template field",
                            "", "", " | ".join(t for _, t, _, _, _ in d1.specs[e]), local(e)])
    with open(REPORTS / "d5-residue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["what", "category", "section_number", "page", "text", "detail"])
        w.writerows(residue)

    conf = Counter()
    for x in linked:
        t = ("blue" if x["optional"] else "black") + (" in {}" if x["conditional"] else "")
        conf[(t, "/".join(sorted({c for _, _, _, c, _ in d1.specs[x["element"]]})))] += 1

    def table(rows):
        return ["| What | Count |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in rows]

    tiers = Counter((x["source"], x["match"], x["scope"]) for x in linked)
    lines = ["# D5: ICH M11 Template", "",
             "Generated by `scripts/build_d5.py`. Do not edit by hand. Every count comes from the build.", "",
             f"Template PDF: {tpl['pdf_pages']} pages, protocol content pages {tpl['protocol_pages'][0]}–{tpl['protocol_pages'][1]}. "
             f"Read with PyMuPDF {tpl['pymupdf']} (MuPDF {tpl['mupdf']}).", "",
             "## Headings", ""]
    lines += table([
        ("headings", len(heads)),
        ("numbered headings with a C217272 section", len(numbered)),
        ("numbered C217272 sections without a Template heading", len(numbered_sections - numbered)),
        ("Amendment Details heading", sum(1 for h in rendered if h["number"] == "Amendment Details")),
        ("repeating headings not rendered", sum(1 for h in heads if h["section"] is None)),
        ("rendered headings optional (blue)", sum(h["optional"] for h in rendered)),
        ("rendered headings conditional", sum(h["conditional"] for h in rendered)),
        ("headings that are an element, same section", sum(1 for h in rendered if h["scope"] == "section")),
        ("headings that are an element, via namespace", sum(1 for h in rendered if h["scope"] == "namespace")),
        ("headings without an element", sum(1 for h in rendered if h["element"] is None)),
    ])
    lines += ["", "## Fields", ""]
    lines += table([("fields", len(fields))]
                   + [(f"fields, {name}", sum(1 for x in fields if x["kind"] == k)) for k, name in
                      (("insert", "text insertion point <...>"), ("pick", "controlled terminology [...]"))]
                   + [("fields optional (blue)", sum(x["optional"] for x in fields)),
                      ("fields conditional", sum(x["conditional"] for x in fields))]
                   + [(f"not fields: {k}", v) for k, v in tpl["excluded"].items()])
    lines += ["", "## Links to elements", ""]
    lines += table([(f"realises, {s} / {m} / {sc}", tiers[(s, m, sc)]) for s, m, sc in
                    [t for t in TIERS] + [("ts-heading-context", "exact", "section")] if tiers[(s, m, sc)]]
                   + [("fields that realise an element", len(linked)),
                      ("fields without an element", len(fields) - len(linked)),
                      ("elements reached by fields", len(by_field)),
                      ("elements reached by headings", len(by_heading)),
                      ("elements reached", len(reached)),
                      ("D1 elements", len(d1.elements)),
                      ("D1 elements not reached", len(d1.elements) - len(reached))])
    lines += ["", "## Field kind and TS D/V/H (fields that realise an element)", ""]
    lines += table(sorted(kinds.items()))
    lines += ["", "## Template optionality and TS conformance (fields that realise an element)", "",
              "| Template | TS conformance | Count |", "| --- | --- | --- |"]
    lines += [f"| {t} | {c} | {v} |" for (t, c), v in sorted(conf.items())]
    lines += ["", "## Residue (`d5-residue.csv`)", "", "| What | Category | Count |", "| --- | --- | --- |"]
    lines += [f"| {w} | {c} | {v} |" for (w, c), v in sorted(Counter((r[0], r[1]) for r in residue).items())]
    (REPORTS / "d5-template.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
