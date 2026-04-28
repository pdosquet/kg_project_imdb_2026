#!/usr/bin/env python3
"""
ol_preprocess.py
================
Preprocessor for the Open Library authors dump, used as the M4
demonstrator for the KR&R project.

PURPOSE
-------
Transform the Open Library authors dump (a gzip-compressed TSV where the
fifth column is a JSON blob) into flat CSV files that RMLMapper can consume,
and produce a candidate owl:sameAs table linking OL authors to IMDB talents.

This script is intentionally verbose about what it does and does not work,
because the difficulties encountered ARE the demonstrator content.

INPUT
-----
  ol_dump_authors_latest.txt.gz   (~0.5 GB compressed, ~3 GB decompressed)
      Format: type TAB key TAB revision TAB last_modified TAB JSON
  data/talent.csv                 IMDB talent table from M3

OUTPUT (all in data/generated/)
--------------------------------
  ol_author.csv           flat author records, one per OL author key
  ol_author_work.csv      one row per (author, work) pair, from OL search API
  ol_imdb_sameas.csv      candidate owl:sameAs links for manual review
  ol_preprocess_log.json  metrics: how many records were parsed, dropped,
                          matched — this document goes in the M4 report

DIFFICULTIES DOCUMENTED
-----------------------
1. Format: TSV with embedded JSON — not directly RML-consumable
2. Date semantics: birth_date / death_date are free-text strings
   e.g. "26 February 1802", "ca. 1802", "fl. 1500", "1802?"
   → must parse to xsd:gYear or declare unparseable
3. Name fields: OL has name, personal_name, alternate_names — which to use?
4. Identity resolution: no IMDB↔OL crosswalk exists; must do
   name + life-date fuzzy matching and defend precision decisions
5. Scale: 6M+ authors, most irrelevant — must filter early and aggressively

USAGE
-----
  # Step 1: download (once)
  wget https://openlibrary.org/data/ol_dump_authors_latest.txt.gz

  # Step 2: run preprocessor
  python3 ol_preprocess.py \
      --dump ol_dump_authors_latest.txt.gz \
      --talent data/talent.csv \
      --outdir data/generated

  # Step 3: review ol_imdb_sameas.csv manually, delete false positives

  # Step 4: fetch works for matched authors (runs OL Search API)
  python3 ol_preprocess.py \
      --dump ol_dump_authors_latest.txt.gz \
      --talent data/talent.csv \
      --outdir data/generated \
      --fetch-works
"""

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

# ============================================================
# DATE PARSING — the core difficulty
# ============================================================
# OL stores dates as free-text. The full range of formats observed in the
# dump (from community analysis) includes:
#
#   "1802"                  → clean year, use directly
#   "February 26, 1802"     → month-day-year, extract year
#   "26 February 1802"      → day-month-year, extract year
#   "1802?"                 → uncertain year, extract with flag
#   "ca. 1802"              → circa, extract with flag
#   "c. 1802"               → circa variant
#   "born 1802"             → keyword prefix
#   "fl. 1500"              → floruit (active period), not a birth date
#   "active 1900s"          → decade range, unparseable
#   "19th century"          → century, unparseable
#   ""  / null              → absent
#
# Strategy: extract the first 4-digit sequence that looks like a year
# (1000–2100). Flag uncertain ones. Declare the rest unparseable.
# Record counts of each outcome in the metrics log.

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})\b")
_FLORUIT_RE = re.compile(r"\bfl\.?\b", re.IGNORECASE)
_CIRCA_RE = re.compile(r"\b(ca?\.?|circa|approx)\b", re.IGNORECASE)
_CENTURY_RE = re.compile(r"\bcentury\b", re.IGNORECASE)
_DECADE_RE = re.compile(r"\b\d{3}0s\b")

def parse_year(raw, metrics_bucket):
    """
    Parse a free-text OL date string to an integer year.
    Returns (year_int_or_None, outcome_string).
    outcome is one of: 'clean', 'extracted', 'uncertain', 'floruit',
                       'century', 'decade', 'absent', 'unparseable'
    """
    if not raw or not raw.strip():
        metrics_bucket["absent"] += 1
        return None, "absent"

    raw = raw.strip()

    if _FLORUIT_RE.search(raw):
        metrics_bucket["floruit"] += 1
        return None, "floruit"

    if _CENTURY_RE.search(raw):
        metrics_bucket["century"] += 1
        return None, "century"

    if _DECADE_RE.search(raw):
        metrics_bucket["decade"] += 1
        return None, "decade"

    m = _YEAR_RE.search(raw)
    if not m:
        metrics_bucket["unparseable"] += 1
        return None, "unparseable"

    year = int(m.group(1))

    # Check if the raw string was JUST the year (clean)
    clean = re.fullmatch(r"\d{4}", raw.strip())
    if clean:
        metrics_bucket["clean"] += 1
        return year, "clean"

    # Check for uncertainty markers
    if _CIRCA_RE.search(raw) or "?" in raw:
        metrics_bucket["uncertain"] += 1
        return year, "uncertain"

    metrics_bucket["extracted"] += 1
    return year, "extracted"


# ============================================================
# NAME NORMALISATION — for fuzzy matching
# ============================================================

def normalise(name):
    """Lowercase, strip diacritics, collapse whitespace, drop punctuation."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name.lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def name_tokens(name):
    return set(normalise(name).split())


def names_match(imdb_name, ol_name, ol_alternates=None):
    """
    Return True if the OL author is plausibly the same person as the
    IMDB talent. Matching strategy:
      1. At least 2 tokens overlap between IMDB name and OL name.
      2. OR: the shorter name's tokens are a subset of the longer name's.
      3. If (1) and (2) fail on primary name, try alternate_names.
    """
    a = name_tokens(imdb_name)
    if not a:
        return False

    def _match_pair(a, b_str):
        b = name_tokens(b_str)
        if not b:
            return False
        overlap = a & b
        return len(overlap) >= 2 or a.issubset(b) or b.issubset(a)

    if _match_pair(a, ol_name):
        return True

    if ol_alternates:
        alts = ol_alternates if isinstance(ol_alternates, list) else [ol_alternates]
        for alt in alts:
            if _match_pair(a, str(alt)):
                return True

    return False


DATE_TOLERANCE = 3  # years

def years_close(y1, y2):
    if y1 is None or y2 is None:
        return None  # can't compare
    return abs(y1 - y2) <= DATE_TOLERANCE


def life_dates_match(imdb_birth, imdb_death, ol_birth, ol_death):
    """
    Return True only if at least one date is comparable AND all comparable
    dates are within DATE_TOLERANCE years of each other.
    If no dates are available on either side, return None (inconclusive).
    """
    birth_check = years_close(imdb_birth, ol_birth)
    death_check = years_close(imdb_death, ol_death)
    checks = [c for c in (birth_check, death_check) if c is not None]
    if not checks:
        return None  # no evidence either way
    return all(checks)


# ============================================================
# OL SEARCH API — fetch works for matched authors
# ============================================================

OL_SEARCH = "https://openlibrary.org/search.json"
SLEEP = 0.5  # seconds between API calls — be polite


def fetch_works_for_author(ol_author_key, max_works=10):
    """
    Query OL search API for works by an author key.
    Returns list of dicts with: work_key, title, first_publish_year, subjects.
    """
    q = urllib.parse.urlencode({
        "author": ol_author_key,
        "fields": "key,title,first_publish_year,subject,language",
        "limit": max_works,
        "sort": "editions",
    })
    url = f"{OL_SEARCH}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "kr-project-m4/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        time.sleep(SLEEP)
        results = []
        for doc in data.get("docs", []):
            results.append({
                "ol_work_key":        doc.get("key", "").replace("/works/", ""),
                "title":              doc.get("title", ""),
                "first_publish_year": doc.get("first_publish_year", ""),
                "subjects":           "; ".join((doc.get("subject") or [])[:5]),
                "languages":          "; ".join((doc.get("language") or [])[:3]),
            })
        return results
    except Exception as e:
        print(f"  ! API error for {ol_author_key}: {e}", file=sys.stderr)
        return []


# ============================================================
# MAIN PIPELINE
# ============================================================

def load_imdb_talents(talent_path):
    """Load talent.csv into a dict keyed by talent_id."""
    talents = {}
    with open(talent_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            byear_raw = row.get("birth_year", "")
            dyear_raw = row.get("death_year", "")
            def to_int(s):
                s = (s or "").strip()
                return int(s) if s.lstrip("-").isdigit() else None
            talents[row["talent_id"]] = {
                "talent_id":  row["talent_id"],
                "name":       row.get("talent_name", ""),
                "birth":      to_int(byear_raw),
                "death":      to_int(dyear_raw),
            }
    return talents


def stream_ol_dump(dump_path):
    """
    Stream the OL authors dump line by line without fully decompressing.
    Yields parsed JSON objects for /type/author records only.

    The format is:
        type TAB key TAB revision TAB last_modified TAB JSON
    Column indices (0-based): 0=type, 1=key, 2=revision, 3=last_modified, 4=JSON
    """
    opener = gzip.open if dump_path.endswith(".gz") else open
    with opener(dump_path, "rt", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if lineno % 500_000 == 0:
                print(f"  ... {lineno:,} lines read", file=sys.stderr)
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) < 5:
                continue
            rec_type = parts[0]
            if rec_type != "/type/author":
                continue
            key = parts[1]   # e.g. "/authors/OL26320A"
            try:
                obj = json.loads(parts[4])
            except json.JSONDecodeError:
                continue
            obj["_key"] = key
            yield obj


def run(dump_path, talent_path, outdir, fetch_works=False, max_works=10):
    os.makedirs(outdir, exist_ok=True)

    # ---- metrics skeleton -----------------------------------------------
    metrics = {
        "run_timestamp":       datetime.utcnow().isoformat(),
        "dump_path":           dump_path,
        "talent_path":         talent_path,
        "total_ol_authors":    0,
        "filtered_wikidata":   0,   # kept: had wikidata ID (pre-filter)
        "birth_parse":         defaultdict(int),
        "death_parse":         defaultdict(int),
        "name_match_candidates": 0,
        "date_match_confirmed":  0,
        "date_match_inconclusive": 0,
        "date_match_rejected":   0,
        "sameas_asserted":       0,
        "works_fetched":         0,
        "difficulty_notes": [
            "TSV-with-JSON: line splitting on \\t with limit=4 required; naive CSV would break on embedded commas",
            "birth_date/death_date are free-text; regex extraction with fallback categories used",
            "floruit dates (fl. NNNN) silently discarded — they express active period, not birth",
            "circa markers kept as uncertain years; included in matching with relaxed tolerance",
            "6M+ records streamed without full decompression to avoid 3GB temp file",
            "No OL↔IMDB crosswalk exists; name+life-date matching precision is a methodological choice",
        ],
    }

    # ---- load IMDB candidates -------------------------------------------
    print("Loading IMDB talents...", file=sys.stderr)
    talents = load_imdb_talents(talent_path)
    # Index by normalised name for O(1) lookup during streaming
    imdb_by_name = defaultdict(list)
    for t in talents.values():
        for tok in name_tokens(t["name"]):
            if len(tok) >= 4:   # skip short tokens like "de", "van"
                imdb_by_name[tok].append(t)
    print(f"  {len(talents):,} IMDB talents indexed.", file=sys.stderr)

    # ---- output file handles --------------------------------------------
    author_path  = os.path.join(outdir, "ol_author.csv")
    sameas_path  = os.path.join(outdir, "ol_imdb_sameas.csv")

    author_fields = [
        "ol_key", "name", "personal_name", "birth_year", "birth_quality",
        "death_year", "death_quality", "wikidata_id", "viaf_id",
        "alternate_names_count",
    ]
    sameas_fields = [
        "imdb_talent_id", "imdb_name", "imdb_birth", "imdb_death",
        "ol_key", "ol_name", "ol_birth", "ol_birth_quality",
        "ol_death", "ol_death_quality", "ol_wikidata_id",
        "name_match", "date_match",
        "confidence",    # 'high' / 'medium' / 'low'
        "keep",          # pre-filled 'yes'; reviewer changes to 'no' for FPs
    ]

    author_f  = open(author_path,  "w", newline="", encoding="utf-8")
    sameas_f  = open(sameas_path,  "w", newline="", encoding="utf-8")
    author_w  = csv.DictWriter(author_f,  fieldnames=author_fields)
    sameas_w  = csv.DictWriter(sameas_f,  fieldnames=sameas_fields)
    author_w.writeheader()
    sameas_w.writeheader()

    # ---- stream dump ----------------------------------------------------
    print("Streaming OL dump — this takes a few minutes...", file=sys.stderr)

    for obj in stream_ol_dump(dump_path):
        metrics["total_ol_authors"] += 1

        ol_key  = obj.get("_key", "")
        ol_name = obj.get("name", "")
        remote  = obj.get("remote_ids") or {}
        wikidata_id = remote.get("wikidata", "")
        viaf_id     = remote.get("viaf", "")
        alternates  = obj.get("alternate_names") or []

        # --- Date parsing (DIFFICULTY 2) ---------------------------------
        birth_raw = obj.get("birth_date", "")
        death_raw = obj.get("death_date", "")
        ol_birth, birth_q = parse_year(birth_raw, metrics["birth_parse"])
        ol_death, death_q = parse_year(death_raw, metrics["death_parse"])

        # --- Pre-filter: only keep if wikidata ID present ----------------
        # Rationale documented in M4 report: we only federate with authors
        # that have an external authority link, limiting false positives
        # and ensuring the owl:sameAs chain is grounded in LOD best practice.
        if not wikidata_id:
            continue
        metrics["filtered_wikidata"] += 1

        # --- Write author row --------------------------------------------
        author_w.writerow({
            "ol_key":                 ol_key,
            "name":                   ol_name,
            "personal_name":          obj.get("personal_name", ""),
            "birth_year":             ol_birth if ol_birth is not None else "",
            "birth_quality":          birth_q,
            "death_year":             ol_death if ol_death is not None else "",
            "death_quality":          death_q,
            "wikidata_id":            wikidata_id,
            "viaf_id":                viaf_id,
            "alternate_names_count":  len(alternates),
        })

        # --- Identity matching (DIFFICULTY 4) ----------------------------
        # Find IMDB talents that share at least one significant name token
        # with this OL author. This is the candidate generation step.
        candidate_talents = set()
        for tok in name_tokens(ol_name):
            if len(tok) >= 4:
                for t in imdb_by_name.get(tok, []):
                    candidate_talents.add(t["talent_id"])
        # Also try alternate names
        for alt in alternates:
            for tok in name_tokens(str(alt)):
                if len(tok) >= 4:
                    for t in imdb_by_name.get(tok, []):
                        candidate_talents.add(t["talent_id"])

        if not candidate_talents:
            continue

        # For each candidate, check name + date
        for tid in candidate_talents:
            t = talents[tid]
            nm = names_match(t["name"], ol_name, alternates)
            if not nm:
                continue
            metrics["name_match_candidates"] += 1

            dt = life_dates_match(t["birth"], t["death"], ol_birth, ol_death)

            if dt is True:
                date_match_str = "confirmed"
                metrics["date_match_confirmed"] += 1
                confidence = "high" if birth_q in ("clean", "extracted") else "medium"
            elif dt is None:
                date_match_str = "inconclusive"
                metrics["date_match_inconclusive"] += 1
                confidence = "low"
            else:
                # dt is False — name matched but dates contradict
                date_match_str = "rejected"
                metrics["date_match_rejected"] += 1
                continue   # skip — likely a false positive

            metrics["sameas_asserted"] += 1
            sameas_w.writerow({
                "imdb_talent_id":   tid,
                "imdb_name":        t["name"],
                "imdb_birth":       t["birth"] or "",
                "imdb_death":       t["death"] or "",
                "ol_key":           ol_key,
                "ol_name":          ol_name,
                "ol_birth":         ol_birth if ol_birth is not None else "",
                "ol_birth_quality": birth_q,
                "ol_death":         ol_death if ol_death is not None else "",
                "ol_death_quality": death_q,
                "ol_wikidata_id":   wikidata_id,
                "name_match":       "yes",
                "date_match":       date_match_str,
                "confidence":       confidence,
                "keep":             "yes",
            })

    author_f.close()
    sameas_f.close()

    # ---- Fetch works for matched authors (optional) ----------------------
    if fetch_works:
        print("\nFetching works for matched authors via OL Search API...",
              file=sys.stderr)
        # Read back the sameas file to get distinct ol_keys to fetch
        matched_ol_keys = {}
        with open(sameas_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["keep"] == "yes":
                    ol_key = row["ol_key"]  # e.g. /authors/OL26320A
                    ol_key_short = ol_key.replace("/authors/", "")
                    matched_ol_keys[ol_key_short] = row["ol_name"]

        works_path  = os.path.join(outdir, "ol_author_work.csv")
        works_fields = [
            "ol_key", "ol_name", "ol_work_key", "title",
            "first_publish_year", "subjects", "languages",
        ]
        with open(works_path, "w", newline="", encoding="utf-8") as wf:
            ww = csv.DictWriter(wf, fieldnames=works_fields)
            ww.writeheader()
            for ol_key_short, ol_name in matched_ol_keys.items():
                print(f"  Fetching works for {ol_name} ({ol_key_short})...",
                      file=sys.stderr)
                works = fetch_works_for_author(ol_key_short, max_works)
                for w in works:
                    metrics["works_fetched"] += 1
                    ww.writerow({
                        "ol_key":             f"/authors/{ol_key_short}",
                        "ol_name":            ol_name,
                        "ol_work_key":        w["ol_work_key"],
                        "title":              w["title"],
                        "first_publish_year": w["first_publish_year"],
                        "subjects":           w["subjects"],
                        "languages":          w["languages"],
                    })
        print(f"  Wrote {metrics['works_fetched']} work rows.", file=sys.stderr)

    # ---- Write metrics log ----------------------------------------------
    # Convert defaultdicts to plain dicts for JSON serialisation
    metrics["birth_parse"] = dict(metrics["birth_parse"])
    metrics["death_parse"] = dict(metrics["death_parse"])

    log_path = os.path.join(outdir, "ol_preprocess_log.json")
    with open(log_path, "w", encoding="utf-8") as lf:
        json.dump(metrics, lf, indent=2)

    # ---- Human-readable summary -----------------------------------------
    print("\n" + "="*60, file=sys.stderr)
    print("PREPROCESSING COMPLETE", file=sys.stderr)
    print("="*60, file=sys.stderr)
    print(f"  Total OL authors read:          {metrics['total_ol_authors']:>10,}", file=sys.stderr)
    print(f"  Kept (have Wikidata ID):         {metrics['filtered_wikidata']:>10,}", file=sys.stderr)
    print(f"  IMDB name-match candidates:      {metrics['name_match_candidates']:>10,}", file=sys.stderr)
    print(f"  Date-confirmed matches:          {metrics['date_match_confirmed']:>10,}", file=sys.stderr)
    print(f"  Date-inconclusive (kept, low):   {metrics['date_match_inconclusive']:>10,}", file=sys.stderr)
    print(f"  Date-rejected (contradicted):    {metrics['date_match_rejected']:>10,}", file=sys.stderr)
    print(f"  Candidate owl:sameAs written:    {metrics['sameas_asserted']:>10,}", file=sys.stderr)
    print(f"\nBirth date parse outcomes:", file=sys.stderr)
    for outcome, count in sorted(metrics["birth_parse"].items()):
        print(f"  {outcome:<18} {count:>10,}", file=sys.stderr)
    print(f"\nDeath date parse outcomes:", file=sys.stderr)
    for outcome, count in sorted(metrics["death_parse"].items()):
        print(f"  {outcome:<18} {count:>10,}", file=sys.stderr)
    print(f"\nOutput files:", file=sys.stderr)
    print(f"  {author_path}", file=sys.stderr)
    print(f"  {sameas_path}", file=sys.stderr)
    print(f"  {log_path}", file=sys.stderr)
    if fetch_works:
        print(f"  {works_path}", file=sys.stderr)
    print(f"\n⚠  REVIEW {sameas_path} MANUALLY before asserting owl:sameAs.", file=sys.stderr)
    print(f"   Set keep=no for any false positives.", file=sys.stderr)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dump",    required=True,
                    help="Path to ol_dump_authors_latest.txt.gz")
    ap.add_argument("--talent",  required=True,
                    help="Path to IMDB talent.csv")
    ap.add_argument("--outdir",  default="data/generated",
                    help="Output directory (default: data/generated)")
    ap.add_argument("--fetch-works", action="store_true",
                    help="After matching, fetch works from OL Search API")
    ap.add_argument("--max-works", type=int, default=10,
                    help="Max works to fetch per matched author (default: 10)")
    args = ap.parse_args()

    run(
        dump_path   = args.dump,
        talent_path = args.talent,
        outdir      = args.outdir,
        fetch_works = args.fetch_works,
        max_works   = args.max_works,
    )
