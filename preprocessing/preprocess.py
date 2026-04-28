"""
preprocess.py

Transforms IMDB source CSVs into files needed by the YARRRML mappings.
Must be run once before executing any mapping.

Folder structure
----------------
data/
  *.csv          — IMDB source data (read-only)
  seeded/        — Vocabulary lookups encoding M2 decisions. Edit manually.
  generated/     — Files produced by this script. Never edit manually.

Seeded files (inputs)
---------------------
  role_lookup.csv                role_id -> individual IRI
  content_type_lookup.csv        content_type_id -> WorkType individual IRI
  title_type_lookup.csv          title_type_id -> TitleTypeCategory IRI
  additional_attrs_lookup.csv    additional_attrs value -> individual IRI
  contribution_role_lookup.csv   (category_id, job) -> role individual IRI
  region_xcode_lookup.csv        IMDB X-code -> imdb: individual IRI
  region_sameAs.csv              imdb: individual -> external standard IRI

Generated files (outputs)
--------------------------
  title_structure_lookup.csv     title_id -> OWL class IRI
  characters.csv                 one row per character (exploded role_names)
  seasons.csv                    synthesised cw:WorkVolume individuals
  episode_volume_links.csv       episode title_id -> season IRI
  title_principal_resolved.csv   title_principal + resolved_role_iri column
  region_iso_lookup.csv          ISO 3166-1 code -> minted cw:Region IRI
  region_xcode_lookup.csv        X-code -> imdb: IRI (copy of seeded, for YARRRML)

Why preprocessing is needed
----------------------------
  1. No multi-column join in RML: role = f(category_id, job)
  2. No conditional IRI templates: ISO vs X-code regions
  3. No string splitting: multi-valued role_names
  4. No entity synthesis: seasons don't exist as source rows
"""

import csv
import urllib.parse
from pathlib import Path

SRC  = Path("data")
SEED = Path("data/seeded")
GEN  = Path("data/generated")
GEN.mkdir(exist_ok=True)

CW   = "http://localhost:3030/culturalworks/ontology#"
FILM = "http://localhost:3030/culturalworks/film#"
IMDB = "http://localhost:3030/culturalworks/imdb#"
BASE = "http://localhost:3030/culturalworks/"

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

for row in read_csv(SRC / "title_principal.csv"):
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

multi = sum(1 for r in read_csv(SRC / "title_principal.csv")
            if not is_null(r["role_names"]) and "," in r["role_names"])
print(f"2. generated/characters.csv — {len(characters)} rows ({multi} multi-valued exploded)")
print()

# ================================================================
# PART 3: Season synthesis + episode-volume links
# ================================================================

seasons_seen = set()
seasons, ep_vol_links = [], []

for row in read_csv(SRC / "title_episode.csv"):
    season, episode = row["season_number"], row["episode_number"]
    if is_null(season):
        continue
    key        = (row["parent_title_id"], season)
    season_iri = BASE + "season/" + row["parent_title_id"] + "/S" + season
    if key not in seasons_seen:
        seasons_seen.add(key)
        seasons.append({
            "parent_title_id": row["parent_title_id"],
            "season_number":   season,
            "season_iri":      season_iri,
            "series_iri":      BASE + "title/" + row["parent_title_id"],
        })
    ep_vol_links.append({
        "title_id":       row["title_id"],
        "season_iri":     season_iri,
        "episode_number": "" if is_null(episode) else episode,
    })

write_csv(GEN / "seasons.csv",
          ["parent_title_id", "season_number", "season_iri", "series_iri"], seasons)
write_csv(GEN / "episode_volume_links.csv",
          ["title_id", "season_iri", "episode_number"], ep_vol_links)

total = len(read_csv(SRC / "title_episode.csv"))
print(f"3. generated/seasons.csv — {len(seasons)} synthesised seasons")
print(f"4. generated/episode_volume_links.csv — {len(ep_vol_links)} episodes with known season")
print(f"   Episodes with null season_number (no volume): {total - len(ep_vol_links)}")
print()

# ================================================================
# PART 4: Role resolution for title_principal
# Reads seeded/contribution_role_lookup.csv
# ================================================================

role_resolution = {
    (r["category_id"], r["job"]): r["role_iri"]
    for r in read_csv(SEED / "contribution_role_lookup.csv")
}

rows_out, unresolved = [], []

for row in read_csv(SRC / "title_principal.csv"):
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

iso_lookup, xcode_lookup = [], []

for code in sorted(region_codes):
    if code in xcode_map:
        xcode_lookup.append({"region_code": code, "region_iri": xcode_map[code]})
    else:
        iso_lookup.append({
            "region_code": code,
            "region_iri":  BASE + "region/" + urllib.parse.quote(code, safe=""),
        })

write_csv(GEN / "region_iso_lookup.csv",   ["region_code", "region_iri"], iso_lookup)
write_csv(GEN / "region_xcode_lookup.csv", ["region_code", "region_iri"], xcode_lookup)

print(f"6. generated/region_iso_lookup.csv — {len(iso_lookup)} ISO codes")
print(f"7. generated/region_xcode_lookup.csv — {len(xcode_lookup)} X-codes")
print()

# ================================================================
# PART 6: Language lookup
# Mints cw:Language individuals only for codes that appear
# in title_aka. language.csv language_name is 100% null.
# ================================================================

language_codes = {
    r["language"] for r in aka_rows
    if not is_null(r["language"])
}

def lexvo_iri(code):
    # ISO 639-1 codes are 2 characters; ISO 639-3 are 3 characters.
    # Lexvo uses different paths for each standard.
    if len(code) == 2:
        return f"http://lexvo.org/id/iso639-1/{code}"
    else:
        return f"http://lexvo.org/id/iso639-3/{code}"

language_lookup = [
    {
        "language_code": code,
        "language_iri":  BASE + "language/" + urllib.parse.quote(code, safe=""),
        "lexvo_iri":     lexvo_iri(code),
    }
    for code in sorted(language_codes)
]

write_csv(GEN / "language_lookup.csv",
          ["language_code", "language_iri", "lexvo_iri"],
          language_lookup)
print(f"8. generated/language_lookup.csv --- {len(language_lookup)} codes")
iso1 = sum(1 for r in language_lookup if len(r["language_code"]) == 2)
iso3 = sum(1 for r in language_lookup if len(r["language_code"]) == 3)
print(f"   ISO 639-1 codes: {iso1}, ISO 639-3 codes: {iso3}")
print()

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
    for r in read_csv(SRC / "title_principal.csv")
} - {("category_id", "job")}
check("contribution_role_lookup", cr_keys, tp_combos)

print()
print("Done. Run YARRRML mappings referencing data/generated/ and data/seeded/ as needed.")
