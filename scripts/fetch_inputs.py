"""Fetch the pinned inputs of m11-rdf into downloads/ and write the manifest.

Every input has a fixed URL and an expected SHA-256. A download is written to
<name>.part, checked, and only then renamed to <name>. A mismatch stops the
script and leaves the .part file for inspection. NCI EVS answers a wrong file
name with HTTP 200 and an HTML page, so the status code proves nothing; the
checksum does.

Re-running replaces the files and the manifest.
"""
import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"

EVS = "https://evs.nci.nih.gov/ftp1/ICH/M11/Archive/"
ICH = "https://database.ich.org/sites/default/files/"

INPUTS = [
    {
        "name": "evs/ICH M11 Terminology 2025-12-19.txt",
        "url": EVS + "ICH%20M11%20Terminology%202025-12-19.txt",
        "source": "NCI EVS, ICH M11 Terminology, release 2025-12-19 (dated archive)",
        "terms": "CC BY 4.0",
        "sha256": "9fc91bf836cd1e6bf510d7321921d30ca9db57d521f4292fba7597e9188450a9",
    },
    {
        "name": "evs/ICH M11 Terminology 2025-12-19.OWL.zip",
        "url": EVS + "ICH%20M11%20Terminology%202025-12-19.OWL.zip",
        "source": "NCI EVS, ICH M11 Terminology, release 2025-12-19 (dated archive)",
        "terms": "CC BY 4.0",
        "sha256": "4f700c13fb8e0bcb29f60851aeaa15a38e31ff76b0f0ac80e5d98de52c4fccf1",
    },
    {
        "name": "ich/ICH_Step4_M11_Final_TechnicalSpecification_2025_1119.pdf",
        "url": ICH + "ICH_Step4_M11_Final_TechnicalSpecification_2025_1119.pdf",
        "source": "ICH M11 Technical Specification, Step 4, 2025-11-19",
        "terms": "ICH copyright, ICH Legal Mentions",
        "sha256": "57b8bf8edf32bf359a90a8632f0d771e7956fac5083f2f3a31350a47520e7691",
    },
    {
        "name": "ich/M11_code_lists_1.zip",
        "url": "https://admin.ich.org/sites/default/files/inline-files/3.M11_code_lists_1.zip",
        "source": "ICH Step 4 M11 Package 1.0, November 2025 (Genericode code lists, OID Listing 2025-10-16)",
        "terms": "ICH copyright, ICH Legal Mentions",
        "sha256": "c988f16a7cc2880f3d00f0188a414407bdb0a17d4e15b4a22fee66ce317f7de8",
    },
    {
        "name": "hl7/M11 to FHIR Mapping 02.xlsx",
        "url": "https://hl7.org/fhir/uv/clinical-study-protocol/2026May/en/Mappings/M11%20to%20FHIR%20Mapping%2002.xlsx",
        "source": "HL7 FHIR Clinical Study Protocol IG, STU 1 ballot, May 2026",
        "terms": "Licenses sheet in the file; HL7 terms to be checked before v0.2.0",
        "sha256": "7781cc6eed97363b389045f15d5e029e02d3938269a0643e136f0e648bf7b93e",
    },
    {
        "name": "cdisc/m11_mapping.xlsx",
        "url": "https://raw.githubusercontent.com/cdisc-org/DDF-RA/v4.0.0/Documents/Mappings/m11_mapping.xlsx",
        "source": "CDISC DDF-RA, tag v4.0.0 (commit aa303cb32f5d3ceecc68a16803e26720d2c1fc26)",
        "terms": "CC BY 4.0 (DDF-RA content)",
        "sha256": "82f35cfdd37628dfe8415ed4324303eb9c452e534f8aaea0002d31519f5ae341",
    },
    {
        "name": "usdm-rdf/usdm_v4.ttl",
        "url": "https://raw.githubusercontent.com/kerfors/usdm-rdf/v0.7.1/usdm_v4.ttl",
        "source": "kerfors/usdm-rdf, tag v0.7.1 (commit da86062db2bacb01d5725ad000a8f1c5118aebfd)",
        "terms": "CC BY 4.0",
        "sha256": "7c6c7b2f79ecc9908a5b7cc7f75011a93245b34c54713d7ee9a19b00dc261deb",
    },
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(item):
    target = DOWNLOADS / item["name"]
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    urllib.request.urlretrieve(item["url"], part)
    actual = sha256(part)
    if actual != item["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {item['name']}\n"
            f"  url:      {item['url']}\n"
            f"  expected: {item['sha256']}\n"
            f"  actual:   {actual}\n"
            f"  bytes:    {part.stat().st_size}\n"
            f"  kept as:  {part}"
        )
    part.replace(target)


def main():
    for item in INPUTS:
        fetch(item)
    lines = [
        "# Pinned inputs",
        "",
        "Written by `scripts/fetch_inputs.py` after every checksum matched. Do not edit by hand.",
        "The expected SHA-256 values are fixed in the script; a mismatch stops the fetch.",
        "",
        "| File | Source | Terms | URL | SHA-256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in INPUTS:
        lines.append(
            f"| `{item['name']}` | {item['source']} | {item['terms']} | <{item['url']}> | `{item['sha256']}` |"
        )
    (DOWNLOADS / "MANIFEST.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
