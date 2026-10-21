"""Extract the headings and fields of the ICH M11 Template (Step 4, 2025-11-19).

Input: the pinned Template PDF. Output: build/template.json, checked against
the SHA-256 pinned in common.py (TEMPLATE_JSON_SHA256); a different PyMuPDF
or MuPDF version that reads the PDF differently stops the build.

The PDF is tagged. PyMuPDF (TEXT_COLLECT_STRUCTURE) returns the tag tree with
the styled text inside it, so one pass gives both:
- structure from the tags: headings from H1-H4, text units from the block
  tags (P, LBody, Lbl; a table cell TH or TD is one unit);
- the Template's conventions (its section 0.3) from the text colour:
  red = instructional text, blue = optional text, black = universal text.
Amendment Details is the one heading without a number; it is tagged P and
found by its exact text in bold.

Protocol content starts after "This is the end of the instructional
section". A field is a text insertion point <...> or a controlled-terminology
pick [...] of at least two characters, outside instructional text (the
numbering placeholder <#> is not a field). A field is optional when all its
non-instructional characters are blue, conditional when it stands inside
{...} in its text unit. A field in a table cell other than the first cell of
its row carries the text of that first cell (row_first_cell). Labels are the
text inside the brackets with line breaks and runs of white space as one
space.
"""
import hashlib
import json
import re
from collections import Counter

import pymupdf

from common import BUILD, TEMPLATE_JSON_SHA256, TEMPLATE_PDF, checked

RED = {0xC00000, 0xFF0000}
BLUE = {0x3333FF, 0x0000FF}
UNITS = {"H1", "H2", "H3", "H4", "P", "TH", "TD", "LBody", "Lbl", "TOCI", "Caption", "Note"}
HEADINGS = ("H1", "H2", "H3", "H4")
FLAGS = pymupdf.TEXTFLAGS_DICT | pymupdf.TEXT_COLLECT_STRUCTURE
END_OF_INSTRUCTIONS = "This is the end of the instructional section"
HEADING_RE = re.compile(r"^(\d+(?:\.\s?(?:\d+|X))*)\s+(\S.*)$")
FIELD_RE = re.compile(r"<([^<>]{2,200})>|\[([^\[\]]{2,200})\]")
SHORT_RE = re.compile(r"<[^<>]>|\[[^\[\]]\]")


def convention(span):
    if span["color"] in RED:
        return "instruction"
    if span["color"] in BLUE:
        return "optional"
    return "universal"


def text_units(doc, start):
    """Text units in reading order: tag, pages, and (character, convention, page, bold) per character."""
    units = {}

    def walk(block, path, pno):
        if block["type"] == 2:
            p = path + ((block["index"], block["std"]),)
            for b in block.get("blocks", []):
                walk(b, p, pno)
            return
        if block["type"] != 0:
            return
        cells = [i for i, (_, std) in enumerate(path) if std in ("TH", "TD")]
        key = path[:cells[0] + 1] if cells else path
        while key and key[-1][1] not in UNITS:
            key = key[:-1]
        if not key:
            raise RuntimeError(f"Page {pno + 1}: text outside any structure element: {block['lines'][0]['spans'][0]['text']!r}")
        rows = [i for i, (_, std) in enumerate(path) if std == "TR"]
        u = units.setdefault(key, {"tag": key[-1][1], "pages": [], "chars": [],
                                   "row": path[:rows[0] + 1] if cells and rows else None})
        if pno + 1 not in u["pages"]:
            u["pages"].append(pno + 1)
        for line in block["lines"]:
            if u["chars"] and u["chars"][-1][0] != " ":
                u["chars"].append((" ", "space", pno + 1, False))
            for s in line["spans"]:
                k = convention(s)
                for ch in s["text"]:
                    u["chars"].append((ch, k if ch.strip() else "space", pno + 1, "Bold" in s["font"]))

    for pno in range(start, len(doc)):
        for b in doc[pno].get_text("dict", flags=FLAGS)["blocks"]:
            if b["type"] == 0 and not "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip():
                continue
            if b["type"] == 0 and re.fullmatch(r"\d+", "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()):
                continue  # page number, not tagged
            walk(b, (), pno)
    return list(units.values())


def conventions(chars):
    return {k for _, k, _, _ in chars if k != "space"}


def one_space(s):
    return re.sub(r"\s+", " ", s).strip()


def parse(doc):
    start = next(i for i, p in enumerate(doc) if END_OF_INSTRUCTIONS in p.get_text()) + 1
    units = text_units(doc, start)
    first_cell = {}
    for u in units:
        if u["row"] is not None and u["row"] not in first_cell:
            first_cell[u["row"]] = u
    headings, fields, excluded = [], [], Counter()
    section = "Title Page"
    for u in units:
        text = one_space("".join(c[0] for c in u["chars"]))
        ks = conventions(u["chars"])
        if u["tag"] in HEADINGS:
            m = HEADING_RE.match(text)
            if not m:
                raise RuntimeError(f"Heading tag without a number: {text!r}")
            section = m.group(1).replace(" ", "")
            if len(section.split(".")) != int(u["tag"][1]):
                raise RuntimeError(f"Heading {section} tagged {u['tag']}")
            title = m.group(2)
            headings.append({"number": section, "title": title, "tag": u["tag"], "page": u["pages"][0],
                             "optional": ks == {"optional"},
                             "conditional": title.startswith("{") and title.endswith("}")})
            continue
        if u["tag"] == "P" and text.lower() == "amendment details" and all(b for ch, _, _, b in u["chars"] if ch.strip()):
            section = "Amendment Details"
            headings.append({"number": "Amendment Details", "title": text, "tag": "P", "page": u["pages"][0],
                             "optional": ks == {"optional"}, "conditional": False})
            continue
        if u["tag"] == "TOCI":
            continue
        raw = "".join(c[0] for c in u["chars"])
        excluded["single character (<#>)"] += len(SHORT_RE.findall(raw))
        for m in FIELD_RE.finditer(raw):
            ks = conventions(u["chars"][m.start():m.end()])
            if ks == {"instruction"}:
                excluded["inside instructional text"] += 1
                continue
            if "instruction" in ks:
                raise RuntimeError(f"Field mixed with instructional text: {m.group(0)!r}")
            before = "".join(c[0] for c in u["chars"][:m.start()] if c[1] != "instruction")
            fields.append({
                "order": len(fields) + 1,
                "page": u["chars"][m.start()][2],
                "section": section,
                "kind": "insert" if m.group(1) else "pick",
                "label": one_space(m.group(1) or m.group(2)),
                "optional": ks == {"optional"},
                "conditional": before.count("{") > before.count("}"),
                "unit_text": one_space("".join(c[0] for c in u["chars"] if c[1] != "instruction")),
                "row_first_cell": (one_space("".join(c[0] for c in first_cell[u["row"]]["chars"] if c[1] != "instruction"))
                              if u["row"] is not None and first_cell[u["row"]] is not u else ""),
            })
    return {"pdf_pages": len(doc), "protocol_pages": [start + 1, len(doc)],
            "pymupdf": pymupdf.pymupdf_version, "mupdf": pymupdf.mupdf_version,
            "excluded": dict(sorted(excluded.items())), "headings": headings, "fields": fields}


def main():
    doc = pymupdf.open(checked(TEMPLATE_PDF))
    data = parse(doc)
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "template.json"
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    actual = hashlib.sha256(out.read_bytes()).hexdigest()
    if actual != TEMPLATE_JSON_SHA256:
        raise RuntimeError(f"build/template.json differs from the pinned extraction (SHA-256 {actual}); "
                           f"PyMuPDF {pymupdf.pymupdf_version}, MuPDF {pymupdf.mupdf_version}")
    print(len(data["headings"]), "headings;", len(data["fields"]), "fields; excluded", data["excluded"])


if __name__ == "__main__":
    main()
