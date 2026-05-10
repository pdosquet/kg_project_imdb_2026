#!/usr/bin/env python3
"""
federation_experiment.py
========================
M4 demonstrator: cross-engine analysis of federated SPARQL.

Runs the same logical query through three implementations against three
endpoint setups, measuring HTTP requests, bytes transferred, wall-clock
time, result correctness, and failure behaviour.

The logical query
-----------------
For each IMDB-credited writer/director who is also in Open Library,
retrieve their Wikidata occupation labels.

This query has interesting properties for a federation study:
  - IMDB endpoint: 1,441 candidate persons, only 5 have owl:sameAs to OL
  - OL endpoint:   5 persons, fast
  - Wikidata:      huge, slow, must be queried with filtered IRIs

Optimal plan: query OL first (5 persons), get their Wikidata IRIs, then
query Wikidata with exactly those 5 IRIs. Naive plan: query Wikidata for
all writers and join client-side (fails — Wikidata limits result size).

Three implementations
---------------------
1. Single endpoint baseline   — load everything into one Fuseki instance
2. rdflib + SPARQLWrapper     — Python client, manual join logic
3. Apache Jena via SERVICE    — server-side federation

Run all three, compare the measurements, write the M4 chapter.

Requirements:
    pip install SPARQLWrapper rdflib requests

Usage:
    python3 federation_experiment.py --strategy naive
    python3 federation_experiment.py --strategy optimised
    python3 federation_experiment.py --strategy jena_service
    python3 federation_experiment.py --strategy single_endpoint
    python3 federation_experiment.py --all      # runs everything
"""

import argparse
import json
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    from SPARQLWrapper import SPARQLWrapper, JSON, POST
except ImportError:
    print("Install SPARQLWrapper:  pip install SPARQLWrapper", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# Endpoints
# ============================================================================
IMDB_EP   = "http://localhost:3031/imdb/sparql"
BOOK_EP   = "http://localhost:3032/books/sparql"
SINGLE_EP = "http://localhost:3030/culturalworks/sparql"  # M4 baseline
WIKIDATA  = "https://query.wikidata.org/sparql"

# ============================================================================
# Measurement infrastructure
# ============================================================================

@dataclass
class Measurements:
    strategy:        str
    http_requests:   int = 0
    bytes_received:  int = 0
    wall_clock_s:    float = 0.0
    rows_returned:   int = 0
    result_set:      list = field(default_factory=list)
    server_imdb_reqs:  int = 0
    server_books_reqs: int = 0
    error:           Optional[str] = None
    request_log:     list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["request_log_size"] = len(self.request_log)
        d["request_log"] = self.request_log[:5]   # truncate for readability
        d["result_set"] = sorted(self.result_set)
        return d


# ---- server-side request counter (Fuseki access log) ------------------------
LOG_DIR = Path(__file__).parent / "run" / "logs"
REQ_RE  = re.compile(r"Fuseki\s+::\s+\[\d+\]\s+(?:GET|POST)\s+http://")

def _count_log_reqs(logfile: Path) -> int:
    if not logfile.exists():
        return 0
    with open(logfile, errors="replace") as f:
        return sum(1 for line in f if REQ_RE.search(line))

def _snapshot_server_reqs():
    return {
        "imdb":  _count_log_reqs(LOG_DIR / "imdb.log"),
        "books": _count_log_reqs(LOG_DIR / "books.log"),
    }

def _diff_server_reqs(m: Measurements, before: dict):
    after = _snapshot_server_reqs()
    m.server_imdb_reqs  = after["imdb"]  - before["imdb"]
    m.server_books_reqs = after["books"] - before["books"]


class InstrumentedSPARQL:
    """Wraps SPARQLWrapper to count requests and measure bytes."""
    def __init__(self, endpoint, measurements: Measurements):
        self.endpoint = endpoint
        self.m = measurements
        self.wrapper = SPARQLWrapper(endpoint)
        self.wrapper.setReturnFormat(JSON)
        # Wikidata requires a User-Agent
        self.wrapper.addCustomHttpHeader(
            "User-Agent", "kr-project-m4/1.0 (federation experiment)"
        )

    def query(self, q: str):
        self.m.http_requests += 1
        self.m.request_log.append({
            "endpoint": self.endpoint,
            "query_preview": " ".join(q.split())[:120],
        })
        self.wrapper.setQuery(q)
        try:
            res = self.wrapper.query().convert()
            # Estimate bytes from JSON serialisation
            self.m.bytes_received += len(json.dumps(res).encode("utf-8"))
            return res
        except Exception as e:
            self.m.error = f"HTTP error to {self.endpoint}: {e}"
            raise


@contextmanager
def timed(measurements: Measurements):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        measurements.wall_clock_s = time.perf_counter() - t0


# ============================================================================
# STRATEGY 1: SINGLE-ENDPOINT BASELINE
# Trivial — load everything into one Fuseki and query it. The correctness
# oracle. All other strategies must produce the same rows (set equality).
# ============================================================================

SINGLE_QUERY = """
PREFIX cw:   <https://example.org/culturalworks/ontology#>
PREFIX film: <https://example.org/culturalworks/film#>
PREFIX book: <https://example.org/culturalworks/book#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>

SELECT DISTINCT ?personName WHERE {
  ?fc a film:FilmContribution ; cw:contributedBy ?p ; cw:involves ?f .
  ?p cw:name ?personName ; owl:sameAs ?olP .
  ?bc a book:BookContribution ; cw:contributedBy ?olP .
} ORDER BY ?personName
"""

def run_single_endpoint() -> Measurements:
    m = Measurements(strategy="single_endpoint")
    sparql = InstrumentedSPARQL(SINGLE_EP, m)
    with timed(m):
        try:
            res = sparql.query(SINGLE_QUERY)
            m.result_set = sorted({b["personName"]["value"]
                                   for b in res["results"]["bindings"]})
            m.rows_returned = len(m.result_set)
        except Exception:
            pass
    return m


# ============================================================================
# STRATEGY 2A: rdflib NAIVE FEDERATION
# Query Wikidata first for ALL writers, then filter locally to the 5 we
# care about. This is what a naive client implementation does. Likely
# fails because Wikidata limits result size and cuts you off.
# ============================================================================

NAIVE_WIKIDATA_QUERY = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd:  <http://www.wikidata.org/entity/>

SELECT ?person ?occupationLabel WHERE {
  ?person wdt:P106 ?occupation .
  ?occupation rdfs:label ?occupationLabel .
  FILTER(LANG(?occupationLabel) = "en")
}
"""  # Note: deliberately unfiltered. Will likely be cut off.

def run_naive_federation() -> Measurements:
    m = Measurements(strategy="rdflib_naive")
    imdb_sparql = InstrumentedSPARQL(IMDB_EP, m)
    wd_sparql   = InstrumentedSPARQL(WIKIDATA, m)
    with timed(m):
        try:
            # Step 1: get name + sameAs bridges from IMDB endpoint
            res = imdb_sparql.query("""
                PREFIX cw:  <https://example.org/culturalworks/ontology#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                SELECT ?personName ?olP WHERE {
                  ?p cw:name ?personName ; owl:sameAs ?olP .
                }
            """)
            name_by_olp = {b["olP"]["value"]: b["personName"]["value"]
                           for b in res["results"]["bindings"]}

            # Step 2: pull EVERYTHING from Wikidata, filter locally
            res2 = wd_sparql.query(NAIVE_WIKIDATA_QUERY)
            # If we even get here, set the result via local intersection
            wd_persons = {b["person"]["value"]
                          for b in res2["results"]["bindings"]}
            # Naive client has no way to map Wikidata IRI back to OL author
            # without an extra query — so the joined result is empty.
            m.result_set = []
            m.rows_returned = 0
        except Exception as e:
            m.error = str(e)
    return m


# ============================================================================
# STRATEGY 2B: rdflib OPTIMISED FEDERATION
# Query OL first, get exactly the 5 Wikidata IRIs, then send a tiny
# targeted query to Wikidata with VALUES. This is the optimal plan.
# ============================================================================

def run_optimised_federation() -> Measurements:
    m = Measurements(strategy="rdflib_optimised")
    imdb_sparql = InstrumentedSPARQL(IMDB_EP, m)
    book_sparql = InstrumentedSPARQL(BOOK_EP, m)
    wd_sparql   = InstrumentedSPARQL(WIKIDATA, m)

    with timed(m):
        try:
            # Step 1: from BOOK endpoint, get OL persons that have both
            # cw:RealPerson type AND a BookContribution AND a Wikidata sameAs
            res = book_sparql.query("""
                PREFIX cw:  <https://example.org/culturalworks/ontology#>
                PREFIX book:<https://example.org/culturalworks/book#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                SELECT DISTINCT ?olP ?wd WHERE {
                  ?olP a cw:RealPerson ; owl:sameAs ?wd .
                  ?bc a book:BookContribution ; cw:contributedBy ?olP .
                  FILTER(STRSTARTS(STR(?wd), "http://www.wikidata.org/entity/"))
                }
            """)
            ol_to_wd = {b["olP"]["value"]: b["wd"]["value"]
                        for b in res["results"]["bindings"]}
            if not ol_to_wd:
                m.error = "No bridged OL persons in book endpoint"
                return m

            # Step 2: from IMDB endpoint, get personName for those OL IRIs
            #         AND require a film contribution (matches single oracle)
            values_olp = "\n    ".join(f"<{iri}>" for iri in ol_to_wd)
            res2 = imdb_sparql.query(f"""
                PREFIX cw:   <https://example.org/culturalworks/ontology#>
                PREFIX film: <https://example.org/culturalworks/film#>
                PREFIX owl:  <http://www.w3.org/2002/07/owl#>
                SELECT DISTINCT ?personName ?olP WHERE {{
                  VALUES ?olP {{ {values_olp} }}
                  ?p cw:name ?personName ; owl:sameAs ?olP .
                  ?fc a film:FilmContribution ; cw:contributedBy ?p .
                }}
            """)
            name_by_olp = {b["olP"]["value"]: b["personName"]["value"]
                           for b in res2["results"]["bindings"]}

            # Step 3: targeted Wikidata query with VALUES — N IRIs only
            values_wd = "\n    ".join(f"<{ol_to_wd[k]}>" for k in name_by_olp)
            res3 = wd_sparql.query(f"""
                PREFIX wdt: <http://www.wikidata.org/prop/direct/>
                SELECT DISTINCT ?person WHERE {{
                  VALUES ?person {{ {values_wd} }}
                  ?person wdt:P106 ?occupation .
                }}
            """)
            wd_confirmed = {b["person"]["value"]
                            for b in res3["results"]["bindings"]}
            wd_to_ol = {v: k for k, v in ol_to_wd.items()}
            m.result_set = sorted({name_by_olp[wd_to_ol[wd]]
                                   for wd in wd_confirmed
                                   if wd_to_ol[wd] in name_by_olp})
            m.rows_returned = len(m.result_set)
        except Exception as e:
            m.error = str(e)
    return m


# ============================================================================
# STRATEGY 3: JENA SERVICE FEDERATION
# Uses the SPARQL 1.1 SERVICE keyword. The query is sent to one Fuseki
# endpoint, which then dispatches subqueries to the other endpoint and
# Wikidata. We don't run this in Python — we send the query to the
# IMDB endpoint and let Jena handle the federation server-side.
# Measurement of HTTP traffic on the IMDB endpoint side requires
# reading Fuseki's access log separately.
# ============================================================================

JENA_SERVICE_QUERY = """
PREFIX cw:   <https://example.org/culturalworks/ontology#>
PREFIX film: <https://example.org/culturalworks/film#>
PREFIX book: <https://example.org/culturalworks/book#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>

SELECT DISTINCT ?personName WHERE {

  # Local: IMDB endpoint — person with a film contribution
  ?p cw:name ?personName ; owl:sameAs ?olP .
  ?fc a film:FilmContribution ; cw:contributedBy ?p .

  # Federate to the BOOK endpoint — same person also wrote a book
  SERVICE <http://localhost:3032/books/sparql> {
    ?olP a cw:RealPerson ; owl:sameAs ?wd .
    ?bc a book:BookContribution ; cw:contributedBy ?olP .
    FILTER(STRSTARTS(STR(?wd), "http://www.wikidata.org/entity/"))
  }

  # Federate to Wikidata — confirm the person has an occupation on Wikidata
  SERVICE <https://query.wikidata.org/sparql> {
    ?wd wdt:P106 ?occupation .
  }
}
ORDER BY ?personName
"""

def run_jena_service() -> Measurements:
    m = Measurements(strategy="jena_service")
    sparql = InstrumentedSPARQL(IMDB_EP, m)
    with timed(m):
        try:
            res = sparql.query(JENA_SERVICE_QUERY)
            m.result_set = sorted({b["personName"]["value"]
                                   for b in res["results"]["bindings"]})
            m.rows_returned = len(m.result_set)
        except Exception as e:
            m.error = str(e)
    return m


# ============================================================================
# Reporting
# ============================================================================

def report(results: list, oracle_name: str = "single_endpoint"):
    """Print a comparison table of the measurements."""
    oracle = next((m for m in results if m.strategy == oracle_name), None)
    oracle_set = set(oracle.result_set) if oracle else None

    print("\n" + "=" * 110)
    print(f"{'Strategy':<22} {'Time (s)':>10} {'HTTP':>6} {'Bytes':>10} {'Rows':>6} "
          f"{'imdb-srv':>9} {'books-srv':>10} {'Oracle?':<10} {'Error':<20}")
    print("=" * 110)
    for m in results:
        err = (m.error[:18] + "..") if m.error and len(m.error) > 20 else (m.error or "—")
        if m.strategy == oracle_name:
            ok = "(oracle)"
        elif oracle_set is None:
            ok = "?"
        else:
            ok = "OK" if set(m.result_set) == oracle_set else "MISMATCH"
        print(f"{m.strategy:<22} {m.wall_clock_s:>10.3f} {m.http_requests:>6} "
              f"{m.bytes_received:>10,} {m.rows_returned:>6} "
              f"{m.server_imdb_reqs:>9} {m.server_books_reqs:>10} {ok:<10} {err:<20}")
    print("=" * 110)
    if oracle:
        sample = sorted(oracle_set)[:5]
        more = "" if len(oracle_set) <= 5 else f"  ... ({len(oracle_set) - 5} more)"
        print(f"\nOracle result set ({len(oracle_set)} rows): {', '.join(sample)}{more}")


# ============================================================================
# SINGLE-DOMAIN STRATEGIES
# Same logical query — "list every IMDB person with their film-credit count
# and birth year" — touches IMDB only. No book data, no Wikidata. Compares:
#   - single_local:     query the consolidated /culturalworks endpoint
#   - direct_imdb:      query the focused /imdb endpoint directly
#   - federated_blind:  query /imdb but also SERVICE to /books "just in case",
#                       the way someone unaware of the data layout would write it
# ============================================================================

SINGLE_DOMAIN_QUERY = """
PREFIX cw:   <https://example.org/culturalworks/ontology#>
PREFIX film: <https://example.org/culturalworks/film#>

SELECT ?personName (COUNT(?fc) AS ?credits) WHERE {
  ?p cw:name ?personName .
  ?fc a film:FilmContribution ; cw:contributedBy ?p .
}
GROUP BY ?personName
ORDER BY DESC(?credits) ?personName
"""

FEDERATED_BLIND_QUERY = """
PREFIX cw:   <https://example.org/culturalworks/ontology#>
PREFIX film: <https://example.org/culturalworks/film#>
PREFIX book: <https://example.org/culturalworks/book#>

SELECT ?personName (COUNT(?fc) AS ?credits) WHERE {
  ?p cw:name ?personName .
  ?fc a film:FilmContribution ; cw:contributedBy ?p .

  # Useless side-trip: a developer who doesn't know that film data lives
  # only on the IMDB endpoint asks the books endpoint anyway, "just in case".
  OPTIONAL {
    SERVICE <http://localhost:3032/books/sparql> {
      ?b a book:Book ; cw:contributedBy ?p .
    }
  }
}
GROUP BY ?personName
ORDER BY DESC(?credits) ?personName
"""

def _run_count_query(strategy, endpoint, query):
    m = Measurements(strategy=strategy)
    sparql = InstrumentedSPARQL(endpoint, m)
    with timed(m):
        try:
            res = sparql.query(query)
            m.result_set = sorted({b["personName"]["value"]
                                   for b in res["results"]["bindings"]})
            m.rows_returned = len(m.result_set)
        except Exception as e:
            m.error = str(e)
    return m

def run_single_local():
    return _run_count_query("single_local",    SINGLE_EP, SINGLE_DOMAIN_QUERY)
def run_direct_imdb():
    return _run_count_query("direct_imdb",     IMDB_EP,   SINGLE_DOMAIN_QUERY)
def run_federated_blind():
    return _run_count_query("federated_blind", IMDB_EP,   FEDERATED_BLIND_QUERY)


# ============================================================================
# Main
# ============================================================================

CROSS_STRATEGIES = {
    "single_endpoint":     run_single_endpoint,
    "naive":               run_naive_federation,
    "optimised":           run_optimised_federation,
    "jena_service":        run_jena_service,
}

SINGLE_STRATEGIES = {
    "single_local":     run_single_local,
    "direct_imdb":      run_direct_imdb,
    "federated_blind":  run_federated_blind,
}

ALL_STRATEGIES = {**CROSS_STRATEGIES, **SINGLE_STRATEGIES}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=ALL_STRATEGIES.keys())
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--mode", choices=["cross", "single", "both"], default="both",
                    help="Which evaluation mode(s) to run when --all is set")
    ap.add_argument("--out", default="federation_results.json")
    args = ap.parse_args()

    def _run(fn):
        before = _snapshot_server_reqs()
        m = fn()
        _diff_server_reqs(m, before)
        return m

    if args.all:
        results = {"cross": [], "single": []}
        if args.mode in ("cross", "both"):
            for name, fn in CROSS_STRATEGIES.items():
                print(f"Running cross-domain: {name}...")
                results["cross"].append(_run(fn))
        if args.mode in ("single", "both"):
            for name, fn in SINGLE_STRATEGIES.items():
                print(f"Running single-domain: {name}...")
                results["single"].append(_run(fn))
    elif args.strategy:
        results = {"cross": [], "single": []}
        bucket = "cross" if args.strategy in CROSS_STRATEGIES else "single"
        results[bucket].append(_run(ALL_STRATEGIES[args.strategy]))
    else:
        ap.print_help()
        sys.exit(1)

    if results["cross"]:
        print("\n### CROSS-DOMAIN EVALUATION ###")
        report(results["cross"])
    if results["single"]:
        print("\n### SINGLE-DOMAIN EVALUATION ###")
        report(results["single"], oracle_name="single_local")

    # Persist results for the M4 report
    flat = {k: [m.to_dict() for m in v] for k, v in results.items()}
    with open(args.out, "w") as f:
        json.dump(flat, f, indent=2)
    print(f"\nResults written to {args.out}")


if __name__ == "__main__":
    main()
