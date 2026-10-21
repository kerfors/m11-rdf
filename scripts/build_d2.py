"""Build D2: mapping statements from ICH M11 elements to usdm-rdf attributes, as an SSSOM mapping set.

Inputs (pinned, checked): the HL7 CSP IG ballot mapping and the CDISC DDF-RA
v4.0.0 mapping (neither primary, DECISIONS M16), usdm-rdf v0.7.0, the
SSSOM schema; and the D1 graph m11-rdf.ttl as
written by build_d1.py (run build_d1.py first).

One statement per mapping row whose M11 side is identified and whose USDM
target resolves (M17, M19):
- M11 side by code: the NCIt Code cell is one C-code that is the concept of
  one D1 element. If the code is the concept of elements in several
  namespaces, the row's section (number, or title when the number is empty)
  decides against the elements' ToC references; otherwise the row is
  ambiguous.
- Otherwise by unique name: the normalised ElementName equals the
  normalised term of exactly one Technical Specification element block.
- USDM side: the stated Class and Attribute are looked up in usdm-rdf: a
  property of the class or of a superclass, by attribute name or by
  usdm:modelName (the relationship role name, e.g. previous for
  previousId); the object is that property. Nothing is repaired.
Rows without a statement, and statements with a flag, are written to
reports/d2-residue.csv for usdm-overlay layer 4.

Outputs: m11-usdm.sssom.tsv, m11-usdm.sssom.ttl, m11-rdf.ttl (D1 plus the
mapping records and one m11:mappedTo triple per distinct pair),
reports/d2-identification.md, reports/d2-identification.csv,
reports/d2-residue.csv.
"""
import csv
import json
import re
from collections import Counter, defaultdict

import openpyxl
import yaml
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from common import BUILD, DOWNLOADS, M11, REPORTS, ROOT, checked
from fetch_inputs import INPUTS

USDM = Namespace("https://w3id.org/cdisc/usdm/v4/")
SSSOM = Namespace("https://w3id.org/sssom/")
SEMAPV = Namespace("https://w3id.org/semapv/vocab/")
MAP = Namespace(str(M11) + "mapping/")

VERSION = "0.2.0"
SET_FILE = "m11-usdm.sssom.tsv"
SET_ID = str(M11) + SET_FILE
SCHEMA = "sssom/sssom_schema.yaml"
USDM_TTL = "usdm-rdf/usdm_v4.ttl"
URL = {i["name"]: i["url"] for i in INPUTS}

SOURCES = [
    {"key": "hl7", "file": "hl7/M11 to FHIR Mapping 02.xlsx",
     "author": "HL7 International / Biomedical Research and Regulation (FHIR Clinical Study Protocol IG, STU 1 ballot, May 2026)",
     "provider": "https://hl7.org/fhir/uv/clinical-study-protocol/2026May/en/"},
    {"key": "cdisc", "file": "cdisc/m11_mapping.xlsx",
     "author": "CDISC (DDF-RA v4.0.0, Documents/Mappings/m11_mapping.xlsx)",
     "provider": "https://github.com/cdisc-org/DDF-RA/tree/v4.0.0"},
]
COLUMNS = ["Section Number", "Section Title", "ElementName", "NCIt Code", "Class", "Attribute", "Target Path",
           "Condition Path"]

PREDICATE = M11.mappedTo
JUSTIFICATION = SEMAPV.ManualMappingCuration
EXTENSIONS = [
    ("source_row", M11.sourceRow, XSD.integer),
    ("source_section", M11.sourceSection, XSD.string),
    ("subject_identification", M11.subjectIdentification, XSD.string),
    ("object_resolution", M11.objectResolution, XSD.string),
    ("stated_class", M11.statedClass, XSD.string),
    ("stated_attribute", M11.statedAttribute, XSD.string),
    ("target_path", M11.targetPath, XSD.string),
    ("condition_path", M11.conditionPath, XSD.string),
]
TSV_COLUMNS = ["record_id", "subject_id", "subject_label", "subject_type", "predicate_id", "predicate_label",
               "object_id", "object_label", "object_type", "mapping_justification", "subject_match_field",
               "match_string", "mapping_source", "author_label"] + [e[0] for e in EXTENSIONS]
CURIES = {"m11": str(M11), "m11map": str(MAP), "usdm": str(USDM), "semapv": str(SEMAPV),
          "skos": str(SKOS), "owl": str(OWL),
          "hl7csp": "https://hl7.org/fhir/uv/clinical-study-protocol/2026May/en/Mappings/",
          "ddfra": "https://raw.githubusercontent.com/cdisc-org/DDF-RA/v4.0.0/Documents/Mappings/"}


def norm(s):
    """Name normalisation for by-unique-name: case, punctuation, brackets, white space."""
    s = s.lower().replace("’", "'")
    s = re.sub(r"[{}\[\]<>():;,.?'\"/\-–_]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def one_line(s):
    """Cell text with each line break (and the white space around it) replaced by one space."""
    return re.sub(r"\s*\n\s*", " ", s).strip()


def curie(iri):
    for p, ns in sorted(CURIES.items(), key=lambda kv: -len(kv[1])):
        if str(iri).startswith(ns):
            return f"{p}:{str(iri)[len(ns):]}"
    raise RuntimeError(f"No prefix for {iri}")


def local(iri):
    return str(iri)[len(str(M11)):]


def read_rows(source):
    ws = openpyxl.load_workbook(checked(source["file"]), read_only=True)["Mapping"]
    rows = list(ws.iter_rows(values_only=True))
    if rows[0][0] != "M11" or rows[0][8] != "USDM":
        raise RuntimeError(f"{source['file']}: unexpected group header {rows[0][:9]}")
    col = {k: i for i, k in enumerate(rows[1]) if k}
    missing = [c for c in COLUMNS if c not in col]
    if missing:
        raise RuntimeError(f"{source['file']}: missing columns {missing}")
    out = []
    for n, r in enumerate(rows[2:], start=3):
        if all(x is None for x in r):
            continue
        out.append({"source": source["key"], "row": n,
                    **{c: (str(r[col[c]]).strip() if r[col[c]] is not None else "") for c in COLUMNS}})
    return out


def d1_index(g):
    """Elements by concept code; element blocks by normalised term; ToC references per element."""
    elements = sorted(g.subjects(RDF.type, M11.Element), key=str)
    by_code = defaultdict(list)
    tocs = {}
    names = defaultdict(set)
    for e in elements:
        by_code[str(g.value(e, M11.ichConceptCode))].append(e)
        specs = list(g.objects(e, M11.hasSpecification))
        tocs[e] = sorted({str(g.value(s, M11.tocReference)) for s in specs})
        for s in specs:
            names[norm(str(g.value(s, M11.tsTerm)))].add((int(g.value(s, M11.tsBlock)), e))
    return elements, by_code, tocs, names


def place_matches(place, toc):
    """Row section (number, or title) against an element ToC reference.

    A title must equal the ToC reference. A number matches when it equals the
    leading number of the ToC reference or is a prefix of it, segment by
    segment, with X and # read as any number.
    """
    if not place:
        return False
    if place == toc:
        return True
    p = place.rstrip(".").split(".")
    t = toc.split(" ")[0].split(".")
    seg = re.compile(r"\d+|X|#")
    if not all(seg.fullmatch(x) for x in p + t) or len(p) > len(t):
        return False
    return all(a == b or a in ("X", "#") or b in ("X", "#") for a, b in zip(p, t))


def identify(row, by_code, tocs, names, other_blocks):
    """(method, [elements], note) for the M11 side of a mapping row (DECISIONS M19)."""
    code = row["NCIt Code"]
    place = row["Section Number"] or row["Section Title"]
    notes = []
    if re.fullmatch(r"C\d+", code) and code in by_code:
        cands = by_code[code]
        if len(cands) == 1:
            return "by-code", cands, ""
        pick = [e for e in cands if any(place_matches(place, t) for t in tocs[e])]
        if len(pick) == 1:
            return "by-code", pick, "code is the concept of elements in several namespaces; the row's section decides"
        return "ambiguous-code", cands, "code is the concept of elements in several namespaces; the row's section does not decide"
    if re.fullmatch(r"C\d+", code):
        notes.append("code is not the concept of a TS element")
    elif code and code != "CNEW":
        notes.append("code cell is not one C-code")
    hits = names.get(norm(row["ElementName"]), set())
    if len(hits) > 1:
        return "ambiguous-name", sorted({e for _, e in hits}, key=str), "; ".join(
            notes + ["name on TS element blocks " + ", ".join(str(b) for b, _ in sorted(hits, key=lambda h: h[0]))])
    if len(hits) == 1:
        return "by-unique-name", [next(iter(hits))[1]], "; ".join(notes)
    blocks = other_blocks.get(norm(row["ElementName"]))
    if blocks:
        notes.append("name on TS block(s) without a concept: " + ", ".join(str(b) for b in blocks))
    return "unidentified", [], "; ".join(notes)


class Usdm:
    """usdm-rdf classes and properties for resolving a stated Class.Attribute."""

    def __init__(self):
        self.g = Graph().parse(checked(USDM_TTL))
        self.classes = {local_usdm(c) for c in self.g.subjects(RDF.type, OWL.Class) if str(c).startswith(str(USDM))}
        self.kind = {}
        for t in (OWL.ObjectProperty, OWL.DatatypeProperty):
            for p in self.g.subjects(RDF.type, t):
                if str(p).startswith(str(USDM)):
                    self.kind[local_usdm(p)] = t
        self.own = defaultdict(list)
        for p in self.kind:
            domain = self.g.value(USDM[p], RDFS.domain)
            if local_usdm(domain) + "-" != p[:len(local_usdm(domain)) + 1]:
                raise RuntimeError(f"usdm-rdf property {p} is not named <domain class>-<attribute>")
            self.own[local_usdm(domain)].append(p)
        self.supers = defaultdict(list)
        self.subs = defaultdict(list)
        for c in self.classes:
            for s in self.g.objects(USDM[c], RDFS.subClassOf):
                if isinstance(s, URIRef) and str(s).startswith(str(USDM)):
                    self.supers[c].append(local_usdm(s))
                    self.subs[local_usdm(s)].append(c)

    def ancestors(self, c):
        seen, todo = [], [c]
        while todo:
            x = todo.pop(0)
            if x not in seen:
                seen.append(x)
                todo.extend(sorted(self.supers[x]))
        return seen

    def declared(self, c, attr):
        """[(property, how)] declared on class c for attr: by attribute name, or by usdm:modelName."""
        out = [(p, "attribute name") for p in self.own[c] if p == f"{c}-{attr}"]
        out += [(p, "model name") for p in self.own[c]
                if p != f"{c}-{attr}" and str(self.g.value(USDM[p], USDM.modelName)) == attr]
        if len(out) > 1:
            raise RuntimeError(f"{c}: {attr} matches several usdm-rdf properties {out}")
        return out

    def resolve(self, cls, attr):
        """(usdm-rdf property local name or None, how). Own or inherited; nothing repaired."""
        if cls not in self.classes:
            return None, "class not in usdm-rdf"
        for a in self.ancestors(cls):
            hit = self.declared(a, attr)
            if hit:
                prop, how = hit[0]
                return prop, how + ("" if a == cls else ", inherited")
        subs = sorted(s for s in self.subs[cls] if self.declared(s, attr))
        return None, ("attribute only on subclasses " + ", ".join(subs)) if subs else "attribute not on the class"


def local_usdm(iri):
    return str(iri)[len(str(USDM)):]


def other_block_names():
    """Normalised terms of TS blocks without a concept (headings and the like), for residue notes."""
    blocks = json.loads((BUILD / "ts_blocks.json").read_text(encoding="utf-8"))
    out = defaultdict(list)
    for b in blocks:
        if not re.search(r"Concept:\s*C\d+", b.get("business_rules", "")):
            out[norm(b["term"])].append(b["block"])
    return out


def schema_slot_uris():
    """slot name -> RDF property, from the pinned SSSOM schema (slot_uri, else sssom:<name>)."""
    schema = yaml.safe_load(checked(SCHEMA).read_text(encoding="utf-8"))
    prefixes = {**schema["prefixes"], "owl": str(OWL)}
    out = {}
    for name, slot in schema["slots"].items():
        uri = slot.get("slot_uri")
        if uri:
            p, l = uri.split(":", 1)
            out[name] = URIRef(prefixes[p] + l)
        else:
            out[name] = SSSOM[name]
    return out


def main():
    g = Graph().parse(ROOT / "m11-rdf.ttl")
    if (None, PREDICATE, None) in g or (None, RDF.type, OWL.Axiom) in g:
        raise RuntimeError("m11-rdf.ttl already holds mapping statements; run build_d1.py first")
    elements, by_code, tocs, names = d1_index(g)
    other_blocks = other_block_names()
    usdm = Usdm()
    slot = schema_slot_uris()

    rows = [r for s in SOURCES for r in read_rows(s)]
    records = []
    for r in rows:
        method, ids, note = identify(r, by_code, tocs, names, other_blocks)
        prop, how = (usdm.resolve(r["Class"], r["Attribute"]) if r["Class"] else (None, "no target"))
        flags = []
        if method in ("by-code", "by-unique-name"):
            e = ids[0]
            if r["Section Number"] and not any(place_matches(r["Section Number"], t) for t in tocs[e]):
                flags.append("row section differs from the element's ToC reference")
            if method == "by-code":
                hits = names.get(norm(r["ElementName"]), set())
                if len(hits) == 1 and next(iter(hits))[1] != e:
                    flags.append("unique name identifies " + local(next(iter(hits))[1]))
        status = "statement" if method in ("by-code", "by-unique-name") and prop and not any(
            f.startswith("unique name identifies") for f in flags) else "residue"
        records.append({**r, "method": method, "elements": ids, "note": note, "object": prop, "how": how,
                        "flags": flags, "status": status})

    statements = [x for x in records if x["status"] == "statement"]
    write_set(g, statements, usdm, slot)
    write_reports(records, statements, elements, usdm)
    print(len(statements), "statements;", len(records) - len(statements), "rows without a statement;",
          len({(x["elements"][0], x["object"]) for x in statements}), "distinct element-target pairs")


def record_iri(x):
    return MAP[f"{x['source']}/{x['row']}"]


def ext_values(x):
    return {
        "source_row": x["row"],
        "source_section": x["Section Number"] or x["Section Title"],
        "subject_identification": x["method"],
        "object_resolution": x["how"],
        "stated_class": x["Class"],
        "stated_attribute": x["Attribute"],
        "target_path": one_line(x["Target Path"]),
        "condition_path": one_line(x["Condition Path"]),
    }


def set_metadata():
    usdm_version = Graph().parse(checked(USDM_TTL)).value(URIRef(str(USDM)), OWL.versionIRI)
    return {
        "mapping_set_id": SET_ID,
        "mapping_set_version": VERSION,
        "mapping_set_title": "ICH M11 elements to USDM v4 (usdm-rdf), as stated in two published mappings",
        "mapping_set_description": (
            "One record per row of the HL7 FHIR Clinical Study Protocol IG ballot mapping (May 2026) and of the CDISC "
            "DDF-RA v4.0.0 M11 mapping whose M11 side is identified against m11-rdf and whose USDM target resolves "
            "in usdm-rdf (USDM v4.0.0). Neither mapping is primary. The link from element to USDM target is the publisher's; "
            "m11-rdf adds only the identification of the M11 side: by code (the row's NCIt Code is the concept of one "
            "element, or the row's section decides between namespaces), or by the row's element name when its "
            "normalised form (case, punctuation, brackets, white space) equals the term of exactly one Technical "
            "Specification element block. Target and condition paths as given, line breaks replaced by a space. "
            "Rows without a record are listed in reports/d2-residue.csv. Draft, not normative; not an ICH, CDISC or "
            "HL7 artifact."),
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "sssom_version": "1.1",
        "creator_label": "Kerstin Forsberg",
        "subject_source": str(M11),
        "subject_source_version": str(M11[VERSION]),
        "object_source": str(USDM),
        "object_source_version": str(usdm_version),
        "see_also": "https://github.com/kerfors/m11-rdf",
    }


def write_set(g, statements, usdm, slot):
    meta = set_metadata()
    labels = {e: str(g.value(e, SKOS.prefLabel)) for e in g.subjects(RDF.type, M11.Element)}
    otype = {OWL.ObjectProperty: "owl object property", OWL.DatatypeProperty: "owl data property"}
    otype_iri = {OWL.ObjectProperty: OWL.ObjectProperty, OWL.DatatypeProperty: URIRef(str(OWL) + "DataProperty")}
    author = {s["key"]: s["author"] for s in SOURCES}
    file_of = {s["key"]: s["file"] for s in SOURCES}

    # SSSOM/TSV.
    head = ["curie_map:"] + [f"  {p}: {ns}" for p, ns in sorted(CURIES.items())]
    for k, v in meta.items():
        head.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    head.append("extension_definitions:")
    for name, prop, hint in EXTENSIONS:
        head += [f"  - slot_name: {name}", f"    property: {curie(prop)}",
                 f"    type_hint: {'xsd:' + str(hint)[len(str(XSD)):] if hint else 'linkml:Uriorcurie'}"]
    lines = ["#" + h for h in head]
    lines.append("\t".join(TSV_COLUMNS))
    for x in sorted(statements, key=lambda x: ([s["key"] for s in SOURCES].index(x["source"]), x["row"])):
        e = x["elements"][0]
        ext = ext_values(x)
        cells = {
            "record_id": curie(record_iri(x)),
            "subject_id": curie(e),
            "subject_label": labels[e],
            "subject_type": "skos concept",
            "predicate_id": curie(PREDICATE),
            "predicate_label": "mapped to",
            "object_id": curie(USDM[x["object"]]),
            "object_label": x["object"],
            "object_type": otype[usdm.kind[x["object"]]],
            "mapping_justification": curie(JUSTIFICATION),
            "subject_match_field": "m11:ichConceptCode" if x["method"] == "by-code" else "m11:tsTerm",
            "match_string": x["NCIt Code"] if x["method"] == "by-code" else x["ElementName"],
            "mapping_source": curie(URL[file_of[x["source"]]]),
            "author_label": author[x["source"]],
            **{k: (curie(v) if isinstance(v, URIRef) else str(v)) for k, v in ext.items()},
        }
        for k, v in cells.items():
            if "\t" in v or "\n" in v:
                raise RuntimeError(f"Tab or line break in {k} of {x['source']} row {x['row']}")
        lines.append("\t".join(cells[c] for c in TSV_COLUMNS))
    (ROOT / SET_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # SSSOM/RDF (spec-formats-rdf): the set, its extension definitions, one owl:Axiom per record.
    s = Graph()
    for p, ns in list(CURIES.items()) + [("sssom", SSSOM), ("dcterms", DCTERMS), ("xsd", XSD)]:
        s.bind(p, ns)
    ms = URIRef(SET_ID)
    s.add((ms, RDF.type, SSSOM.MappingSet))
    for k, v in meta.items():
        if k == "mapping_set_id":
            continue
        uri_valued = k in ("license", "subject_source", "subject_source_version", "object_source",
                           "object_source_version", "see_also")
        if k == "sssom_version":
            s.add((ms, slot[k], SSSOM["version" + v]))
        else:
            s.add((ms, slot[k], URIRef(v) if uri_valued else Literal(v)))
    for i, (name, prop, hint) in enumerate(EXTENSIONS):
        d = BNode(f"ext{i}")
        s.add((ms, slot["extension_definitions"], d))
        s.add((d, RDF.type, SSSOM.ExtensionDefinition))
        s.add((d, SSSOM.slot_name, Literal(name)))
        s.add((d, SSSOM.property, prop))
        s.add((d, SSSOM.type_hint, hint if hint else URIRef("https://w3id.org/linkml/Uriorcurie")))
    records = Graph()
    for x in statements:
        r = record_iri(x)
        e = x["elements"][0]
        records.add((ms, slot["mappings"], r))
        records.add((r, RDF.type, OWL.Axiom))
        records.add((r, slot["subject_id"], e))
        records.add((r, slot["subject_label"], Literal(labels[e])))
        records.add((r, slot["subject_type"], SKOS.Concept))
        records.add((r, slot["predicate_id"], PREDICATE))
        records.add((r, slot["predicate_label"], Literal("mapped to")))
        records.add((r, slot["object_id"], USDM[x["object"]]))
        records.add((r, slot["object_label"], Literal(x["object"])))
        records.add((r, slot["object_type"], otype_iri[usdm.kind[x["object"]]]))
        records.add((r, slot["mapping_justification"], JUSTIFICATION))
        records.add((r, slot["subject_match_field"], M11.ichConceptCode if x["method"] == "by-code" else M11.tsTerm))
        records.add((r, slot["match_string"], Literal(x["NCIt Code"] if x["method"] == "by-code" else x["ElementName"])))
        records.add((r, slot["mapping_source"], URIRef(URL[file_of[x["source"]]])))
        records.add((r, slot["author_label"], Literal(author[x["source"]])))
        for name, prop, hint in EXTENSIONS:
            v = ext_values(x)[name]
            records.add((r, prop, v if isinstance(v, URIRef) else Literal(v, datatype=hint if hint != XSD.string else None)))
    for t in records:
        s.add(t)
    s.serialize(ROOT / "m11-usdm.sssom.ttl", format="turtle")

    # Whole graph: D1 plus the records (without extension definitions) and the direct triples.
    out = relabel_specs(g)
    for p, ns in [("usdm", USDM), ("m11map", MAP), ("sssom", SSSOM), ("semapv", SEMAPV)]:
        out.bind(p, ns)
    onto = URIRef(str(M11))
    for t in records:
        out.add(t)
    out.add((ms, RDF.type, SSSOM.MappingSet))
    out.add((ms, slot["mapping_set_title"], Literal(meta["mapping_set_title"])))
    out.add((ms, slot["mapping_set_version"], Literal(VERSION)))
    out.add((onto, DCTERMS.hasPart, ms))
    for x in statements:
        out.add((x["elements"][0], PREDICATE, USDM[x["object"]]))
    out.serialize(ROOT / "m11-rdf.ttl", format="turtle")


def relabel_specs(g):
    """Copy of g with each specification's blank node labelled spec<TS block>, as build_d1 writes them."""
    label = {s: BNode(f"spec{g.value(s, M11.tsBlock)}") for s in g.subjects(RDF.type, M11.Specification)}
    if any(isinstance(x, BNode) and x not in label for t in g for x in t):
        raise RuntimeError("Blank nodes other than one per specification in m11-rdf.ttl")
    out = Graph()
    for prefix, ns in g.namespaces():
        out.bind(prefix, ns)
    for s, p, o in g:
        out.add((label.get(s, s), p, label.get(o, o)))
    return out


def write_reports(records, statements, elements, usdm):
    REPORTS.mkdir(exist_ok=True)
    fields = ["source", "row", "section", "element_name", "ncit_code", "identification", "elements", "note",
              "stated_class", "stated_attribute", "object", "object_resolution", "flags", "status"]

    def flat(x):
        return {"source": x["source"], "row": x["row"], "section": x["Section Number"] or x["Section Title"],
                "element_name": one_line(x["ElementName"]), "ncit_code": one_line(x["NCIt Code"]),
                "identification": x["method"], "elements": ";".join(local(e) for e in x["elements"]),
                "note": x["note"], "stated_class": x["Class"], "stated_attribute": x["Attribute"],
                "object": x["object"] or "", "object_resolution": x["how"], "flags": "; ".join(x["flags"]),
                "status": x["status"]}
    with open(REPORTS / "d2-identification.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(flat(x) for x in records)
    residue = [x for x in records if x["status"] == "residue" or x["flags"]]
    with open(REPORTS / "d2-residue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["category"] + fields)
        w.writeheader()
        for x in residue:
            w.writerow({"category": residue_category(x), **flat(x)})

    lines = [
        "# D2: identification of the mapping rows",
        "",
        "Generated by `scripts/build_d2.py`. Do not edit by hand. Every D2 count in the documentation comes from here or from `scripts/test_d2.py`. Per row: `reports/d2-identification.csv`; rows without a statement and flagged statements: `reports/d2-residue.csv`.",
        "",
        "## Rows and statements",
        "",
        "| | " + " | ".join(s["key"] for s in SOURCES) + " |",
        "| --- | " + " | ".join("---" for _ in SOURCES) + " |",
    ]

    def row(label, f):
        return f"| {label} | " + " | ".join(str(f([x for x in records if x["source"] == s["key"]])) for s in SOURCES) + " |"
    lines += [
        row("mapping rows", len),
        row("statements", lambda xs: sum(x["status"] == "statement" for x in xs)),
        row("rows without a statement", lambda xs: sum(x["status"] == "residue" for x in xs)),
        row("statements flagged", lambda xs: sum(x["status"] == "statement" and bool(x["flags"]) for x in xs)),
        row("elements with a statement", lambda xs: len({x["elements"][0] for x in xs if x["status"] == "statement"})),
        row("USDM targets in statements", lambda xs: len({x["object"] for x in xs if x["status"] == "statement"})),
        "",
        "## Identification of the M11 side",
        "",
        "| | " + " | ".join(s["key"] for s in SOURCES) + " |",
        "| --- | " + " | ".join("---" for _ in SOURCES) + " |",
    ]
    for m in ["by-code", "by-unique-name", "ambiguous-code", "ambiguous-name", "unidentified"]:
        lines.append(row(m, lambda xs, m=m: sum(x["method"] == m for x in xs)))
    lines += [
        row("by-code where the row's section decides", lambda xs: sum(x["method"] == "by-code" and bool(x["note"]) for x in xs)),
        "",
        "## USDM target",
        "",
        "| | " + " | ".join(s["key"] for s in SOURCES) + " |",
        "| --- | " + " | ".join("---" for _ in SOURCES) + " |",
    ]
    for h in sorted({x["how"] for x in records}):
        lines.append(row(h, lambda xs, h=h: sum(x["how"] == h for x in xs)))
    lines += [
        "",
        "## Residue by category (input for usdm-overlay layer 4)",
        "",
        "| | " + " | ".join(s["key"] for s in SOURCES) + " |",
        "| --- | " + " | ".join("---" for _ in SOURCES) + " |",
    ]
    for c in sorted({residue_category(x) for x in residue}):
        lines.append(row(c, lambda xs, c=c: sum((x["status"] == "residue" or bool(x["flags"])) and residue_category(x) == c for x in xs)))

    # The two sources per element and per (section, name) key.
    per = defaultdict(lambda: defaultdict(set))
    for x in statements:
        per[x["elements"][0]][x["source"]].add(x["object"])
    a, b = SOURCES[0]["key"], SOURCES[1]["key"]
    both = [e for e in per if per[e][a] and per[e][b]]
    keyed = defaultdict(lambda: defaultdict(list))
    for x in records:
        keyed[(x["Section Number"], x["ElementName"])][x["source"]].append(x)
    shared = [k for k in keyed if keyed[k][a] and keyed[k][b]]

    def differs(k, f):
        return sorted(f(x) for x in keyed[k][a]) != sorted(f(x) for x in keyed[k][b])
    lines += [
        "",
        "## The two mappings compared",
        "",
        "| | Count |",
        "| --- | --- |",
        f"| elements with statements from both | {len(both)} |",
        f"| of which the same USDM targets | {sum(per[e][a] == per[e][b] for e in both)} |",
        f"| elements with statements from {a} only | {sum(1 for e in per if per[e][a] and not per[e][b])} |",
        f"| elements with statements from {b} only | {sum(1 for e in per if per[e][b] and not per[e][a])} |",
        f"| D1 elements without a statement | {len(elements) - len(per)} |",
        f"| (section number, element name) keys in both files | {len(shared)} |",
        f"| keys in {a} only | {sum(1 for k in keyed if keyed[k][a] and not keyed[k][b])} |",
        f"| keys in {b} only | {sum(1 for k in keyed if keyed[k][b] and not keyed[k][a])} |",
        f"| shared keys whose NCIt Code differs | {sum(differs(k, lambda x: x['NCIt Code']) for k in shared)} |",
        f"| shared keys whose Class and Attribute differ | {sum(differs(k, lambda x: (x['Class'], x['Attribute'])) for k in shared)} |",
        f"| shared keys whose Target Path differs | {sum(differs(k, lambda x: one_line(x['Target Path'])) for k in shared)} |",
        f"| shared keys whose Condition Path differs | {sum(differs(k, lambda x: one_line(x['Condition Path'])) for k in shared)} |",
        "",
        "Keys are compared as sets of rows: a key can have several rows in a file.",
        "",
        "## Rules",
        "",
        "- By code: the NCIt Code cell is one C-code and the concept of one D1 element. If it is the concept of elements in several namespaces, the row's Section Number (or Section Title when the number is empty) decides against the elements' ToC references, X and # read as any number.",
        "- By unique name: otherwise, the ElementName normalised (lower case; punctuation, brackets and quotes to spaces; white space collapsed) equals the normalised term of exactly one Technical Specification element block.",
        "- USDM target: Class and Attribute looked up in usdm-rdf, as a property of the class or of a superclass, by attribute name or by usdm:modelName (the relationship role name); the statement's object is that property. Nothing is repaired.",
        "- A by-code row whose element name identifies another element uniquely gets no statement.",
        "- Flag on a statement: the row's Section Number does not match any ToC reference of the element.",
    ]
    (REPORTS / "d2-identification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def residue_category(x):
    if x["status"] == "statement":
        return "statement flagged: " + "; ".join(f.split(" identifies ")[0] for f in x["flags"])
    if x["method"] not in ("by-code", "by-unique-name"):
        return x["method"] + ("" if x["Class"] else ", no target")
    if any(f.startswith("unique name identifies") for f in x["flags"]):
        return "code and unique name identify different elements"
    if not x["Class"]:
        return "identified, no target"
    return "identified, target: " + re.sub(r" [A-Z]\w+(, [A-Z]\w+)*$", "", x["how"])


if __name__ == "__main__":
    main()
