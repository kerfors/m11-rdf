"""Build the GitHub Pages site in docs/ from m11-rdf.ttl.

One page per minted IRI at its own path (<local name>/index.html): elements,
sections, code lists and vocabulary terms; each mapping record
(mapping/<source>/<row>) as a forward to its row on the element page. The
ICH M11 Template (D5) on the section and element pages and as one page in
Template order (template/). The whole graph as Turtle, N-Triples, RDF/XML
and JSON-LD; the mapping set as SSSOM/TSV and SSSOM/RDF. docs/ is
generated; do not edit by hand.
Fails if two page paths differ only by case.
"""
import html
import os
import shutil
import subprocess
import sys
from collections import defaultdict

import markdown

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from common import M11, NCIT, OBO, ROOT

USDM = "https://w3id.org/cdisc/usdm/v4/"
SOURCE_LABEL = {"hl7": "HL7 CSP IG ballot", "cdisc": "CDISC DDF-RA v4.0.0"}
MAPPING_FILES = ["m11-usdm.sssom.tsv", "m11-usdm.sssom.ttl"]

DOCS = ROOT / "docs"
REPO = "https://github.com/kerfors/m11-rdf"
READING_PAGES = {"d4-skeleton", "template"}
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
"""


def esc(x):
    return html.escape(str(x))


def local(iri):
    return str(iri)[len(str(M11)):]


def link(iri, g, depth=1):
    """Link to a minted IRI's page (relative), labelled with its prefLabel or rdfs:label."""
    label = g.value(iri, SKOS.prefLabel) or g.value(iri, RDFS.label) or local(iri)
    return f'<a href="{"../" * depth}{esc(local(iri))}/">{esc(label)}</a>'


def page(title, body, depth=1, iri=None):
    up = "../" * depth
    head_iri = f'<p><span class="iri">{esc(iri)}</span></p>' if iri else ""
    alt = f'<link rel="alternate" type="text/turtle" href="{up}m11-rdf.ttl">'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · m11-rdf</title>
{alt}
<style>{CSS}</style>
</head>
<body>
<main>
<nav><a href="{up}">m11-rdf</a> · <a href="{up}sections/">sections</a> · <a href="{up}code-lists/">code lists</a> · <a href="{up}template/">template</a> · <a href="{up}vocabulary/">vocabulary</a> · <a href="{REPO}">source</a></nav>
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
    elements = sorted(g.subjects(RDF.type, M11.Element), key=str)
    sections = sorted(g.subjects(RDF.type, M11.Section), key=str)
    namespaces = sorted(g.subjects(RDF.type, M11.Namespace), key=lambda n: int(str(g.value(n, SKOS.notation)).rsplit(".", 1)[1]))
    value_lists = sorted(g.subjects(RDF.type, M11.ValueCodeList), key=lambda n: int(str(g.value(n, SKOS.notation)).rsplit(".", 1)[1]))
    vocab = Graph().parse(ROOT / "vocabulary.ttl")
    terms = sorted({s for s in vocab.subjects() if isinstance(s, URIRef) and str(s).startswith(str(M11)) and local(s)}, key=str)

    records = sorted(g.subjects(RDF.type, OWL.Axiom),
                     key=lambda r: (list(SOURCE_LABEL).index(local(r).split("/")[1]), int(local(r).split("/")[2])))
    records_by_element = defaultdict(list)
    for r in records:
        records_by_element[g.value(r, OWL.annotatedSource)].append(r)

    paths = [local(x) for x in elements + sections + namespaces + value_lists + terms + records]
    paths += ["sections", "code-lists", "vocabulary"] + sorted(READING_PAGES)
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
        return f'<div class="table-wrap"><table><tr><th>Field</th><th>Template</th><th>Page</th><th>Realises</th><th>Linked by</th></tr>{rows}</table></div>'

    def template_part(s, depth=1):
        heading = g.value(s, M11.templateHeading)
        out = "<h2>In the ICH M11 Template</h2>"
        if heading is not None:
            el = g.value(s, M11.headingElement)
            out += f"""<dl>
<dt>Heading</dt><dd>{esc(heading)} <span class="muted">{esc(flags(s))}</span></dd>
<dt>Page</dt><dd>{pdf_page(s)}</dd>
{f'<dt>Heading is</dt><dd>{link(el, g, depth)} <span class="muted">(TS term, {esc(g.value(s, M11.placeScope))})</span></dd>' if el is not None else ''}
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
            out += "<p>The Template heading of " + ", ".join(link(x, g) for x in hs) + " is this element.</p>"
        if fs:
            rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in [
                link(g.value(predicate=M11.hasTemplateField, object=n), g) + f' <span class="muted">{esc(g.value(n, M11.templateSectionNumber))}</span>',
                f"<code>{bracketed(n)}</code>",
                esc(flags(n)),
                pdf_page(n),
                f'<span class="muted">{basis(n)}</span>',
            ]) + "</tr>" for n in fs)
            out += f'<div class="table-wrap"><table><tr><th>Section</th><th>Field</th><th>Template</th><th>Page</th><th>Linked by</th></tr>{rows}</table></div>'
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
        map_rows = []
        for r in records_by_element.get(e, []):
            _, src, row = local(r).split("/")
            target = g.value(r, OWL.annotatedTarget)
            map_rows.append(f'<tr id="mapping-{src}-{row}">' + "".join(f"<td>{c}</td>" for c in [
                f'{esc(SOURCE_LABEL[src])}<br><a href="../mapping/{src}/{row}/">row {esc(row)}</a>',
                f'<a href="{esc(target)}">{esc(str(target)[len(USDM):])}</a><br><span class="muted">stated: {esc(g.value(r, M11.statedClass))}.{esc(g.value(r, M11.statedAttribute))} ({esc(g.value(r, M11.objectResolution))})</span>',
                esc(g.value(r, M11.subjectIdentification)),
                f'<code>{esc(g.value(r, M11.targetPath))}</code>',
                f'<code>{esc(g.value(r, M11.conditionPath))}</code>' if str(g.value(r, M11.conditionPath)) else "",
            ]) + "</tr>")
        mappings = (f"""<h2>Mapping statements to USDM v4</h2>
<p class="muted">One row per published mapping row that names this element (SSSOM record). The link to the USDM attribute is the mapping publisher's; how the row was tied to this element is in the third column. Paths as given.</p>
<div class="table-wrap"><table>
<tr><th>Source</th><th>USDM attribute (usdm-rdf)</th><th>Identified</th><th>Target path</th><th>Condition</th></tr>
{''.join(map_rows)}
</table></div>""" if map_rows else '<h2>Mapping statements to USDM v4</h2><p class="muted">None: no row of the two pinned mappings is identified with this element and resolves in USDM v4.0.0.</p>')
        alts = ", ".join(esc(a) for a in g.objects(e, SKOS.altLabel))
        definition = g.value(e, SKOS.definition)
        body = f"""
<dl>
<dt>Definition</dt><dd>{esc(definition) if definition else '<span class="muted">none (no EVS term for this pair)</span>'}</dd>
{f'<dt>Synonyms</dt><dd>{alts}</dd>' if alts else ''}
<dt>Namespace</dt><dd>{link(g.value(e, SKOS.inScheme), g)}</dd>
<dt>ICH pair</dt><dd><code>{esc(g.value(e, M11.ichNamespaceOid))}</code> + <code>{esc(g.value(e, M11.ichConceptCode))}</code> <span class="muted">({esc(g.value(g.value(e, M11.pairBasis), RDFS.label))})</span></dd>
<dt>NCIt concept</dt><dd>{ncit_links(g, e)}</dd>
<dt>EVS term</dt><dd>{evs_twin(g, e)}</dd>
<dt>Label from</dt><dd>{esc(g.value(g.value(e, M11.labelSource), RDFS.label))}</dd>
</dl>
<h2>Specifications in the Technical Specification</h2>
<p class="muted">One row per component block of Appendix 1 that names this element. Text as printed.</p>
<div class="table-wrap"><table>
<tr><th>Block</th><th>Term</th><th>Section</th><th>Conformance</th><th>Cardinality</th><th>Data type</th><th>Value code list</th><th>Repeating / reuse</th></tr>
{''.join(rows)}
</table></div>
{element_template(e)}
{mappings}
"""
        write(f"{local(e)}/index.html", page(str(g.value(e, SKOS.prefLabel)), body, iri=e))

    # Mapping records: a forward to the row on the element page.
    for r in records:
        _, src, row = local(r).split("/")
        e = g.value(r, OWL.annotatedSource)
        to = f"../../../{local(e)}/#mapping-{src}-{row}"
        write(f"{local(r)}/index.html", f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={esc(to)}">
<link rel="alternate" type="text/turtle" href="../../../m11-rdf.ttl">
<title>Mapping record {esc(src)} row {esc(row)} · m11-rdf</title></head>
<body><p>Mapping record <span class="iri">{esc(r)}</span>: {esc(SOURCE_LABEL[src])}, row {esc(row)}, on <a href="{esc(to)}">{esc(g.value(e, SKOS.prefLabel))}</a>.</p></body></html>
""")

    # Sections.
    for s in sections:
        num = g.value(s, M11.sectionNumber)
        here = sorted(specs_by_section.get(s, []), key=lambda es: int(g.value(es[1], M11.tsBlock)))
        el_rows = "".join(f"<tr><td>{link(e, g)}</td><td><code>{esc(local(e))}</code></td><td>{esc(g.value(sp, M11.conformance))}</td><td>{esc(g.value(sp, M11.tsBlock))}</td></tr>"
                          for e, sp in here)
        kids = "".join(f"<li>{link(k, g)}</li>" for k in sorted(narrower.get(s, []), key=section_sort))
        ns = [n for n in namespaces if g.value(n, M11.forSection) == s]
        body = f"""
<dl>
<dt>Definition</dt><dd>{esc(g.value(s, SKOS.definition))}</dd>
<dt>Section number</dt><dd>{esc(num) if num else '<span class="muted">none</span>'}</dd>
<dt>Broader</dt><dd>{link(g.value(s, SKOS.broader), g) if g.value(s, SKOS.broader) else '<span class="muted">top level</span>'}</dd>
{f'<dt>Namespace</dt><dd>{link(ns[0], g)}</dd>' if ns else ''}
<dt>NCIt concept</dt><dd>{ncit_links(g, s)}</dd>
<dt>EVS term</dt><dd>{evs_twin(g, s)}</dd>
</dl>
{f'<h2>Subsections</h2><ul class="tree">{kids}</ul>' if kids else ''}
<h2>Elements specified in this section</h2>
{f'<div class="table-wrap"><table><tr><th>Element</th><th>IRI</th><th>Conformance</th><th>TS block</th></tr>{el_rows}</table></div>' if el_rows else '<p class="muted">None.</p>'}
{template_part(s)}
"""
        write(f"{local(s)}/index.html", page(str(g.value(s, SKOS.prefLabel)), body, iri=s))

    # Code lists.
    for c in namespaces + value_lists:
        is_ns = (c, RDF.type, M11.Namespace) in g
        if is_ns:
            members = sorted(g.subjects(SKOS.inScheme, c), key=str)
            listing = "".join(f"<tr><td>{link(e, g)}</td><td><code>{esc(local(e))}</code></td></tr>" for e in members)
            extra = f'<h2>Elements ({len(members)})</h2><div class="table-wrap"><table><tr><th>Element</th><th>IRI</th></tr>{listing}</table></div>'
        else:
            users = specs_by_codelist.get(c, [])
            listing = "".join(f"<tr><td>{link(e, g)}</td><td>{esc(g.value(sp, M11.tsBlock))}</td></tr>" for e, sp in users)
            extra = (f'<h2>Used by</h2><div class="table-wrap"><table><tr><th>Element</th><th>TS block</th></tr>{listing}</table></div>'
                     if listing else '<h2>Used by</h2><p class="muted">No element block names this code list.</p>')
            extra += '<p class="muted">The values of this code list are not rendered in this release.</p>'
        body = f"""
<dl>
<dt>Kind</dt><dd>{'Namespace (section code list)' if is_ns else 'Value code list'}</dd>
<dt>ICH OID</dt><dd><code>{esc(g.value(c, SKOS.notation))}</code> <span class="muted">(OID Listing, 2025-10-16)</span></dd>
<dt>Definition</dt><dd>{esc(g.value(c, SKOS.definition) or '')}</dd>
{f'<dt>Section</dt><dd>{link(g.value(c, M11.forSection), g)}</dd>' if is_ns else ''}
<dt>NCIt concept</dt><dd>{ncit_links(g, c)}</dd>
<dt>EVS code list</dt><dd>{evs_twin(g, c)}</dd>
</dl>
{extra}
"""
        write(f"{local(c)}/index.html", page(str(g.value(c, SKOS.prefLabel)), body, iri=c))

    # Vocabulary terms.
    vocab_rows = []
    for t in terms:
        kinds = ", ".join(sorted(local(k) if str(k).startswith(str(M11)) else str(k).split("#")[-1] for k in vocab.objects(t, RDF.type)))
        dom, rng = vocab.value(t, RDFS.domain), vocab.value(t, RDFS.range)
        sup = vocab.value(t, RDFS.subClassOf)

        def ref(x):
            if x is None:
                return ""
            if str(x).startswith(str(M11)):
                return link(x, vocab)
            return f'<span class="iri">{esc(x)}</span>'
        body = f"""
<dl>
<dt>Type</dt><dd>{esc(kinds)}</dd>
<dt>Description</dt><dd>{esc(vocab.value(t, RDFS.comment) or '')}</dd>
{f'<dt>Subclass of</dt><dd>{ref(sup)}</dd>' if sup else ''}
{f'<dt>Domain</dt><dd>{ref(dom)}</dd>' if dom else ''}
{f'<dt>Range</dt><dd>{ref(rng)}</dd>' if rng else ''}
</dl>
"""
        write(f"{local(t)}/index.html", page(str(vocab.value(t, RDFS.label)), body, iri=t))
        vocab_rows.append(f"<tr><td>{link(t, vocab)}</td><td><code>m11:{esc(local(t))}</code></td><td>{esc(kinds)}</td></tr>")
    write("vocabulary/index.html", page("Vocabulary", f'<div class="table-wrap"><table><tr><th>Term</th><th>Name</th><th>Type</th></tr>{"".join(vocab_rows)}</table></div>'))

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

    onto = URIRef(str(M11))
    version = g.value(onto, OWL.versionInfo)
    body = f"""
<p>{esc(g.value(onto, URIRef("http://purl.org/dc/terms/description")))}</p>
<dl>
<dt>Release</dt><dd>{esc(version)} · version IRI <span class="iri">{esc(g.value(onto, OWL.versionIRI))}</span></dd>
<dt>Elements</dt><dd>{len(elements)} · one IRI each, <code>&lt;namespace code list&gt;.&lt;concept code&gt;</code>, e.g. {link(M11['C217356.C132352'], g, 0)} <code>C217356.C132352</code></dd>
<dt>Sections</dt><dd><a href="sections/">{len(sections)}</a> · identified by their C217272 term</dd>
<dt>Code lists</dt><dd><a href="code-lists/">{len(namespaces) + len(value_lists)}</a> · {len(namespaces)} namespaces, {len(value_lists)} value code lists, with ICH OIDs</dd>
<dt>Mapping statements</dt><dd>{len(records)} SSSOM records ({", ".join(f"{sum(1 for r in records if local(r).split('/')[1] == k)} {esc(v)}" for k, v in SOURCE_LABEL.items())}) to {len(set(g.objects(None, M11.mappedTo)))} USDM attributes, on {len(records_by_element)} elements · <a href="m11-usdm.sssom.tsv">SSSOM/TSV</a> · <a href="m11-usdm.sssom.ttl">SSSOM/RDF</a> · <a href="{REPO}/blob/main/reports/d2-identification.md">identification report</a></dd>
<dt>ICH M11 Template</dt><dd><a href="template/">{sum(1 for s in sections if g.value(s, M11.templateHeading) is not None)} headings and {len(fields)} fields</a> on their sections, {sum(1 for n in fields if g.value(n, M11.realises) is not None)} fields linked to the element they realise · <a href="{REPO}/blob/main/reports/d5-template.md">D5 report</a></dd>
<dt>Whole graph</dt><dd><a href="m11-rdf.ttl">Turtle</a> · <a href="m11-rdf.nt">N-Triples</a> · <a href="m11-rdf.rdf">RDF/XML</a> · <a href="m11-rdf.jsonld">JSON-LD</a></dd>
<dt>Reports</dt><dd><a href="{REPO}/blob/main/reports/reconciliation.md">reconciliation of the sources</a> · <a href="{REPO}/blob/main/reports/tests.md">tests</a> · <a href="{REPO}/blob/main/reports/d2-identification.md">D2 identification</a> · <a href="{REPO}/blob/main/reports/tests-d2.md">D2 tests</a> · <a href="{REPO}/blob/main/reports/d5-template.md">D5 Template</a> · <a href="{REPO}/blob/main/reports/tests-d5.md">D5 tests</a></dd>
<dt>Design note</dt><dd><a href="d4-skeleton/">D4 skeleton</a>: how a study, a document section or a template field points at the element it realises</dd>
</dl>
<h2>Namespaces</h2>
<div class="table-wrap"><table><tr><th>Namespace</th><th>Section</th><th>Elements</th></tr>
{''.join(f"<tr><td>{link(n, g, 0)}</td><td>{link(g.value(n, M11.forSection), g, 0)}</td><td>{len(set(g.subjects(SKOS.inScheme, n)))}</td></tr>" for n in namespaces)}
</table></div>
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
