#!/bin/bash
# load_split.sh
# Loads triples into the two-endpoint setup.
# - IMDB graph   → 3031/imdb
# - Book graph   → 3032/books
# - The owl:sameAs links go into the IMDB endpoint because they are about
#   IMDB persons; without them the IMDB endpoint cannot bridge to the book
#   endpoint.
# - The shared cw: ontology is loaded into BOTH endpoints because both
#   need to resolve cw: predicates and class IRIs locally.

IMDB_ENDPOINT="http://localhost:3031/imdb/data?default"
BOOK_ENDPOINT="http://localhost:3032/books/data?default"

post_ttl()  { curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: text/turtle"           --data-binary @"$2" "$1"; }
post_nt()   { curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/n-triples" --data-binary @"$2" "$1"; }

echo "=== Loading IMDB endpoint ==="
echo "Ontologies (cw, film, imdb)..."
for f in ontologies/culturalworks.ttl ontologies/film.ttl ontologies/imdb.ttl; do
    echo -n "  $f ... "; echo "HTTP $(post_ttl "$IMDB_ENDPOINT" "$f")"
done
echo "Data (films, persons, AKAs, contributions)..."
for f in output/0[1-9]_*.nt; do
    echo -n "  $f ... "; echo "HTTP $(post_nt "$IMDB_ENDPOINT" "$f")"
done

# Extract just the owl:sameAs triples from 10_book.nt and load them on the
# IMDB side so the IMDB endpoint knows it can bridge to the book endpoint.
echo "owl:sameAs bridge triples..."
mkdir -p output/split
grep "<https://example.org/culturalworks/person/" output/10_book.nt > output/split/10_sameas_bridge.nt
echo -n "  output/split/10_sameas_bridge.nt ... "
echo "HTTP $(post_nt "$IMDB_ENDPOINT" output/split/10_sameas_bridge.nt)"

echo ""
echo "=== Loading Book endpoint ==="
echo "Ontologies (cw, book)..."
for f in ontologies/culturalworks.ttl ontologies/book.ttl; do
    echo -n "  $f ... "; echo "HTTP $(post_ttl "$BOOK_ENDPOINT" "$f")"
done
echo "Data (books, authors, contributions)..."
# Strip the owl:sameAs bridge triples and Wikidata sameAs from the book
# graph; what remains is books, authors, languages, and contributions.
grep -v "<https://example.org/culturalworks/person/" output/10_book.nt > output/split/10_book_only.nt
echo -n "  output/split/10_book_only.nt ... "
echo "HTTP $(post_nt "$BOOK_ENDPOINT" output/split/10_book_only.nt)"

echo ""
echo "=== Verification ==="
COUNT_IMDB=$(curl -s -G "http://localhost:3031/imdb/sparql"  --data-urlencode "query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }" -H "Accept: text/csv" | tail -1)
COUNT_BOOK=$(curl -s -G "http://localhost:3032/books/sparql" --data-urlencode "query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }" -H "Accept: text/csv" | tail -1)
echo "IMDB endpoint triples:  $COUNT_IMDB"
echo "Book endpoint triples:  $COUNT_BOOK"
