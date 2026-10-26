"""One HTML page for one SSSOM/TSV mapping set: the set metadata from the
# header, then every record as one table with the TSV columns in file order.

Cell values are shown as in the file. Links are added only for record_id
(to the record IRI), subject_id and object_id (to their IRIs), expanded with
the set's own curie_map. Each row's id is the record_id's local part with
"/" replaced by "-" (m11map:hl7/3 -> hl7-3). A small inline script sorts by
a clicked column, filters on typed text, and keeps only rows whose column
equals a query parameter of the same name (?subject_id=m11:C217356.C132346).
Without the script the whole table is shown.

Used by build_site.py for m11-usdm.sssom.tsv. Standalone for any other set:
    python mapping_view.py <set.sssom.tsv> <out.html>
"""
import csv
import html
import sys
from pathlib import Path

import yaml

LINKED = ["record_id", "subject_id", "object_id"]
CSS = """
#records td { white-space: nowrap; }
#records td.wrap { white-space: normal; min-width: 18rem; }
#records th { cursor: pointer; white-space: nowrap; }
#records tr:target td { background: var(--code); }
.filter { margin: 1rem 0 0.5rem; }
.filter input { font: inherit; padding: 0.2rem 0.4rem; width: 20rem; max-width: 100%; }
"""
WRAP = {"mapping_source", "author_label", "target_path", "condition_path", "subject_label", "object_label"}
SCRIPT = """
<script>
(function () {
  var table = document.getElementById("records");
  var body = table.tBodies[0];
  var rows = Array.prototype.slice.call(body.rows);
  var heads = table.tHead.rows[0].cells;
  var input = document.getElementById("filter");
  var count = document.getElementById("count");
  var exact = document.getElementById("exact");
  var params = new URLSearchParams(location.search);
  var wanted = [];
  for (var i = 0; i < heads.length; i++) {
    var v = params.get(heads[i].dataset.col);
    if (v !== null) { wanted.push([i, v]); }
  }
  if (wanted.length) {
    exact.innerHTML = "Showing rows where " + wanted.map(function (w) {
      return "<code>" + heads[w[0]].dataset.col + "</code> = <code>" + w[1].replace(/</g, "&lt;") + "</code>";
    }).join(" and ") + " · <a href=\\"" + location.pathname + "\\">show all rows</a>";
  }
  function apply() {
    var text = input.value.toLowerCase();
    var shown = 0;
    rows.forEach(function (r) {
      var ok = wanted.every(function (w) { return r.cells[w[0]].textContent === w[1]; })
        && (!text || r.textContent.toLowerCase().indexOf(text) !== -1);
      r.hidden = !ok;
      if (ok) { shown++; }
    });
    count.textContent = shown + " of " + rows.length + " rows";
  }
  var order = { col: -1, dir: 1 };
  Array.prototype.forEach.call(heads, function (th, i) {
    th.addEventListener("click", function () {
      order.dir = order.col === i ? -order.dir : 1;
      order.col = i;
      var numeric = rows.every(function (r) { var t = r.cells[i].textContent; return t === "" || !isNaN(t); });
      rows.sort(function (a, b) {
        var x = a.cells[i].textContent, y = b.cells[i].textContent;
        return order.dir * (numeric ? (Number(x) - Number(y)) : x.localeCompare(y));
      });
      rows.forEach(function (r) { body.appendChild(r); });
      Array.prototype.forEach.call(heads, function (h) { h.textContent = h.dataset.col; });
      th.textContent = th.dataset.col + (order.dir === 1 ? " \\u25b2" : " \\u25bc");
    });
  });
  input.addEventListener("input", apply);
  apply();
})();
</script>
"""


def esc(x):
    return html.escape(str(x))


def read_sssom_tsv(path):
    """Metadata (the # header as YAML), column names and rows of an SSSOM/TSV file."""
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    header = [l[1:] for l in lines if l.startswith("#")]
    data = [l for l in lines if l and not l.startswith("#")]
    if lines[:len(header)] != ["#" + h for h in header]:
        raise RuntimeError(f"{path}: # lines are not all at the top")
    meta = yaml.safe_load("\n".join(header))
    reader = csv.reader(data, delimiter="\t", quoting=csv.QUOTE_NONE)
    columns = next(reader)
    rows = list(reader)
    bad = [n for n, r in enumerate(rows, 1) if len(r) != len(columns)]
    if bad:
        raise RuntimeError(f"{path}: rows {bad[:5]} do not have {len(columns)} cells")
    return meta, columns, [dict(zip(columns, r)) for r in rows]


def expand(curie, curie_map):
    prefix, rest = curie.split(":", 1)
    return curie_map[prefix] + rest


def anchor(record_id):
    return record_id.split(":", 1)[1].replace("/", "-")


def value_html(v):
    if isinstance(v, list):
        return "<br>".join(value_html(x) for x in v)
    s = str(v)
    if s.startswith("http://") or s.startswith("https://"):
        return f'<a href="{esc(s)}">{esc(s)}</a>'
    return esc(s)


def render(path, files):
    """Title and body HTML for the set in path; files = [(label, href)] for the download line."""
    meta, columns, rows = read_sssom_tsv(path)
    curie_map = meta["curie_map"]
    ids = [anchor(r["record_id"]) for r in rows] if "record_id" in columns else []
    if len(set(ids)) != len(ids):
        raise RuntimeError(f"{path}: two records with one anchor")
    scalars = "".join(f"<dt>{esc(k)}</dt><dd>{value_html(v)}</dd>"
                      for k, v in meta.items() if k not in ("curie_map", "extension_definitions"))
    prefixes = "".join(f"<tr><td><code>{esc(k)}</code></td><td>{value_html(v)}</td></tr>" for k, v in curie_map.items())
    ext = meta.get("extension_definitions", [])
    ext_keys = list(dict.fromkeys(k for d in ext for k in d))
    ext_rows = "".join("<tr>" + "".join(f"<td><code>{esc(d.get(k, ''))}</code></td>" for k in ext_keys) + "</tr>" for d in ext)

    def cell(col, v):
        cls = ' class="wrap"' if col in WRAP else ""
        if col in LINKED and v:
            return f'<td{cls}><a href="{esc(expand(v, curie_map))}">{esc(v)}</a></td>'
        return f"<td{cls}>{esc(v)}</td>"
    body_rows = "".join(
        (f'<tr id="{esc(anchor(r["record_id"]))}">' if ids else "<tr>")
        + "".join(cell(c, r[c]) for c in columns) + "</tr>\n" for r in rows)
    downloads = " · ".join(f'<a href="{esc(h)}">{esc(l)}</a>' for l, h in files)
    body = f"""
<p>A mapping set in <a href="https://mapping-commons.github.io/sssom/">SSSOM</a> format: {len(rows)} records. This page shows the file as it is: the set metadata from its header, then one table row per record, columns in file order. Links are added to <code>record_id</code>, <code>subject_id</code> and <code>object_id</code>, expanded with the set's own prefixes.</p>
<p>Files: {downloads}</p>
<h2>Mapping set</h2>
<dl>{scalars}</dl>
<h2>Prefixes (curie_map)</h2>
<div class="table-wrap"><table><tr><th>Prefix</th><th>IRI</th></tr>{prefixes}</table></div>
{f'<h2>Extension slots (extension_definitions)</h2><div class="table-wrap"><table><tr>{"".join(f"<th>{esc(k)}</th>" for k in ext_keys)}</tr>{ext_rows}</table></div>' if ext else ''}
<h2>Records</h2>
<p class="muted">Click a column name to sort. Typing filters on any cell.</p>
<p id="exact"></p>
<p class="filter"><label>Filter <input id="filter" type="search"></label> <span id="count" class="muted">{len(rows)} rows</span></p>
<div class="table-wrap"><table id="records">
<thead><tr>{"".join(f'<th data-col="{esc(c)}">{esc(c)}</th>' for c in columns)}</tr></thead>
<tbody>
{body_rows}</tbody>
</table></div>
{SCRIPT}"""
    return str(meta.get("mapping_set_title", Path(path).name)), body


def main():
    from build_site import CSS as SITE_CSS
    source, target = sys.argv[1:3]
    meta, _, _ = read_sssom_tsv(source)
    title, body = render(source, [(Path(source).name, meta["mapping_set_id"])])
    Path(target).write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{SITE_CSS}{CSS}</style>
</head>
<body>
<main>
<h1>{esc(title)}</h1>
{body}
</main>
</body>
</html>
""", encoding="utf-8")


if __name__ == "__main__":
    main()
