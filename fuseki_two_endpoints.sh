#!/bin/bash
# fuseki_two_endpoints.sh
# Launches two Fuseki instances on ports 3030 and 3031.
# Run this in a terminal you can leave open. Use Ctrl+C to stop both.
#
# Endpoints:
#   IMDB graph  → http://localhost:3030/imdb/sparql
#   Book graph  → http://localhost:3031/books/sparql
#   Remote      → https://query.wikidata.org/sparql
#
# Adjust FUSEKI_DIR to your Fuseki installation path.

FUSEKI_DIR="${FUSEKI_DIR:-./apache-jena-fuseki-6.0.0}"

if [ ! -x "$FUSEKI_DIR/fuseki-server" ]; then
    echo "Error: $FUSEKI_DIR/fuseki-server not found or not executable"
    echo "Set FUSEKI_DIR or check your Fuseki installation path."
    exit 1
fi

echo "Starting Fuseki IMDB endpoint on port 3030..."
"$FUSEKI_DIR/fuseki-server" --mem --port 3030 /imdb &
PID_IMDB=$!

echo "Starting Fuseki Books endpoint on port 3031..."
"$FUSEKI_DIR/fuseki-server" --mem --port 3031 /books &
PID_BOOKS=$!

echo ""
echo "IMDB:  http://localhost:3030/imdb/sparql  (PID $PID_IMDB)"
echo "Books: http://localhost:3031/books/sparql (PID $PID_BOOKS)"
echo ""
echo "Ctrl+C to stop both."

# Trap Ctrl+C to clean up both processes
trap "kill $PID_IMDB $PID_BOOKS 2>/dev/null; exit" INT TERM
wait
