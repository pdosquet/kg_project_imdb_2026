#!/usr/bin/env python3
"""
fetch_ol_works.py
=================
Fetch works from the Open Library Search API for the confirmed
owl:sameAs authors only (keep=yes in the reviewed sameAs file).

Usage:
    python3 fetch_ol_works.py \
        --sameas  data/generated/ol_imdb_sameas_reviewed.csv \
        --outdir  data/generated \
        --max-works 15
"""

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request

OL_SEARCH = "https://openlibrary.org/search.json"
SLEEP = 0.5


def fetch_works(ol_key_short, ol_name, max_works, retries=4):
    """Hit OL search API for works by this author key.
    Retries up to `retries` times with exponential backoff on any error."""
    q = urllib.parse.urlencode({
        "author":  ol_key_short,
        "fields":  "key,title,first_publish_year,subject,language",
        "limit":   max_works,
        "sort":    "editions",
    })
    url = f"{OL_SEARCH}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "kr-project-m4/1.0"})

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(SLEEP)
            results = []
            for doc in data.get("docs", []):
                results.append({
                    "ol_key":             f"/authors/{ol_key_short}",
                    "ol_name":            ol_name,
                    "ol_work_key":        doc.get("key", "").replace("/works/", ""),
                    "title":              doc.get("title", ""),
                    "first_publish_year": doc.get("first_publish_year", ""),
                    "subjects":           "; ".join((doc.get("subject") or [])[:5]),
                    "languages":          "; ".join((doc.get("language") or [])[:3]),
                })
            return results
        except Exception as e:
            wait = 2 ** attempt   # 2, 4, 8, 16 seconds
            print(f"  ! Attempt {attempt}/{retries} failed for {ol_key_short}: {e}")
            if attempt < retries:
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ! All {retries} attempts failed. Skipping {ol_key_short}.")
                return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sameas",     required=True,
                    help="Path to reviewed ol_imdb_sameas_reviewed.csv")
    ap.add_argument("--outdir",     default="data/generated")
    ap.add_argument("--max-works",  type=int, default=15)
    args = ap.parse_args()

    # ---- Load only keep=yes rows, deduplicate by ol_key ------------------
    confirmed = {}   # ol_key_short -> ol_name
    with open(args.sameas, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["keep"].strip().lower() == "yes":
                # ol_key is e.g. "/authors/OL107571A"
                key_short = row["ol_key"].replace("/authors/", "")
                confirmed[key_short] = row["ol_name"]

    if not confirmed:
        print("No keep=yes rows found. Check your reviewed sameAs file.")
        return

    print(f"Found {len(confirmed)} confirmed author(s) to fetch:\n")
    for k, n in confirmed.items():
        print(f"  {n} ({k})")
    print()

    # ---- Fetch works for each confirmed author ----------------------------
    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, "ol_author_work.csv")
    fields = ["ol_key", "ol_name", "ol_work_key", "title",
              "first_publish_year", "subjects", "languages"]

    total = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for key_short, ol_name in confirmed.items():
            print(f"  Fetching works for {ol_name} ({key_short})...")
            works = fetch_works(key_short, ol_name, args.max_works)
            writer.writerows(works)
            total += len(works)
            print(f"    → {len(works)} works fetched")

    print(f"\nDone. {total} total work rows written to {out_path}")


if __name__ == "__main__":
    main()
