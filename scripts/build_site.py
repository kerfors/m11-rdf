"""Build the GitHub Pages site in docs/ from m11-rdf.ttl, vocabulary.ttl and m11-usdm.sssom.tsv.

The site follows the file split: the vocabulary first, then the instances
(elements, sections, code lists, Template) from m11-rdf.ttl, then the
mapping sets that point at these identifiers, each on a page of its own.

One page per minted IRI at its own path (<local name>/index.html): vocabulary
terms, elements, sections and code lists. Each page shows one IRI: its types,
what m11-rdf.ttl states about it (labels with the predicate's CURIE), and,
for elements, how many records of the mapping set point at it, with a link
to those rows. Indexes: vocabulary/ (terms by type), elements/, sections/,
code-lists/, template/ (the ICH M11 Template, D5, in Template order).

The mapping set m11-usdm.sssom.tsv as one table page (mappings/m11-usdm/,
scripts/mapping_view.py); each mapping record IRI (mapping/<source>/<row>)
as a forward to its row there. The rows of the two source mappings that did
not become a record, and the flagged records, from reports/d2-residue.csv
as one table page (mappings/m11-usdm/residue/). The M11 graph as Turtle, N-Triples, RDF/XML
and JSON-LD; the mapping set as SSSOM/TSV and SSSOM/RDF. The slides PDF
(rendered from site/slides/ by scripts/render_slides.py) in slides/, where
the folder URL forwards to it. docs/ is generated; do not edit by hand.
Fails if two page paths differ only by case.
"""
import csv
import html
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from urllib.parse import quote, unquote

import markdown

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

import mapping_view
from common import M11, NCIT, OBO, ROOT

USDM = "https://w3id.org/cdisc/usdm/v4/"
SOURCE_LABEL = {"hl7": "HL7 CSP IG ballot", "cdisc": "CDISC DDF-RA v4.0.0"}
SOURCE_SHORT = {"hl7": "HL7", "cdisc": "CDISC"}
MAPPING_FILES = ["m11-usdm.sssom.tsv", "m11-usdm.sssom.ttl"]
MAPPING_PAGE = "mappings/m11-usdm"
RESIDUE_PAGE = "mappings/m11-usdm/residue"
RESIDUE_WRAP = {"category", "element_name", "note", "flags", "elements", "section"}
PREFIXES = [("m11", M11), ("skos", SKOS), ("rdfs", RDFS), ("rdf", RDF), ("owl", OWL), ("dcterms", DCTERMS)]
CLASS_INDEX = {"Element": "elements", "Section": "sections", "CodeList": "code-lists", "Namespace": "code-lists",
               "ValueCodeList": "code-lists", "TemplateField": "template"}
BNODE_SHOWN = {"Specification": 'on the element pages (table "Specifications in the Technical Specification")',
               "TemplateField": 'on the section pages and the <a href="../template/">Template</a> page'}

DOCS = ROOT / "docs"
REPO = "https://github.com/kerfors/m11-rdf"
READING_PAGES = {"d4-skeleton", "slides", "template"}
SLIDES_PDF = "ich-m11-elements-mapping-target.pdf"
TEMPLATE_URL = "https://database.ich.org/sites/default/files/ICH_Step4_M11_Final_Template_2025_1119.pdf"
KIND_SIGN = {"TextInsertion": "&lt;…&gt;", "ControlledTerminology": "[…]"}
CSS = """
:root { --bg: #ffffff; --fg: #1d1d1f; --muted: #5f6368; --line: #dadce0; --link: #1a5fb4; --code: #f3f4f6; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #16181c; --fg: #e8eaed; --muted: #9aa0a6; --line: #3c4043; --link: #8ab4f8; --code: #23262b; }
}
:root[data-theme="dark"] { --bg: #16181c; --fg: #e8eaed; --muted: #9aa0a6; --line: #3c4043; --link: #8ab4f8; --code: #23262b; }
body { background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; }
main { max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
a { color: var(--link); }
nav { font-size: 0.9rem; color: var(--muted); margin-bottom: 1rem; }
h1 { font-size: 1.6rem; margin: 0.2rem 0 0.4rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid var(--line); padding-bottom: 0.2rem; }
.iri, code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88rem; background: var(--code); padding: 0.05rem 0.3rem; border-radius: 3px; overflow-wrap: anywhere; }
.muted { color: var(--muted); font-size: 0.9rem; }
dl { display: grid; grid-template-columns: minmax(9rem, max-content) 1fr; gap: 0.3rem 1rem; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border-bottom: 1px solid var(--line); padding: 0.35rem 0.5rem; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
ul.tree { list-style: none; padding-left: 1.2rem; }
ul.tree > li { margin: 0.15rem 0; }
@media (max-width: 600px) { dl { grid-template-columns: 1fr; gap: 0.1rem; } dt { margin-top: 0.6rem; } }
.draft { border-left: 3px solid var(--muted); padding: 0.3rem 0.8rem; color: var(--muted); font-size: 0.9rem; }
.curie { display: block; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.75rem; font-weight: normal; color: var(--muted); }
.curie a { color: var(--muted); }
td.nw code { white-space: nowrap; overflow-wrap: normal; }
"""


def esc(x):
    return html.escape(str(x))


def local(iri):
    return str(iri)[len(str(M11)):]


def link(iri, g, depth=1):
    """Link to a minted IRI's page (relative), labelled with its prefLabel or rdfs:label."""
    label = g.value(iri, SKOS.prefLabel) or g.value(iri, RDFS.label) or local(iri)
    return f'<a href="{"../" * depth}{esc(local(iri))}/">{esc(label)}</a>'


def curie(iri, depth=1):
    """The IRI as a CURIE; m11 terms linked to their page."""
    for prefix, ns in PREFIXES:
        if str(iri).startswith(str(ns)) and str(iri) != str(ns):
            name = str(iri)[len(str(ns)):]
            if prefix == "m11":
                return f'<a href="{"../" * depth}{esc(name)}/">m11:{esc(name)}</a>'
            return f"{prefix}:{esc(name)}"
    return esc(iri)


def dt(label, preds, depth=1):
    """A field label with the CURIE(s) of the predicate(s) it shows."""
    return f'<dt>{label}<span class="curie">{" ".join(curie(p, depth) for p in preds)}</span></dt>'


def th(label, preds, depth=1):
    return f'<th>{label}<span class="curie">{" ".join(curie(p, depth) for p in preds)}</span></th>'


def types_html(g, s, depth=1):
    return " ".join(curie(t, depth) for t in sorted(g.objects(s, RDF.type), key=str))


def page(title, body, depth=1, iri=None, kind=None, alternate="m11-rdf.ttl", css=""):
    up = "../" * depth
    head_iri = (f'<p><span class="iri">{esc(iri)}</span>' + (f' <span class="muted">a</span> {kind}' if kind else "") + "</p>") if iri else ""
    alt = f'<link rel="alternate" type="text/turtle" href="{up}{alternate}">'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · m11-rdf</title>
{alt}
<style>{CSS}{css}</style>
</head>
<body>
<main>
<nav><a href="{up}">m11-rdf</a> · <a href="{up}vocabulary/">vocabulary</a> · <a href="{up}elements/">elements</a> · <a href="{up}sections/">sections</a> · <a href="{up}code-lists/">code lists</a> · <a href="{up}template/">template</a> · <a href="{up}{MAPPING_PAGE}/">mapping set</a> · <a href="{up}slides/">slides</a> · <a href="{REPO}">GitHub repository</a></nav>
<h1>{esc(title)}</h1>
{head_iri}
{body}
<p class="draft">Draft, not normative. A derived rendering of the ICH M11 Technical Specification, Template, code lists and OID Listing (© ICH, used under the ICH Legal Mentions) and of the ICH M11 Terminology published by NCI EVS (CC BY 4.0). Not an ICH, CDISC or HL7 artifact, and not endorsed or sponsored by ICH.</p>
</main>
</body>
</html>
"""


def ncit_links(g, s):
    out = []
    for o in sorted(g.objects(s, M11.concept), key=str):
        if str(o).startswith(str(OBO)):
            out.append(f'<a href="{esc(o)}">{esc(str(o)[len(str(OBO)):])}</a> (OBO PURL)')
        elif str(o).startswith(str(NCIT)):
            out.append(f'<span class="iri">{esc(o)}</span> (EVS identifier)')
    return "<br>".join(out)


def evs_twin(g, s):
    t = g.value(s, SKOS.exactMatch)
    return f'<span class="iri">{esc(t)}</span> <span class="muted">(EVS term IRI; does not resolve)</span>' if t else "none"


def stable_bnodes(g):
    """Copy of g with blank nodes labelled spec<TS block> and field<Template order> (parsing assigns random labels)."""
    label = {s: BNode(f"spec{g.value(s, M11.tsBlock)}") for s in g.subjects(RDF.type, M11.Specification)}
    label.update({f: BNode(f"field{g.value(f, M11.templateOrder)}") for f in g.subjects(RDF.type, M11.TemplateField)})
    if len(set(label.values())) != len(label) or any(isinstance(x, BNode) and x not in label for t in g for x in t):
        raise RuntimeError("Blank nodes other than one per specification and one per Template field, or two with one label")
    out = Graph()
    for prefix, ns in g.namespaces():
        out.bind(prefix, ns)
    triples = [(label.get(s, s), p, label.get(o, o)) for s, p, o in g]
    for t in sorted(triples, key=lambda t: tuple(x.n3() for x in t)):
        out.add(t)
    return out


def write(rel, text):
    path = DOCS / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    g = Graph().parse(ROOT / "m11-rdf.ttl")
    set_meta, _, set_rows = mapping_view.read_sssom_tsv(ROOT / "m11-usdm.sssom.tsv")
    elements = sorted(g.subjects(RDF.type, M11.Element), key=str)
    sections = sorted(g.subjects(RDF.type, M11.Section), key=str)
    namespaces = sorted(g.subjects(RDF.type, M11.Namespace), key=lambda n: int(str(g.value(n, SKOS.notation)).rsplit(".", 1)[1]))
    value_lists = sorted(g.subjects(RDF.type, M11.ValueCodeList), key=lambda n: int(str(g.value(n, SKOS.notation)).rsplit(".", 1)[1]))
    vocab = Graph().parse(ROOT / "vocabulary.ttl")
    terms = sorted({s for s in vocab.subjects() if isinstance(s, URIRef) and str(s).startswith(str(M11)) and local(s)}, key=str)

    # Mapping records from the TSV: (record IRI, source, row, element).
    curie_map = set_meta["curie_map"]
    records = []
    for r in set_rows:
        iri = URIRef(mapping_view.expand(r["record_id"], curie_map))
        _, src, row = local(iri).split("/")
        records.append((iri, src, row, URIRef(mapping_view.expand(r["subject_id"], curie_map))))
    records.sort(key=lambda x: (list(SOURCE_LABEL).index(x[1]), int(x[2])))
    records_by_element = defaultdict(list)
    for x in records:
        records_by_element[x[3]].append(x)
    if not set(records_by_element) <= set(elements):
        raise RuntimeError("Mapping records whose subject_id is not an element of m11-rdf.ttl")

    paths = [local(x) for x in elements + sections + namespaces + value_lists + terms] + [local(x[0]) for x in records]
    paths += ["elements", "sections", "code-lists", "vocabulary", "mappings"] + sorted(READING_PAGES)
    seen = defaultdict(list)
    for p in paths:
        seen[p.lower()].append(p)
    clash = [v for v in seen.values() if len(v) > 1]
    if clash:
        raise RuntimeError(f"Page paths differ only by case: {clash}")

    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir()
    (DOCS / ".nojekyll").write_text("")
    shutil.copyfile(ROOT / "m11-rdf.ttl", DOCS / "m11-rdf.ttl")
    for f in MAPPING_FILES:
        shutil.copyfile(ROOT / f, DOCS / f)
    stable = stable_bnodes(g)
    nt = stable.serialize(format="nt", encoding="utf-8").decode("utf-8")
    (DOCS / "m11-rdf.nt").write_text("\n".join(sorted(l for l in nt.split("\n") if l)) + "\n", encoding="utf-8")
    # rdflib writes RDF/XML and JSON-LD in an order that follows Python's per-run string hashing;
    # a child process with a fixed hash seed makes the files byte-stable between builds.
    for fmt, ext in [("xml", "rdf"), ("json-ld", "jsonld")]:
        subprocess.run([sys.executable, __file__, "--serialize", fmt, str(DOCS / "m11-rdf.nt"), str(DOCS / f"m11-rdf.{ext}")],
                       check=True, env={**os.environ, "PYTHONHASHSEED": "0"})

    specs_by_section = defaultdict(list)
    specs_by_codelist = defaultdict(list)
    for e in elements:
        for s in g.objects(e, M11.hasSpecification):
            specs_by_section[g.value(s, M11.inSection)].append((e, s))
            for cl in g.objects(s, M11.hasValueCodeList):
                specs_by_codelist[cl].append((e, s))
    narrower = defaultdict(list)
    for s in sections:
        b = g.value(s, SKOS.broader)
        if b:
            narrower[b].append(s)

    def section_sort(s):
        n = g.value(s, M11.sectionNumber)
        return [int(p) for p in str(n).split(".")] if n else [999, str(g.value(s, SKOS.prefLabel))]

    # Template (D5): fields by section and by element; sections whose heading is an element.
    fields = sorted(g.subjects(RDF.type, M11.TemplateField), key=lambda n: int(g.value(n, M11.templateOrder)))
    fields_by_section = defaultdict(list)
    fields_by_element = defaultdict(list)
    for n in fields:
        fields_by_section[g.value(predicate=M11.hasTemplateField, object=n)].append(n)
        if g.value(n, M11.realises) is not None:
            fields_by_element[g.value(n, M11.realises)].append(n)
    heading_of = defaultdict(list)
    for sec, el in g.subject_objects(M11.headingElement):
        heading_of[el].append(sec)

    def bracketed(n):
        lab = esc(g.value(n, M11.fieldLabel))
        return f"&lt;{lab}&gt;" if g.value(n, M11.fieldKind) == M11.TextInsertion else f"[{lab}]"

    def flags(x):
        out = [w for p, w in ((M11.templateOptional, "optional"), (M11.templateConditional, "conditional"))
               if g.value(x, p) is not None and g.value(x, p).toPython()]
        return ", ".join(out)

    def pdf_page(x, depth=1):
        p = g.value(x, M11.templatePage)
        return f'<a href="{TEMPLATE_URL}#page={esc(p)}">p. {esc(p)}</a>'

    def basis(n):
        return f'{esc(g.value(n, M11.nameSource))} / {esc(g.value(n, M11.nameMatch))} / {esc(g.value(n, M11.placeScope))}'

    def field_table(ns, depth=1):
        rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in [
            f"<code>{bracketed(n)}</code>",
            esc(flags(n)),
            pdf_page(n),
            link(g.value(n, M11.realises), g, depth) if g.value(n, M11.realises) is not None else '<span class="muted">none</span>',
            f'<span class="muted">{basis(n)}</span>' if g.value(n, M11.realises) is not None else "",
        ]) + "</tr>" for n in ns)
        return (f'<div class="table-wrap"><table><tr>{th("Field", [M11.fieldLabel, M11.fieldKind])}{th("Template", [M11.templateOptional, M11.templateConditional])}'
                f'{th("Page", [M11.templatePage])}{th("Realises", [M11.realises])}{th("Linked by", [M11.nameSource, M11.nameMatch, M11.placeScope])}</tr>{rows}</table></div>')

    def template_part(s, depth=1):
        heading = g.value(s, M11.templateHeading)
        out = "<h2>In the ICH M11 Template</h2>"
        if heading is not None:
            el = g.value(s, M11.headingElement)
            out += f"""<dl>
{dt("Heading", [M11.templateHeading], depth)}<dd>{esc(heading)} <span class="muted">{esc(flags(s))}</span></dd>
{dt("Page", [M11.templatePage], depth)}<dd>{pdf_page(s)}</dd>
{f'{dt("Heading is", [M11.headingElement, M11.placeScope], depth)}<dd>{link(el, g, depth)} <span class="muted">(TS term, {esc(g.value(s, M11.placeScope))})</span></dd>' if el is not None else ''}
</dl>"""
        elif fields_by_section.get(s):
            out += '<p class="muted">No heading of its own in the Template.</p>'
        else:
            return ""
        if fields_by_section.get(s):
            out += field_table(fields_by_section[s], depth)
        return out

    def element_template(e):
        hs = sorted(heading_of.get(e, []), key=section_sort)
        fs = fields_by_element.get(e, [])
        if not hs and not fs:
            return '<h2>In the ICH M11 Template</h2><p class="muted">No Template heading or field is linked to this element.</p>'
        out = "<h2>In the ICH M11 Template</h2>"
        if hs:
            out += "<p>The Template heading of " + ", ".join(link(x, g) for x in hs) + f' is this element <span class="muted">({curie(M11.headingElement)})</span>.</p>'
        if fs:
            rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in [
                link(g.value(predicate=M11.hasTemplateField, object=n), g) + f' <span class="muted">{esc(g.value(n, M11.templateSectionNumber))}</span>',
                f"<code>{bracketed(n)}</code>",
                esc(flags(n)),
                pdf_page(n),
                f'<span class="muted">{basis(n)}</span>',
            ]) + "</tr>" for n in fs)
            out += (f'<div class="table-wrap"><table><tr>{th("Section", [M11.hasTemplateField, M11.templateSectionNumber])}{th("Field", [M11.fieldLabel, M11.fieldKind])}'
                    f'{th("Template", [M11.templateOptional, M11.templateConditional])}{th("Page", [M11.templatePage])}'
                    f'{th("Linked by", [M11.nameSource, M11.nameMatch, M11.placeScope])}</tr>{rows}</table></div>')
        return out

    # Elements.
    for e in elements:
        rows = []
        for s in sorted(g.objects(e, M11.hasSpecification), key=lambda s: int(g.value(s, M11.tsBlock))):
            cls = ", ".join(f'{link(c, g)} <span class="muted">{esc(g.value(c, SKOS.notation))}</span>'
                            for c in g.objects(s, M11.hasValueCodeList))
            stated = ", ".join(esc(o) for o in g.objects(s, M11.statedCodeListOid))
            rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in [
                esc(g.value(s, M11.tsBlock)),
                esc(g.value(s, M11.tsTerm)),
                link(g.value(s, M11.inSection), g) + (f'<br><span class="muted">{esc(g.value(s, M11.repeatPattern))}</span>' if g.value(s, M11.repeatPattern) else ""),
                esc(g.value(s, M11.conformance)),
                esc(g.value(s, M11.cardinality)),
                esc(g.value(s, M11.dataType)) + f' <span class="muted">({esc(g.value(s, M11.dvh))})</span>',
                cls + (f'<br><span class="muted">OID as stated in the TS: {stated}</span>' if stated else ""),
                esc(g.value(s, M11.repeatReuse)),
            ]) + "</tr>")
        mine = records_by_element.get(e, [])
        if mine:
            per_source = ", ".join(f"{SOURCE_SHORT[k]} {sum(1 for x in mine if x[1] == k)}" for k in SOURCE_LABEL if any(x[1] == k for x in mine))
            pointed = (f'<code>m11-usdm.sssom.tsv</code>: {len(mine)} mapping record{"s" if len(mine) > 1 else ""} ({per_source}) · '
                       f'<a href="../{MAPPING_PAGE}/?subject_id={quote("m11:" + local(e), safe=":")}">see the rows</a>')
        else:
            pointed = '<code>m11-usdm.sssom.tsv</code>: no records'
        mappings = f"""<h2>Pointed at by other files</h2>
<p class="muted">Statements in separate files that use this element's IRI.</p>
<p>{pointed}</p>"""
        alts = ", ".join(esc(a) for a in g.objects(e, SKOS.altLabel))
        definition = g.value(e, SKOS.definition)
        body = f"""
<dl>
{dt("Definition", [SKOS.definition])}<dd>{esc(definition) if definition else '<span class="muted">none (no EVS term for this pair)</span>'}</dd>
{f'{dt("Synonyms", [SKOS.altLabel])}<dd>{alts}</dd>' if alts else ''}
{dt("Namespace", [SKOS.inScheme])}<dd>{link(g.value(e, SKOS.inScheme), g)}</dd>
{dt("ICH pair", [M11.ichNamespaceOid, M11.ichConceptCode, M11.pairBasis])}<dd><code>{esc(g.value(e, M11.ichNamespaceOid))}</code> + <code>{esc(g.value(e, M11.ichConceptCode))}</code> <span class="muted">({esc(g.value(g.value(e, M11.pairBasis), RDFS.label))})</span></dd>
{dt("NCIt concept", [M11.concept])}<dd>{ncit_links(g, e)}</dd>
{dt("EVS term", [SKOS.exactMatch])}<dd>{evs_twin(g, e)}</dd>
{dt("Label from", [M11.labelSource])}<dd>{esc(g.value(g.value(e, M11.labelSource), RDFS.label))}</dd>
</dl>
<h2>Specifications in the Technical Specification</h2>
<p class="muted">One row per component block of Appendix 1 that names this element (<a href="../Specification/">m11:Specification</a>, via {curie(M11.hasSpecification)}). Text as printed.</p>
<div class="table-wrap"><table>
<tr>{th("Block", [M11.tsBlock])}{th("Term", [M11.tsTerm])}{th("Section", [M11.inSection])}{th("Conformance", [M11.conformance])}{th("Cardinality", [M11.cardinality])}{th("Data type", [M11.dataType, M11.dvh])}{th("Value code list", [M11.hasValueCodeList])}{th("Repeating / reuse", [M11.repeatReuse])}</tr>
{''.join(rows)}
</table></div>
{element_template(e)}
{mappings}
"""
        write(f"{local(e)}/index.html", page(str(g.value(e, SKOS.prefLabel)), body, iri=e, kind=types_html(g, e)))

    # Mapping records: a forward to the row in the mapping set table.
    for r, src, row, e in records:
        to = f"../../../{MAPPING_PAGE}/#{src}-{row}"
        write(f"{local(r)}/index.html", f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={esc(to)}">
<link rel="alternate" type="text/turtle" href="../../../m11-usdm.sssom.ttl">
<title>Mapping record {esc(src)} row {esc(row)} · m11-rdf</title></head>
<body><p>Mapping record <span class="iri">{esc(r)}</span>: {esc(SOURCE_LABEL[src])}, row {esc(row)}, <a href="{esc(to)}">in the mapping set m11-usdm.sssom.tsv</a>. Subject: <a href="../../../{esc(local(e))}/">{esc(g.value(e, SKOS.prefLabel))}</a>.</p></body></html>
""")

    # The mapping set: one table page.
    residue = list(csv.DictReader(open(ROOT / "reports" / "d2-residue.csv", encoding="utf-8")))
    no_record = [r for r in residue if r["status"] == "residue"]
    flagged = [r for r in residue if r["status"] == "statement"]
    if len(no_record) + len(flagged) != len(residue):
        raise RuntimeError("d2-residue.csv: a status other than residue or statement")
    if {(r["source"], r["row"]) for r in flagged} - {(x[1], x[2]) for x in records}:
        raise RuntimeError("d2-residue.csv: a flagged statement without its record")
    set_title, set_body = mapping_view.render(
        ROOT / "m11-usdm.sssom.tsv", [(f, f"../../{f}") for f in MAPPING_FILES],
        notes=f'<p>Rows of the two source mappings that did not become a record ({len(no_record)}), and {len(flagged)} flagged records: <a href="residue/">rows without a record</a>.</p>')
    write(f"{MAPPING_PAGE}/index.html", page(set_title, set_body, depth=2, iri=set_meta["mapping_set_id"],
                                             alternate="m11-usdm.sssom.ttl", css=mapping_view.CSS))

    # Rows without a record, and flagged records: one table page from reports/d2-residue.csv.
    res_cols = list(residue[0])
    by_cat = defaultdict(lambda: defaultdict(int))
    for r in residue:
        by_cat[r["category"]][r["source"]] += 1
    cat_rows = "".join(f"<tr><td>{esc(c)}</td>" + "".join(f"<td>{by_cat[c][k]}</td>" for k in SOURCE_LABEL) + "</tr>"
                       for c in sorted(by_cat))
    cat_rows += "<tr><th>Total</th>" + "".join(f"<th>{sum(1 for r in residue if r['source'] == k)}</th>" for k in SOURCE_LABEL) + "</tr>"

    def res_cell(c, r):
        cls = ' class="wrap"' if c in RESIDUE_WRAP else ""
        v = r[c]
        if c == "row" and r["status"] == "statement":
            return f'<td{cls}><a href="../#{esc(r["source"])}-{esc(v)}">{esc(v)}</a></td>'
        if c == "elements" and v:
            return f"<td{cls}>" + "; ".join(f'<a href="../../../{esc(x)}/">{esc(x)}</a>' for x in v.split(";")) + "</td>"
        return f"<td{cls}>{esc(v)}</td>"
    res_body = "".join("<tr>" + "".join(res_cell(c, r) for c in res_cols) + "</tr>\n" for r in residue)
    write(f"{RESIDUE_PAGE}/index.html", page("m11-usdm: rows without a record, and flagged records", f"""
<p>Rows of the two source mappings ({", ".join(esc(v) for v in SOURCE_LABEL.values())}) that did not become a record in the <a href="../">mapping set m11-usdm.sssom.tsv</a>: {len(no_record)} rows (HL7 {sum(1 for r in no_record if r["source"] == "hl7")}, CDISC {sum(1 for r in no_record if r["source"] == "cdisc")}). Either the row could not be tied to one ICH M11 element by its NCIt Code or its element name, or its USDM class and attribute do not resolve in usdm-rdf. Also listed: {len(flagged)} rows that did become records but are flagged; their row number links to the record.</p>
<p>As reported by <code>scripts/build_d2.py</code> in <a href="{REPO}/blob/main/reports/d2-residue.csv">reports/d2-residue.csv</a>, cells as given in the source row. Nothing is repaired here. <code>elements</code> lists the candidate elements where there were several, or the one identified.</p>
<h2>By category</h2>
<div class="table-wrap"><table><tr><th>category</th>{"".join(f"<th>{esc(SOURCE_SHORT[k])}</th>" for k in SOURCE_LABEL)}</tr>{cat_rows}</table></div>
<h2>Rows</h2>
<p class="muted">Click a column name to sort. Typing filters on any cell.</p>
<p id="exact"></p>
<p class="filter"><label>Filter <input id="filter" type="search"></label> <span id="count" class="muted">{len(residue)} rows</span></p>
<div class="table-wrap"><table id="records">
<thead><tr>{"".join(f'<th data-col="{esc(c)}">{esc(c)}</th>' for c in res_cols)}</tr></thead>
<tbody>
{res_body}</tbody>
</table></div>
{mapping_view.SCRIPT}""", depth=3, css=mapping_view.CSS))

    # Sections.
    for s in sections:
        num = g.value(s, M11.sectionNumber)
        here = sorted(specs_by_section.get(s, []), key=lambda es: int(g.value(es[1], M11.tsBlock)))
        el_rows = "".join(f"<tr><td>{link(e, g)}</td><td><code>{esc(local(e))}</code></td><td>{esc(g.value(sp, M11.conformance))}</td><td>{esc(g.value(sp, M11.tsBlock))}</td></tr>"
                          for e, sp in here)
        el_head = f'<tr><th>Element</th><th>IRI</th>{th("Conformance", [M11.conformance])}{th("TS block", [M11.tsBlock])}</tr>'

        kids = "".join(f"<li>{link(k, g)}</li>" for k in sorted(narrower.get(s, []), key=section_sort))
        ns = [n for n in namespaces if g.value(n, M11.forSection) == s]
        body = f"""
<dl>
{dt("Definition", [SKOS.definition])}<dd>{esc(g.value(s, SKOS.definition))}</dd>
{dt("Section number", [M11.sectionNumber])}<dd>{esc(num) if num else '<span class="muted">none</span>'}</dd>
{dt("Broader", [SKOS.broader])}<dd>{link(g.value(s, SKOS.broader), g) if g.value(s, SKOS.broader) else '<span class="muted">top level</span>'}</dd>
{f'{dt("Namespace", [M11.forSection])}<dd>{link(ns[0], g)} <span class="muted">(the namespace states it is for this section)</span></dd>' if ns else ''}
{dt("NCIt concept", [M11.concept])}<dd>{ncit_links(g, s)}</dd>
{dt("EVS term", [SKOS.exactMatch])}<dd>{evs_twin(g, s)}</dd>
</dl>
{f'<h2>Subsections</h2><p class="muted">Sections whose {curie(SKOS.broader)} is this one.</p><ul class="tree">{kids}</ul>' if kids else ''}
<h2>Elements specified in this section</h2>
{f'<p class="muted">Element specifications whose {curie(M11.inSection)} is this section.</p><div class="table-wrap"><table>{el_head}{el_rows}</table></div>' if el_rows else '<p class="muted">None.</p>'}
{template_part(s)}
"""
        write(f"{local(s)}/index.html", page(str(g.value(s, SKOS.prefLabel)), body, iri=s, kind=types_html(g, s)))

    # Code lists.
    for c in namespaces + value_lists:
        is_ns = (c, RDF.type, M11.Namespace) in g
        if is_ns:
            members = sorted(g.subjects(SKOS.inScheme, c), key=str)
            listing = "".join(f"<tr><td>{link(e, g)}</td><td><code>{esc(local(e))}</code></td></tr>" for e in members)
            extra = f'<h2>Elements ({len(members)})</h2><p class="muted">Elements whose {curie(SKOS.inScheme)} is this namespace.</p><div class="table-wrap"><table><tr><th>Element</th><th>IRI</th></tr>{listing}</table></div>'
        else:
            users = specs_by_codelist.get(c, [])
            listing = "".join(f"<tr><td>{link(e, g)}</td><td>{esc(g.value(sp, M11.tsBlock))}</td></tr>" for e, sp in users)
            extra = (f'<h2>Used by</h2><p class="muted">Element specifications whose {curie(M11.hasValueCodeList)} is this code list.</p><div class="table-wrap"><table><tr><th>Element</th><th>TS block</th></tr>{listing}</table></div>'
                     if listing else '<h2>Used by</h2><p class="muted">No element block names this code list.</p>')
            extra += '<p class="muted">The values of this code list are not rendered in this release.</p>'
        body = f"""
<dl>
{dt("Kind", [RDF.type])}<dd>{'Namespace (section code list)' if is_ns else 'Value code list'}</dd>
{dt("ICH OID", [SKOS.notation])}<dd><code>{esc(g.value(c, SKOS.notation))}</code> <span class="muted">(OID Listing, 2025-10-16)</span></dd>
{dt("Definition", [SKOS.definition])}<dd>{esc(g.value(c, SKOS.definition) or '')}</dd>
{f'{dt("Section", [M11.forSection])}<dd>{link(g.value(c, M11.forSection), g)}</dd>' if is_ns else ''}
{dt("NCIt concept", [M11.concept])}<dd>{ncit_links(g, c)}</dd>
{dt("EVS code list", [SKOS.exactMatch])}<dd>{evs_twin(g, c)}</dd>
</dl>
{extra}
"""
        write(f"{local(c)}/index.html", page(str(g.value(c, SKOS.prefLabel)), body, iri=c, kind=types_html(g, c)))

    # Vocabulary terms.
    groups = [("Classes", OWL.Class), ("Object properties", OWL.ObjectProperty), ("Datatype properties", OWL.DatatypeProperty),
              ("Annotation properties", OWL.AnnotationProperty), ("Datatypes", RDFS.Datatype), ("Values", None)]
    group_of = {}
    for t in terms:
        hit = [name for name, k in groups if k is not None and (t, RDF.type, k) in vocab]
        if not hit and all(str(k).startswith(str(M11)) for k in vocab.objects(t, RDF.type)) and any(vocab.objects(t, RDF.type)):
            hit = ["Values"]
        if len(hit) != 1:
            raise RuntimeError(f"Vocabulary term {t} is in {len(hit)} groups")
        group_of[t] = hit[0]
    annotation = [t for t in terms if group_of[t] == "Annotation properties"]
    in_set = {URIRef(mapping_view.expand(r["predicate_id"], curie_map)) for r in set_rows}
    in_set |= {URIRef(mapping_view.expand(d["property"], curie_map)) for d in set_meta["extension_definitions"]}
    if any((None, t, None) in g for t in annotation) or not set(annotation) <= in_set:
        raise RuntimeError("An annotation property is used in m11-rdf.ttl, or not used by the mapping set")

    vocab_rows = defaultdict(list)
    for t in terms:
        dom, rng = vocab.value(t, RDFS.domain), vocab.value(t, RDFS.range)
        sup = vocab.value(t, RDFS.subClassOf)
        subs = sorted(vocab.subjects(RDFS.subClassOf, t), key=str)

        def ref(x):
            if x is None:
                return ""
            if str(x).startswith(str(M11)):
                return link(x, vocab)
            return f'<span class="iri">{esc(x)}</span>'
        instances = ""
        if group_of[t] == "Classes":
            members = sorted(g.subjects(RDF.type, t), key=str)
            if not members:
                shown = '<span class="muted">none directly; see the subclasses</span>' if subs else '<span class="muted">none</span>'
            elif all(isinstance(x, BNode) for x in members):
                shown = f"{len(members)} blank nodes, no page of their own; shown {BNODE_SHOWN[local(t)]}"
            elif local(t) in CLASS_INDEX:
                shown = f'<a href="../{CLASS_INDEX[local(t)]}/">{len(members)}</a>'
            else:
                shown = ", ".join(link(x, g) for x in members)
            instances = f"{dt('Instances', [RDF.type])}<dd>{shown}</dd>"
        body = f"""
<dl>
{dt("Type", [RDF.type])}<dd>{types_html(vocab, t)}</dd>
{dt("Description", [RDFS.comment])}<dd>{esc(vocab.value(t, RDFS.comment) or '')}</dd>
{f'{dt("Subclass of", [RDFS.subClassOf])}<dd>{ref(sup)}</dd>' if sup else ''}
{f'{dt("Subclasses", [RDFS.subClassOf])}<dd>{", ".join(ref(x) for x in subs)}</dd>' if subs else ''}
{f'{dt("Domain", [RDFS.domain])}<dd>{ref(dom)}</dd>' if dom else ''}
{f'{dt("Range", [RDFS.range])}<dd>{ref(rng)}</dd>' if rng else ''}
{instances}
</dl>
{'<p class="muted">Used by the mapping set <a href="../' + MAPPING_PAGE + '/">m11-usdm.sssom.tsv</a> (predicate or extension slot); not used by any statement in m11-rdf.ttl.</p>' if t in annotation else ''}
"""
        write(f"{local(t)}/index.html", page(str(vocab.value(t, RDFS.label)), body, iri=t))
        vocab_rows[group_of[t]].append(f"<tr><td>{link(t, vocab)}</td><td class=\"nw\"><code>m11:{esc(local(t))}</code></td><td>{esc(vocab.value(t, RDFS.comment) or '')}</td></tr>")
    group_note = {
        "Classes": "Kinds of things. Each class page links to its instances.",
        "Values": "Fixed values, each an instance of one of the classes above.",
        "Annotation properties": f'Used by the mapping set <a href="../{MAPPING_PAGE}/">m11-usdm.sssom.tsv</a> (its predicate and extension slots); no statement in m11-rdf.ttl uses them.',
    }
    vocab_body = (f'<p>The terms m11-rdf defines, from <a href="{REPO}/blob/main/vocabulary.ttl">vocabulary.ttl</a> (also merged into m11-rdf.ttl). '
                  'Other terms on these pages come from SKOS, RDFS, RDF, OWL and Dublin Core. Grouped by type (<code>rdf:type</code>).</p>')
    for name, _ in groups:
        vocab_body += (f'<h2>{name} ({len(vocab_rows[name])})</h2>' + (f'<p class="muted">{group_note[name]}</p>' if name in group_note else "")
                       + f'<div class="table-wrap"><table><tr><th>Term</th><th>Name</th><th>Description</th></tr>{"".join(vocab_rows[name])}</table></div>')
    write("vocabulary/index.html", page("Vocabulary", vocab_body))

    # Element index.
    ns_order = {n: i for i, n in enumerate(namespaces)}
    el_index = sorted(elements, key=lambda e: (ns_order[g.value(e, SKOS.inScheme)], str(e)))
    el_rows = "".join(
        f'<tr><td>{link(e, g)}</td><td class="nw"><code>{esc(local(e))}</code></td><td>{link(g.value(e, SKOS.inScheme), g)}</td><td>'
        + ", ".join(link(x, g) for x in sorted({g.value(sp, M11.inSection) for sp in g.objects(e, M11.hasSpecification)}, key=section_sort))
        + "</td></tr>" for e in el_index)
    write("elements/index.html", page("Elements", f"""
<p>The {len(elements)} ICH M11 protocol elements (<a href="../Element/">m11:Element</a>), by namespace. An element is a concept within a namespace, as the Technical Specification states it; its IRI is <code>&lt;namespace code list&gt;.&lt;concept code&gt;</code>.</p>
<div class="table-wrap"><table><tr><th>Element</th><th>IRI</th>{th("Namespace", [SKOS.inScheme])}{th("Specified in section", [M11.hasSpecification, M11.inSection])}</tr>{el_rows}</table></div>
"""))

    # Section tree and code list index.
    def tree(nodes):
        return '<ul class="tree">' + "".join(
            f"<li>{link(n, g)} <span class=\"muted\">({len(specs_by_section.get(n, []))})</span>{tree(sorted(narrower[n], key=section_sort)) if narrower.get(n) else ''}</li>"
            for n in nodes) + "</ul>"
    roots = sorted([s for s in sections if not g.value(s, SKOS.broader)], key=section_sort)
    write("sections/index.html", page("Sections", '<p class="muted">The ICH M11 sections (code list C217272), in number order. In brackets: element specifications in the section itself.</p>' + tree(roots)))
    cl_rows = "".join(f"<tr><td>{link(c, g)}</td><td><code>{esc(local(c))}</code></td><td><code>{esc(g.value(c, SKOS.notation))}</code></td><td>{'namespace' if (c, RDF.type, M11.Namespace) in g else 'values'}</td></tr>"
                      for c in namespaces + value_lists)
    write("code-lists/index.html", page("Code lists", f'<div class="table-wrap"><table><tr><th>Code list</th><th>Code</th><th>ICH OID</th><th>Kind</th></tr>{cl_rows}</table></div>'))

    # The Template in Template order: Title Page (fields, no heading), then sections by heading page and number.
    in_template = [s for s in sections if g.value(s, M11.templateHeading) is not None or fields_by_section.get(s)]
    in_template.sort(key=lambda s: (int(g.value(s, M11.templatePage)) if g.value(s, M11.templatePage) is not None
                                    else min(int(g.value(n, M11.templatePage)) for n in fields_by_section[s]), section_sort(s)))
    parts = []
    for s in in_template:
        num = g.value(s, M11.sectionNumber)
        heading = g.value(s, M11.templateHeading)
        title = f"{esc(num)} " if num else ""
        title += esc(heading if heading is not None else g.value(s, SKOS.prefLabel))
        el = g.value(s, M11.headingElement)
        meta = [pdf_page(s)] if heading is not None else []
        if flags(s):
            meta.append(esc(flags(s)))
        if el is not None:
            meta.append(f"heading is {link(el, g)}")
        parts.append(f'<h2><a href="../{esc(local(s))}/">{title}</a></h2>'
                     + (f'<p class="muted">{" · ".join(meta)}</p>' if meta else "")
                     + (field_table(fields_by_section[s]) if fields_by_section.get(s) else ""))
    linked = sum(1 for n in fields if g.value(n, M11.realises) is not None)
    write("template/index.html", page("ICH M11 Template", f"""
<p>The headings and fields of the <a href="{TEMPLATE_URL}">ICH M11 Template</a> (Step 4, 19 November 2025), in Template order: {len([s for s in in_template if g.value(s, M11.templateHeading) is not None])} headings on their sections, {len(fields)} fields, {linked} of them linked to the element they realise. Instructional and universal text is not carried; the page links point into the PDF. Optional = printed in blue, conditional = in {{braces}} (Template section 0.3). How fields were linked: <a href="{REPO}/blob/main/reports/d5-template.md">D5 report</a>.</p>
{''.join(parts)}
"""))

    # D4 skeleton note.
    d4 = (ROOT / "notes" / "d4-skeleton.md").read_text(encoding="utf-8")
    write("d4-skeleton/index.html", page("D4 skeleton: how content points at an M11 element", markdown.markdown(d4.split("\n", 2)[2], extensions=["tables"])))

    # Slides: the PDF as rendered, and a forward from the folder URL.
    write("slides/index.html", f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={SLIDES_PDF}">
<title>ICH M11 elements: a target to map to (slides)</title>
</head>
<body><p><a href="{SLIDES_PDF}">ICH M11 elements: a target to map to (slides, PDF)</a></p></body>
</html>
""")
    shutil.copyfile(ROOT / "site" / SLIDES_PDF, DOCS / "slides" / SLIDES_PDF)

    onto = URIRef(str(M11))
    version = g.value(onto, OWL.versionInfo)
    vocab_counts = " · ".join(f"{name.lower()} {len(vocab_rows[name])}" for name, _ in groups)
    body = f"""
<p>Identifiers for ICH M11 protocol elements and sections, in one file. Statements that map them to USDM are in a separate file that points at these identifiers. Each page shows one identifier: what the files say about it, and what points to it.</p>
<dl>
<dt>Release</dt><dd>{esc(version)} · version IRI <span class="iri">{esc(g.value(onto, OWL.versionIRI))}</span></dd>
{dt("Description", [DCTERMS.description], 0)}<dd>{esc(g.value(onto, DCTERMS.description))}</dd>
{dt("Sources", [DCTERMS.source], 0)}<dd>{" · ".join(f'<a href="{esc(x)}">{esc(unquote(str(x).rsplit("/", 1)[1]))}</a>' for x in sorted(g.objects(onto, DCTERMS.source), key=str))}</dd>
</dl>
<h2>1 Vocabulary</h2>
<p>The terms used to describe the instances: <a href="vocabulary/">{len(terms)} terms</a> ({vocab_counts}).</p>
<p>Defined by m11-rdf in <a href="{REPO}/blob/main/vocabulary.ttl">vocabulary.ttl</a> (hand-maintained in the GitHub repository) and merged into m11-rdf.ttl; not taken from a published source. Other terms used come from SKOS, RDFS, RDF, OWL and Dublin Core.</p>
<h2>2 Instances</h2>
<dl>
<dt>Elements</dt><dd><a href="elements/">{len(elements)}</a> · one IRI each, <code>&lt;namespace code list&gt;.&lt;concept code&gt;</code>, e.g. {link(M11['C217356.C132352'], g, 0)} <code>C217356.C132352</code></dd>
<dt>Sections</dt><dd><a href="sections/">{len(sections)}</a> · identified by their C217272 term</dd>
<dt>Code lists</dt><dd><a href="code-lists/">{len(namespaces) + len(value_lists)}</a> · {len(namespaces)} namespaces, {len(value_lists)} value code lists, with ICH OIDs</dd>
<dt>ICH M11 Template</dt><dd><a href="template/">{sum(1 for s in sections if g.value(s, M11.templateHeading) is not None)} headings and {len(fields)} fields</a> on their sections, {sum(1 for n in fields if g.value(n, M11.realises) is not None)} fields linked to the element they realise · <a href="{REPO}/blob/main/reports/d5-template.md">D5 report</a></dd>
<dt>Files</dt><dd>m11-rdf.ttl: <a href="m11-rdf.ttl">Turtle</a> · <a href="m11-rdf.nt">N-Triples</a> · <a href="m11-rdf.rdf">RDF/XML</a> · <a href="m11-rdf.jsonld">JSON-LD</a></dd>
</dl>
<h3>Namespaces</h3>
<div class="table-wrap"><table><tr><th>Namespace</th><th>Section</th><th>Elements</th></tr>
{''.join(f"<tr><td>{link(n, g, 0)}</td><td>{link(g.value(n, M11.forSection), g, 0)}</td><td>{len(set(g.subjects(SKOS.inScheme, n)))}</td></tr>" for n in namespaces)}
</table></div>
<h2>3 Mapping sets that point at these identifiers</h2>
<p>Separate files, with their own sources, licences and versions. m11-rdf.ttl names none of them except through <code>rdfs:seeAlso</code>.</p>
<dl>
<dt>m11-usdm</dt><dd>{esc(set_meta["mapping_set_title"])} · version {esc(set_meta["mapping_set_version"])} · points at <span class="iri">{esc(set_meta["subject_source_version"])}</span></dd>
<dt>Records</dt><dd><a href="{MAPPING_PAGE}/">{len(records)} records</a> ({", ".join(f"{SOURCE_SHORT[k]} {sum(1 for x in records if x[1] == k)}" for k in SOURCE_LABEL)}) on {len(records_by_element)} elements, to {len({r["object_id"] for r in set_rows})} USDM attributes · <a href="m11-usdm.sssom.tsv">SSSOM/TSV</a> · <a href="m11-usdm.sssom.ttl">SSSOM/RDF</a></dd>
<dt>Not records</dt><dd><a href="{RESIDUE_PAGE}/">{len(no_record)} rows of the source mappings without a record</a>, and {len(flagged)} flagged records · <a href="{REPO}/blob/main/reports/d2-identification.md">identification report</a></dd>
</dl>
<h2>More</h2>
<dl>
<dt>Reports</dt><dd><a href="{REPO}/blob/main/reports/reconciliation.md">reconciliation of the sources</a> · <a href="{REPO}/blob/main/reports/tests.md">tests</a> · <a href="{REPO}/blob/main/reports/d2-identification.md">D2 identification</a> · <a href="{REPO}/blob/main/reports/tests-d2.md">D2 tests</a> · <a href="{REPO}/blob/main/reports/d5-template.md">D5 Template</a> · <a href="{REPO}/blob/main/reports/tests-d5.md">D5 tests</a></dd>
<dt>Slides</dt><dd><a href="slides/">ICH M11 elements: a target to map to</a> · what m11-rdf gives when mapping protocol content to ICH M11 and USDM v4, what is left, and questions for USDM 4.1 (PDF, eight slides)</dd>
<dt>Design note</dt><dd><a href="d4-skeleton/">D4 skeleton</a>: how a study, a document section or a template field points at the element it realises</dd>
</dl>
"""
    write("index.html", page("ICH M11 protocol elements and sections as linked data", body, depth=0, iri=str(M11)))
    print("pages:", sum(1 for _ in DOCS.rglob("index.html")))


def serialize(fmt, source, target):
    g = stable_bnodes(Graph().parse(source, format="nt"))
    for prefix, ns in [("m11", M11), ("ncit", NCIT), ("obo", OBO), ("skos", SKOS), ("owl", OWL)]:
        g.bind(prefix, ns)
    g.serialize(target, format=fmt, encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--serialize"]:
        serialize(*sys.argv[2:5])
    else:
        main()
