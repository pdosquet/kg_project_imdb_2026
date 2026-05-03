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
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    from SPARQLWrapper import SPARQLWrapper, JSON, POST
except ImportError:
    print("Install SPARQLWrapper:  pip install SPARQLWrapper", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# Endpoints
# ============================================================================
IMDB_EP   = "http://localhost:3030/imdb/sparql"
BOOK_EP   = "http://localhost:3031/books/sparql"
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
    error:           Optional[str] = None
    request_log:     list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["request_log_size"] = len(self.request_log)
        d["request_log"] = self.request_log[:5]   # truncate for readability
        return d


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
PREFIX cw:   <http://localhost:3030/culturalworks/ontology#>
PREFIX film: <http://localhost:3030/culturalworks/film#>
PREFIX book: <http://localhost:3030/culturalworks/book#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>

SELECT DISTINCT ?personName ?bookTitle ?bookType WHERE {
  ?fc a film:FilmContribution ; cw:contributedBy ?p ; cw:involves ?f .
  ?p cw:name ?personName ; owl:sameAs ?olP .
  ?bc a book:BookContribution ; cw:contributedBy ?olP ; cw:involves ?b .
  ?b cw:primaryTitle ?bookTitle ; cw:hasType ?bookType .
} ORDER BY ?personName ?bookTitle
"""

def run_single_endpoint() -> Measurements:
    m = Measurements(strategy="single_endpoint")
    sparql = InstrumentedSPARQL(SINGLE_EP, m)
    with timed(m):
        try:
            res = sparql.query(SINGLE_QUERY)
            m.rows_returned = len(res["results"]["bindings"])
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
            # Step 1: get all owl:sameAs bridges from IMDB endpoint
            res = imdb_sparql.query("""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                SELECT ?p ?olP WHERE { ?p owl:sameAs ?olP . }
            """)
            local_pairs = {b["p"]["value"]: b["olP"]["value"]
                           for b in res["results"]["bindings"]}

            # Step 2: pull EVERYTHING from Wikidata, filter locally
            res2 = wd_sparql.query(NAIVE_WIKIDATA_QUERY)
            # this will likely truncate or fail
            m.rows_returned = len(res2["results"]["bindings"])
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
    book_sparql = InstrumentedSPARQL(BOOK_EP, m)
    wd_sparql   = InstrumentedSPARQL(WIKIDATA, m)

    with timed(m):
        try:
            # Step 1: get the 5 Wikidata IRIs from the BOOK endpoint
            # (they're asserted on cw:RealPerson via owl:sameAs in 10_book.nt)
            res = book_sparql.query("""
                PREFIX cw:  <http://localhost:3030/culturalworks/ontology#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                SELECT ?olP ?wd WHERE {
                  ?olP a cw:RealPerson ; owl:sameAs ?wd .
                  FILTER(STRSTARTS(STR(?wd), "https://www.wikidata.org/entity/"))
                }
            """)
            wd_iris = [b["wd"]["value"]
                       for b in res["results"]["bindings"]]
            if not wd_iris:
                m.error = "No Wikidata IRIs found in book endpoint"
                return m

            # Step 2: targeted query to Wikidata with VALUES — exactly 5 IRIs
            values_clause = "\n    ".join(f"<{iri}>" for iri in wd_iris)
            targeted = f"""
                PREFIX wdt: <http://www.wikidata.org/prop/direct/>

                SELECT ?person ?occupationLabel WHERE {{
                  VALUES ?person {{
                    {values_clause}
                  }}
                  ?person wdt:P106 ?occupation .
                  SERVICE wikibase:label {{
                    bd:serviceParam wikibase:language "en" .
                  }}
                  ?occupation rdfs:label ?occupationLabel .
                  FILTER(LANG(?occupationLabel) = "en")
                }}
            """
            res2 = wd_sparql.query(targeted)
            m.rows_returned = len(res2["results"]["bindings"])
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
PREFIX cw:   <http://localhost:3030/culturalworks/ontology#>
PREFIX film: <http://localhost:3030/culturalworks/film#>
PREFIX book: <http://localhost:3031/culturalworks/book#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>

SELECT DISTINCT ?personName ?occupationLabel WHERE {

  # Local: IMDB endpoint
  ?p cw:name ?personName ; owl:sameAs ?olP .

  # Federate to the BOOK endpoint
  SERVICE <http://localhost:3031/books/sparql> {
    ?olP a cw:RealPerson ; owl:sameAs ?wd .
    FILTER(STRSTARTS(STR(?wd), "https://www.wikidata.org/entity/"))
  }

  # Federate to Wikidata
  SERVICE <https://query.wikidata.org/sparql> {
    ?wd wdt:P106 ?occupation .
    SERVICE wikibase:label {
      bd:serviceParam wikibase:language "en" .
    }
    ?occupation rdfs:label ?occupationLabel .
    FILTER(LANG(?occupationLabel) = "en")
  }
}
ORDER BY ?personName ?occupationLabel
"""

def run_jena_service() -> Measurements:
    m = Measurements(strategy="jena_service")
    sparql = InstrumentedSPARQL(IMDB_EP, m)
    with timed(m):
        try:
            res = sparql.query(JENA_SERVICE_QUERY)
            m.rows_returned = len(res["results"]["bindings"])
        except Exception as e:
            m.error = str(e)
    return m


# ============================================================================
# Reporting
# ============================================================================

def report(results: list):
    """Print a comparison table of the measurements."""
    print("\n" + "=" * 80)
    print(f"{'Strategy':<22} {'Time (s)':>10} {'HTTP':>6} {'Bytes':>10} {'Rows':>6} {'Error':<20}")
    print("=" * 80)
    for m in results:
        err = (m.error[:18] + "..") if m.error and len(m.error) > 20 else (m.error or "—")
        print(f"{m.strategy:<22} {m.wall_clock_s:>10.3f} {m.http_requests:>6} "
              f"{m.bytes_received:>10,} {m.rows_returned:>6} {err:<20}")
    print("=" * 80)
    print()
    print("Detailed JSON:")
    print(json.dumps([m.to_dict() for m in results], indent=2))


# ============================================================================
# Main
# ============================================================================

STRATEGIES = {
    "single_endpoint":     run_single_endpoint,
    "naive":               run_naive_federation,
    "optimised":           run_optimised_federation,
    "jena_service":        run_jena_service,
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=STRATEGIES.keys())
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="federation_results.json")
    args = ap.parse_args()

    if args.all:
        results = []
        for name, fn in STRATEGIES.items():
            print(f"Running {name}...")
            results.append(fn())
    elif args.strategy:
        results = [STRATEGIES[args.strategy]()]
    else:
        ap.print_help()
        sys.exit(1)

    report(results)

    # Persist results for the M4 report
    with open(args.out, "w") as f:
        json.dump([m.to_dict() for m in results], f, indent=2)
    print(f"\nResults written to {args.out}")


if __name__ == "__main__":
    main()
