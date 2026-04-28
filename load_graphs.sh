#!/bin/bash
# load_graphs.sh
# Loads all ontology and data files into the Fuseki culturalworks dataset.
# Run from your project root directory.
# Usage: bash load_graphs.sh

ENDPOINT="http://localhost:3030/culturalworks/data?default"
SPARQL="http://localhost:3030/culturalworks/sparql"

echo "========================================"
echo " Loading graphs into Fuseki"
echo "========================================"
echo ""

# ---- Ontology files (Turtle) ------------------------------------------------
echo "--- Ontologies ---"
for f in ontologies/*.ttl; do
    echo -n "  Loading $f ... "
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: text/turtle" \
        --data-binary @"$f" \
        "$ENDPOINT")
    echo "HTTP $HTTP"
done

echo ""

# ---- Data files (N-Triples) -------------------------------------------------
echo "--- Data ---"
for f in output/*.nt; do
    echo -n "  Loading $f ... "
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/n-triples" \
        --data-binary @"$f" \
        "$ENDPOINT")
    echo "HTTP $HTTP"
done

echo ""

# ---- Verify -----------------------------------------------------------------
echo "--- Verification ---"
COUNT=$(curl -s -G "$SPARQL" \
    --data-urlencode "query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }" \
    -H "Accept: text/csv" | tail -1)
echo "  Total triples in dataset: $COUNT"
echo ""
echo "Done. SPARQL endpoint: $SPARQL"
