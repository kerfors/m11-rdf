"""Parse Appendix 1 of the ICH M11 Technical Specification into component blocks.

Input: the pdftotext -layout text of the pinned Technical Specification
(common.ts_text). Output: build/ts_blocks.json, one dict per block in
document order, with the block number (1-based) and the labelled fields.

The parser is the Step 0 parser (575 blocks) with four changes, all to how
the layout text is read, none to the content:
- the label tail "from ToC representing the protocol hierarchy", which
  pdftotext places on the same line as some ToC values, is removed from the
  ToC field;
- the label tail "Reuse", placed on the same line as some Repeating and/or
  Reuse Rules values, is removed from that field;
- a document section heading that follows a block (section number, then a
  wide gap) ends the block instead of being appended to its last field;
- the label "<Conformance" printed once in the PDF is read as "Conformance"
  and recorded in the block as printed_label_variants. The block count and kinds are checked
in build_d1.py and test_d1.py.
"""
import re

from common import BUILD, ts_text, write_json

LABELS = [
    ("Term (Variable)", "term"),
    ("Data Type", "data_type"),
    ("Data (D), Value (V) or", "dvh"),
    ("Definition", "definition"),
    ("User Guidance", "user_guidance"),
    ("Conformance", "conformance"),
    ("Cardinality", "cardinality"),
    ("Relationship content", "toc"),
    ("Value", "value"),
    ("Business rules", "business_rules"),
    ("Repeating and/or", "repeat_reuse"),
]
LABEL_TAILS = ["Heading (H)", "from ToC representing", "the protocol hierarchy", "Reuse Rules", "Rules"]
# Labels printed differently in the PDF, accepted as the label and recorded on the block.
PRINTED_VARIANTS = {"<Conformance": "Conformance"}
TOC_TAIL = " from ToC representing the protocol hierarchy"
# A document section heading after a block: section number left of the value column, then a wide gap.
SECTION_LINE = re.compile(r"^ ?\d+(?:\.\d+)*\s{2,}\S")


def parse_blocks(text):
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip().startswith("APPENDIX 1"))
    blocks, cur, field, section = [], None, None, None
    for raw in lines[start + 1:]:
        line = raw.replace("\f", "")
        s = line.strip()
        if not s:
            continue
        if re.fullmatch(r"\d+", s):
            continue
        hit = None
        variant = None
        for printed, label in PRINTED_VARIANTS.items():
            if s.startswith(printed + " "):
                variant = printed
                s = label + s[len(printed):]
        for lab, key in LABELS:
            if s.startswith(lab) and (len(s) == len(lab) or s[len(lab)] == " "):
                hit = (lab, key)
                break
        if hit:
            lab, key = hit
            if key == "term":
                cur = {"block": len(blocks) + 1, "section_heading": section}
                blocks.append(cur)
            rest = s[len(lab):].strip()
            for t in LABEL_TAILS:
                if rest.startswith(t + "  ") or rest == t:
                    rest = rest[len(t):].strip()
            if key == "repeat_reuse" and re.match(r"Reuse\s{2,}", rest):
                rest = rest[len("Reuse"):].strip()
            cur[key] = rest
            if variant:
                cur.setdefault("printed_label_variants", []).append(variant)
            field = key
            continue
        if cur is None or line[:1] != " " and field is None:
            section = s
            continue
        left = line[:25].strip()
        right = line[25:].strip() if len(line) > 25 else ""
        if field == "repeat_reuse" and SECTION_LINE.match(line):
            section = s
            field = None
            continue
        if left in LABEL_TAILS or any(left.startswith(t) for t in LABEL_TAILS):
            txt = right
            for t in LABEL_TAILS:
                if s.startswith(t):
                    txt = s[len(t):].strip()
                    break
        elif not line.startswith(" ") and not left.startswith(("•", "o ")) and field == "repeat_reuse" and right == "":
            section = s
            field = None
            continue
        else:
            txt = s
        if field and txt:
            cur[field] = (cur.get(field, "") + " " + txt).strip()
    for b in blocks:
        if b["toc"].endswith(TOC_TAIL):
            b["toc"] = b["toc"][: -len(TOC_TAIL)]
    return blocks


def main():
    blocks = parse_blocks(ts_text())
    write_json(BUILD / "ts_blocks.json", blocks)
    print(len(blocks), "blocks")


if __name__ == "__main__":
    main()
