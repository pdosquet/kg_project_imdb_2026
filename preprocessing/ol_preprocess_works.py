#!/usr/bin/env python3
"""
ol_preprocess_works.py
======================
Prepare Open Library work and author data for RML mapping.

Produces four files in data/generated/:
  ol_work.csv           one row per OL work — RML-ready, flat
  ol_work_language.csv  one row per (work, language) — exploded
  ol_contribution.csv   one row per (work, author) — for BookContribution
  ol_sameas.csv         one row per confirmed owl:sameAs link (IMDB → OL)

Also reads:
  ol_worktype_lookup.csv  (seeded manually — see instructions below)

Usage:
    python3 ol_preprocess_works.py \
        --works   data/generated/ol_author_work.csv \
        --authors data/generated/ol_author.csv \
        --sameas  data/generated/ol_imdb_sameas_reviewed.csv \
        --outdir  data/generated

SEEDED FILE: ol_worktype_lookup.csv
------------------------------------
You must create this file manually before running the script.
Format: ol_work_key,work_type_iri
Example:
  OL4704007W,book:Essay
  OL18433354W,book:NonFiction
  OL27710705W,book:NonFiction
  OL43550980W,book:NonFiction
  OL42354098W,book:NonFiction
  ...
Valid values for work_type_iri:
  book:Novel, book:ShortStory, book:Poetry, book:Play, book:Essay, book:NonFiction

If the file is absent or a work key is missing, the script defaults to book:NonFiction.
"""

import argparse
import csv
import os
import re

BASE = "http://localhost:3030/culturalworks/"

BOOK_NS   = "http://localhost:3030/culturalworks/book#"
WIKIDATA  = "https://www.wikidata.org/entity/"
LEXVO_639_1 = "http://lexvo.org/id/iso639-1/"
LEXVO_639_3 = "http://lexvo.org/id/iso639-3/"

# ISO 639-1 codes are 2 letters, 639-3 are 3 letters
def lexvo_iri(code):
    code = code.strip()
    if len(code) == 2:
        return f"{LEXVO_639_1}{code}"
    elif len(code) == 3:
        return f"{LEXVO_639_3}{code}"
    return None

def ol_key_short(ol_key):
    """Extract OL key without /authors/ or /works/ prefix."""
    return ol_key.strip().replace("/authors/", "").replace("/works/", "")

def work_iri(ol_work_key):
    return f"{BASE}ol/work/{ol_work_key}"

def author_iri(key_short):
    return f"{BASE}ol/author/{key_short}"

def contribution_iri(ol_work_key, key_short):
    return f"{BASE}ol/contribution/{ol_work_key}/{key_short}"

def imdb_person_iri(talent_id):
    return f"{BASE}person/{talent_id}"

def language_iri(code):
    return f"{BASE}language/{code.strip()}"


def load_worktype_lookup(path):
    """Load manually seeded work type assignments. Returns dict keyed on ol_work_key."""
    if not os.path.exists(path):
        print(f"  ! No worktype lookup found at {path} — defaulting all to book:NonFiction")
        return {}
    lookup = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            wk  = row["ol_work_key"].strip()
            wti = row["work_type_iri"].strip()
            # Expand book: prefix to full IRI
            if wti.startswith("book:"):
                wti = BOOK_NS + wti[5:]
            lookup[wk] = wti
    print(f"  Loaded {len(lookup)} worktype assignments from seeded lookup.")
    return lookup


def run(works_path, authors_path, sameas_path, outdir):
    os.makedirs(outdir, exist_ok=True)

    # ---- Load worktype lookup (seeded) ------------------------------------
    lookup_path = os.path.join(outdir, "ol_worktype_lookup.csv")
    worktype_lookup = load_worktype_lookup(lookup_path)
    default_type = BOOK_NS + "NonFiction"

    # ---- Load works -------------------------------------------------------
    works = []
    with open(works_path, encoding="utf-8") as f:
        works = list(csv.DictReader(f))
    print(f"  Loaded {len(works)} work rows.")

    # ---- Determine confirmed author keys first ----------------------------
    # Filter to keep=yes only so we don't load all 177k rows unnecessarily.
    confirmed_keys = set()
    with open(sameas_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("keep", "").strip().lower() == "yes":
                confirmed_keys.add(ol_key_short(row["ol_key"]))
    print(f"  Confirmed author keys: {confirmed_keys}")

    # ---- Load authors (confirmed only) ------------------------------------
    authors = {}
    with open(authors_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ks = ol_key_short(row["ol_key"])
            if ks in confirmed_keys:
                authors[ks] = row
    print(f"  Loaded {len(authors)} author rows from ol_author.csv (confirmed only).")

    # ---- Load sameAs (keep=yes only) --------------------------------------
    sameas_rows = []
    with open(sameas_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("keep", "").strip().lower() == "yes":
                sameas_rows.append(row)
    print(f"  Loaded {len(sameas_rows)} confirmed owl:sameAs links.")

    # ---- Output 1: ol_work.csv -------------------------------------------
    # One row per work. Flat, RML-consumable.
    work_path = os.path.join(outdir, "ol_work.csv")
    work_fields = [
        "ol_work_iri", "ol_work_key", "title",
        "first_publish_year", "work_type_iri",
    ]
    seen_works = {}
    with open(work_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=work_fields)
        w.writeheader()
        for row in works:
            wk = row["ol_work_key"].strip()
            if wk in seen_works:
                continue
            seen_works[wk] = True
            w.writerow({
                "ol_work_iri":        work_iri(wk),
                "ol_work_key":        wk,
                "title":              row["title"],
                "first_publish_year": row["first_publish_year"].strip() or "",
                "work_type_iri":      worktype_lookup.get(wk, default_type),
            })
    print(f"  Wrote {len(seen_works)} rows to ol_work.csv")

    # ---- Output 2: ol_work_language.csv ----------------------------------
    # One row per (work, language code). Exploded from semicolon-separated field.
    # RML cannot split a cell value — must be pre-exploded.
    lang_path = os.path.join(outdir, "ol_work_language.csv")
    lang_fields = ["ol_work_iri", "language_iri", "lexvo_iri", "language_code"]
    lang_rows = []
    seen_lang_pairs = set()
    for row in works:
        wk   = row["ol_work_key"].strip()
        wiri = work_iri(wk)
        raw  = row.get("languages", "").strip()
        if not raw:
            continue
        codes = [c.strip() for c in raw.split(";") if c.strip()]
        for code in codes:
            pair = (wk, code)
            if pair in seen_lang_pairs:
                continue
            seen_lang_pairs.add(pair)
            lx = lexvo_iri(code)
            lang_rows.append({
                "ol_work_iri":   wiri,
                "language_iri":  language_iri(code),
                "lexvo_iri":     lx or "",
                "language_code": code,
            })
    with open(lang_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=lang_fields)
        w.writeheader()
        w.writerows(lang_rows)
    print(f"  Wrote {len(lang_rows)} rows to ol_work_language.csv")

    # ---- Output 3: ol_contribution.csv -----------------------------------
    # One row per (work, author) — maps to book:BookContribution.
    # Also includes author data for the person triple.
    contrib_path = os.path.join(outdir, "ol_contribution.csv")
    contrib_fields = [
        "contribution_iri", "ol_work_iri", "ol_author_iri",
        "ol_work_key", "ol_key_short",
    ]
    contrib_rows = []
    seen_contribs = set()
    for row in works:
        wk  = row["ol_work_key"].strip()
        ks  = ol_key_short(row["ol_key"])
        pair = (wk, ks)
        if pair in seen_contribs:
            continue
        seen_contribs.add(pair)
        contrib_rows.append({
            "contribution_iri": contribution_iri(wk, ks),
            "ol_work_iri":      work_iri(wk),
            "ol_author_iri":    author_iri(ks),
            "ol_work_key":      wk,
            "ol_key_short":     ks,
        })
    with open(contrib_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=contrib_fields)
        w.writeheader()
        w.writerows(contrib_rows)
    print(f"  Wrote {len(contrib_rows)} rows to ol_contribution.csv")

    # ---- Output 4: ol_person.csv -----------------------------------------
    # One row per confirmed OL author — for cw:RealPerson triples.
    # Only the 5 authors whose works we fetched.
    person_path = os.path.join(outdir, "ol_person.csv")
    person_fields = [
        "ol_author_iri", "ol_key_short", "name",
        "birth_year", "death_year", "wikidata_iri",
    ]
    # Collect distinct author keys from contribution rows
    author_keys = {r["ol_key_short"] for r in contrib_rows}
    person_rows = []
    for ks in author_keys:
        a = authors.get(ks, {})
        wikidata_id = a.get("wikidata_id", "").strip()
        person_rows.append({
            "ol_author_iri": author_iri(ks),
            "ol_key_short":  ks,
            "name":          a.get("name", ""),
            "birth_year":    a.get("birth_year", "").strip(),
            "death_year":    a.get("death_year", "").strip(),
            "wikidata_iri":  f"{WIKIDATA}{wikidata_id}" if wikidata_id else "",
        })
    with open(person_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=person_fields)
        w.writeheader()
        w.writerows(person_rows)
    print(f"  Wrote {len(person_rows)} rows to ol_person.csv")

    # ---- Output 5: ol_sameas.csv -----------------------------------------
    # One row per confirmed IMDB↔OL owl:sameAs link.
    sameas_out_path = os.path.join(outdir, "ol_sameas.csv")
    sameas_out_fields = [
        "imdb_talent_id", "ol_key_short",
        "imdb_person_iri", "ol_author_iri", "ol_wikidata_iri",
    ]
    sameas_out_rows = []
    for row in sameas_rows:
        ks          = ol_key_short(row["ol_key"])
        wikidata_id = row.get("ol_wikidata_id", "").strip()
        sameas_out_rows.append({
            "imdb_talent_id":  row["imdb_talent_id"],
            "ol_key_short":    ks,
            "imdb_person_iri": imdb_person_iri(row["imdb_talent_id"]),
            "ol_author_iri":   author_iri(ks),
            "ol_wikidata_iri": f"{WIKIDATA}{wikidata_id}" if wikidata_id else "",
        })
    with open(sameas_out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sameas_out_fields)
        w.writeheader()
        w.writerows(sameas_out_rows)
    print(f"  Wrote {len(sameas_out_rows)} rows to ol_sameas.csv")

    # ---- Summary ----------------------------------------------------------
    print("\n=== Files produced ===")
    for fname in ["ol_work.csv", "ol_work_language.csv",
                  "ol_contribution.csv", "ol_person.csv", "ol_sameas.csv"]:
        path = os.path.join(outdir, fname)
        print(f"  {path}")
    print("\n⚠  Don't forget to create ol_worktype_lookup.csv before running!")
    print("   See script header for format and valid values.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--works",   required=True)
    ap.add_argument("--authors", required=True)
    ap.add_argument("--sameas",  required=True)
    ap.add_argument("--outdir",  default="data/generated")
    args = ap.parse_args()
    run(args.works, args.authors, args.sameas, args.outdir)
