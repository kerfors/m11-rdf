"""Shared paths, namespaces and input loading for m11-rdf scripts.

Every input is read from downloads/ and checked against the SHA-256 fixed in
fetch_inputs.py before use; a mismatch stops the script.
"""
import csv
import hashlib
import json
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from rdflib import Namespace

from fetch_inputs import INPUTS

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
BUILD = ROOT / "build"
REPORTS = ROOT / "reports"

M11 = Namespace("https://w3id.org/m11-rdf/")
EVS = Namespace("http://rdf.ich.org/ich-terminology#")
NCIT = Namespace("http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#")
OBO = Namespace("http://purl.obolibrary.org/obo/")

TS_PDF = "ich/ICH_Step4_M11_Final_TechnicalSpecification_2025_1119.pdf"
TS_TXT_SHA256 = "b682a9a7e16c4d88339ae874c53a54424e4481e77df31f2dfda1c9b0a9a85267"
TEMPLATE_PDF = "ich/ICH_Step4_M11_Final_Template_2025_1119.pdf"
TEMPLATE_JSON_SHA256 = "c122d6d2b6184d27a33be0a60b1dc55ea0b79e926e827dfa76a9be3f3d0512e8"
EVS_TXT = "evs/ICH M11 Terminology 2025-12-19.txt"
EVS_OWL_ZIP = "evs/ICH M11 Terminology 2025-12-19.OWL.zip"
EVS_OWL_MEMBER = "ICH M11 Terminology.owl"
ICH_ZIP = "ich/M11_code_lists_1.zip"
OID_LISTING_MEMBER = "M11_code_lists/2025-10-16 ICH M11 OID Listing.pdf"
GC = "{http://docs.oasis-open.org/codelist/ns/genericode/1.0/}"

SECTION_CODELIST = "C217272"
OID_ROOT = "2.16.840.1.113883.3.989.2.3"


def checked(name):
    """Return the path of a pinned input after verifying its SHA-256."""
    expected = {item["name"]: item["sha256"] for item in INPUTS}[name]
    path = DOWNLOADS / name
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")
    return path


def ts_text():
    """pdftotext -layout of the Technical Specification, checked against the pinned text hash."""
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "ts.txt"
    subprocess.run(["pdftotext", "-layout", str(checked(TS_PDF)), str(out)], check=True)
    actual = hashlib.sha256(out.read_bytes()).hexdigest()
    if actual != TS_TXT_SHA256:
        raise RuntimeError(f"pdftotext output differs from the pinned text (SHA-256 {actual}); check the poppler version")
    return out.read_text(encoding="utf-8")


def evs_rows():
    with open(checked(EVS_TXT), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    header = ["Code", "Codelist Code", "Codelist Extensible (Yes/No)", "Codelist Name",
              "ICH Preferred Term", "ICH Synonym(s)", "ICH Definition", "NCI Preferred Term"]
    if list(rows[0].keys()) != header:
        raise RuntimeError(f"Unexpected EVS header: {list(rows[0].keys())}")
    return rows


def evs_owl_bytes():
    with zipfile.ZipFile(checked(EVS_OWL_ZIP)) as z:
        return z.read(EVS_OWL_MEMBER)


def genericode_lists():
    """Code list C-code -> {oid, version_oid, name} from the 39 Genericode files."""
    out = {}
    with zipfile.ZipFile(checked(ICH_ZIP)) as z:
        for member in sorted(n for n in z.namelist() if n.endswith(".xml")):
            root = ET.fromstring(z.read(member))
            ident = root.find("Identification")
            code = ident.find("Agency/Identifier").text.strip()
            if code in out:
                raise RuntimeError(f"Duplicate Genericode list {code}")
            out[code] = {
                "oid": ident.find("CanonicalUri").text.strip(),
                "version_oid": ident.find("CanonicalVersionUri").text.strip(),
                "name": ident.find("LongName").text.strip(),
                "member": member,
                "codes": [row.find("Value[@ColumnRef='code']/SimpleValue").text.strip()
                          for row in root.iter("Row")],
            }
    return out


def oid_listing():
    """Code list C-code -> OID from the ICH OID Listing PDF (pdftotext)."""
    BUILD.mkdir(exist_ok=True)
    pdf = BUILD / "oid_listing.pdf"
    with zipfile.ZipFile(checked(ICH_ZIP)) as z:
        pdf.write_bytes(z.read(OID_LISTING_MEMBER))
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                         capture_output=True, text=True).stdout
    out = {}
    for m in re.finditer(r"(C\d{5,6})\s+\d+\s+(" + re.escape(OID_ROOT) + r"\.[13]\.\d+)", txt):
        if m.group(1) in out:
            raise RuntimeError(f"Duplicate OID Listing row for {m.group(1)}")
        out[m.group(1)] = m.group(2)
    return out


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
