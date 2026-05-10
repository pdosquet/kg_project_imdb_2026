"""
preprocess.py

Generates a small set of CSV lookups for the YARRRML mappings, covering
the four transformations that pure RML/YARRRML cannot express:

  1. Composite-key join (category_id, job) -> title_principal_resolved.csv
  2. Set membership / anti-join             -> title_structure_lookup.csv,
                                               region_iso_lookup.csv
  3. String explosion of multi-valued cells -> characters.csv

Everything else (\\N filtering, language ISO branching, season synthesis,
region X-code resolution) is now handled directly in YARRRML using
idlab-fn / grel functions and conditional POs.
"""

import csv
import urllib.parse
from pathlib import Path

SRC  = Path("data")
SEED = Path("data/seeded")
GEN  = Path("data/generated")
GEN.mkdir(exist_ok=True)

CW   = "https://example.org/culturalworks/ontology#"
FILM = "https://example.org/culturalworks/film#"
IMDB = "https://example.org/culturalworks/imdb#"
BASE = "https://example.org/culturalworks/"

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def is_null(val):
    return not val or val == r"\N"

# ── Validate seeded files exist ────────────────────────────────────────────

SEEDED_REQUIRED = [
    "role_lookup.csv",
    "content_type_lookup.csv",
    "title_type_lookup.csv",
    "additional_attrs_lookup.csv",
    "contribution_role_lookup.csv",
    "region_xcode_lookup.csv",
    "region_sameAs.csv",
]

for fname in SEEDED_REQUIRED:
    if not (SEED / fname).exists():
        raise FileNotFoundError(f"Missing seeded file: data/seeded/{fname}")

print("Seeded files: all present")
print()

# ================================================================
# PART 0: Strip \N from title_principal.csv only.
# title_principal_resolved.csv (Part 4) is keyed on (category, job),
# and the join needs job="" (not "\N") to match the seeded fallback
# rows. The other IMDB CSVs are now read raw by YARRRML, which
# filters \N via idlab-fn:notEqual conditions on each PO.
# ================================================================

src = SRC / "title_principal.csv"
dst = GEN / "title_principal.csv"
rows = read_csv(src)
cleaned = [
    {k: ("" if is_null(v) else v) for k, v in row.items()}
    for row in rows
]
fieldnames = list(rows[0].keys()) if rows else []
write_csv(dst, fieldnames, cleaned)
nulls = sum(1 for row in rows for v in row.values() if v == r"\N")
print(f"0. generated/title_principal.csv — stripped {nulls} \\N markers")
print()

# ================================================================
# PART 1: Title structural class lookup
# ================================================================

SERIES_CONTENT_TYPES = {"4", "7"}

episodes   = read_csv(SRC / "title_episode.csv")
series_ids = {r["parent_title_id"] for r in episodes}
unit_ids   = {r["title_id"]        for r in episodes}
all_titles = read_csv(SRC / "title.csv")

title_structure = []
fallback = []

for row in all_titles:
    tid, ct = row["title_id"], row["content_type_id"]
    if ct == "10":
        continue
    if tid in series_ids:
        class_iri = CW + "WorkSeries"
    elif tid in unit_ids:
        class_iri = CW + "WorkUnit"
    elif ct in SERIES_CONTENT_TYPES:
        class_iri = CW + "WorkSeries"
        fallback.append(tid)
    else:
        class_iri = CW + "CreativeWork"
    title_structure.append({"title_id": tid, "class_iri": class_iri})

write_csv(GEN / "title_structure_lookup.csv", ["title_id", "class_iri"], title_structure)

counts = {}
for r in title_structure:
    label = r["class_iri"].split("#")[1]
    counts[label] = counts.get(label, 0) + 1

print("1. generated/title_structure_lookup.csv")
for label, n in sorted(counts.items()):
    print(f"   cw:{label}: {n}")
if fallback:
    print(f"   Fallback (IMDB label, no episodes): {fallback}")
print()

# ================================================================
# PART 2: Character explosion
# ================================================================

characters = []

for row in read_csv(GEN / "title_principal.csv"):
    if is_null(row["role_names"]):
        continue
    for name in [n.strip() for n in row["role_names"].split(",") if n.strip()]:
        characters.append({
            "title_id":       row["title_id"],
            "talent_id":      row["talent_id"],
            "join_key":       row["title_id"] + "_" + row["talent_id"],
            "character_name": name,
            "character_iri":  BASE + "character/" + row["title_id"] + "/" + urllib.parse.quote(name, safe=""),
        })

write_csv(GEN / "characters.csv",
          ["title_id", "talent_id", "join_key", "character_name", "character_iri"],
          characters)

multi = sum(1 for r in read_csv(GEN / "title_principal.csv")
            if not is_null(r["role_names"]) and "," in r["role_names"])
print(f"2. generated/characters.csv — {len(characters)} rows ({multi} multi-valued exploded)")
print()

# ================================================================
# PART 3 (deleted): Season synthesis is now done directly in
# 07_title_episode.yarrrml using template subjects and -d dedup.
# ================================================================

# ================================================================
# PART 4: Role resolution for title_principal
# Reads seeded/contribution_role_lookup.csv
# ================================================================

role_resolution = {
    (r["category_id"], r["job"]): r["role_iri"]
    for r in read_csv(SEED / "contribution_role_lookup.csv")
}

rows_out, unresolved = [], []

for row in read_csv(GEN / "title_principal.csv"):
    cat = row["category_id"]
    job = "" if is_null(row["job"]) else row["job"]
    row["join_key"] = row["title_id"] + "_" + row["talent_id"]
    role_iri = role_resolution.get((cat, job)) or role_resolution.get((cat, ""), "")
    if not role_iri:
        unresolved.append((row["title_id"], row["talent_id"], cat, job))
    row["resolved_role_iri"] = role_iri
    rows_out.append(row)

write_csv(GEN / "title_principal_resolved.csv", list(rows_out[0].keys()), rows_out)

print(f"5. generated/title_principal_resolved.csv — {len(rows_out)} rows")
if unresolved:
    print(f"   WARNING: {len(unresolved)} rows unresolved:")
    for r in unresolved:
        print(f"     title={r[0]}, talent={r[1]}, cat={r[2]}, job={r[3]!r}")
else:
    print("   All (category_id, job) combinations resolved cleanly.")
print()

# ================================================================
# PART 5: Region resolution
# Reads seeded/region_xcode_lookup.csv
# ================================================================

xcode_map = {
    r["region_code"]: r["region_iri"]
    for r in read_csv(SEED / "region_xcode_lookup.csv")
}

aka_rows     = read_csv(SRC / "title_aka.csv")
region_codes = {r["region"] for r in aka_rows if not is_null(r["region"])}

iso_lookup = []

for code in sorted(region_codes):
    if code not in xcode_map:
        iso_lookup.append({
            "region_code": code,
            "region_iri":  BASE + "region/" + urllib.parse.quote(code, safe=""),
        })

write_csv(GEN / "region_iso_lookup.csv", ["region_code", "region_iri"], iso_lookup)
print(f"6. generated/region_iso_lookup.csv — {len(iso_lookup)} ISO codes")
print(f"   (X-codes are read directly from data/seeded/region_xcode_lookup.csv)")
print()

# ================================================================
# PART 6 (deleted): Language lookup is now derived directly in
# 09_language.yarrrml from data/title_aka.csv via grel:string_substring
# branching for ISO 639-1 vs 639-3 Lexvo paths.
# ================================================================

# ================================================================
# PART 7: Validate seeded lookups against source data
# PART 6: Validate seeded lookups against source data
# ================================================================

print("Validating seeded lookups...")

def check(label, seeded_keys, data_keys, intentionally_excluded=None):
    excluded = intentionally_excluded or set()
    missing = (data_keys - seeded_keys) - excluded
    if missing:
        print(f"   WARNING {label}: values in data with no mapping: {missing}")
    else:
        note = f" ({', '.join(excluded)} intentionally excluded)" if excluded else ""
        print(f"   {label}: all {len(data_keys - excluded)} values covered{note}")

role_ids  = {r["role_id"] for r in read_csv(SRC / "talent_role.csv")} - {"role_id"}
role_keys = {r["role_id"] for r in read_csv(SEED / "role_lookup.csv")}
check("role_lookup", role_keys, role_ids)

ct_ids  = {r["content_type_id"] for r in read_csv(SRC / "title.csv")} - {"content_type_id"}
ct_keys = {r["content_type_id"] for r in read_csv(SEED / "content_type_lookup.csv")}
check("content_type_lookup", ct_keys, ct_ids, intentionally_excluded={"10"})

tt_ids  = {r["title_type_id"] for r in read_csv(SRC / "title_aka_title_type.csv")} - {"title_type_id"}
tt_keys = {r["title_type_id"] for r in read_csv(SEED / "title_type_lookup.csv")}
check("title_type_lookup", tt_keys, tt_ids, intentionally_excluded={"2"})

aa_vals = {r["additional_attrs"] for r in aka_rows if not is_null(r["additional_attrs"])}
aa_keys = {r["additional_attrs"] for r in read_csv(SEED / "additional_attrs_lookup.csv")}
check("additional_attrs_lookup", aa_keys, aa_vals)

cr_keys = {(r["category_id"], r["job"]) for r in read_csv(SEED / "contribution_role_lookup.csv")}
tp_combos = {
    (r["category_id"], "" if is_null(r["job"]) else r["job"])
    for r in read_csv(GEN / "title_principal.csv")
} - {("category_id", "job")}
check("contribution_role_lookup", cr_keys, tp_combos)

print()
print("Done. Run YARRRML mappings referencing data/generated/ and data/seeded/ as needed.")
