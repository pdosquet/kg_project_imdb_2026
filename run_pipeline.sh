#!/bin/bash
# run_pipeline.sh
# One-shot orchestrator for the M3/M4 KG pipeline.
#
# Subcommands:
#   prepare    Preprocess CSVs + run RML mappings (produces output/*.nt)
#   ol        Run the Open Library pipeline (download + preprocess + map)
#   close      Materialise OWL 2 RL closure (produces output/closed.nt)
#   serve      Launch the three Fuseki endpoints (3030, 3031, 3032)
#   load       Load triples into all three endpoints
#   evaluate   Run the federation experiment
#   stop       Kill the running Fuseki processes
#   all        prepare + ol + close + serve + load + evaluate
#
# Idempotent: each step skips work it has already done.
# Usage:   ./run_pipeline.sh <subcommand> [more]
#          ./run_pipeline.sh all

set -eo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PY="$VENV/bin/python"
FUSEKI_DIR="${FUSEKI_DIR:-./apache-jena-fuseki-6.0.0}"
FUSEKI="$FUSEKI_DIR/fuseki-server"
RMLMAPPER="$ROOT/rmlmapper.jar"
LOG_DIR="$ROOT/run/logs"
PID_DIR="$ROOT/run/pids"
OL_DUMP="$ROOT/ol_dump_authors_latest.txt.gz"
mkdir -p "$LOG_DIR" "$PID_DIR" output data/generated

# -------- helpers ------------------------------------------------------------

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
need() { command -v "$1" >/dev/null || { echo "Missing: $1"; exit 1; }; }

wait_for_endpoint() {
    local url=$1 tries=30
    until curl -sf -o /dev/null "$url"; do
        ((tries--)) || { echo "Endpoint $url didn't come up"; return 1; }
        sleep 1
    done
}

start_fuseki() {
    local port=$1 ds=$2 name=$3 pidfile="$PID_DIR/$name.pid"
    if curl -sf -o /dev/null "http://localhost:$port/\$/ping" 2>/dev/null; then
        log "Fuseki $name already responding on port $port"
        return
    fi
    log "Starting Fuseki $name on port $port (dataset $ds)..."
    "$FUSEKI" --mem --port "$port" "$ds" > "$LOG_DIR/$name.log" 2>&1 &
    echo $! > "$pidfile"
    wait_for_endpoint "http://localhost:$port/\$/ping"
    log "  $name up (PID $(cat "$pidfile"))"
}

post_ttl() { curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: text/turtle" --data-binary @"$2" "$1"; }
post_nt()  { curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/n-triples" --data-binary @"$2" "$1"; }
drop_all() { curl -s -X POST "$1" --data 'update=DROP ALL' -o /dev/null -w "%{http_code}"; }

# -------- subcommands --------------------------------------------------------

compile_yarrrml() {
    log "Compiling YARRRML → RML..."
    for y in mappings/*.yarrrml; do
        local out="${y%.yarrrml}.rml.ttl"
        npx --yes -p @rmlio/yarrrml-parser yarrrml-parser -i "$y" -o "$out" 2>/dev/null
        printf "  %-25s → %s\n" "$(basename "$y")" "$(basename "$out")"
    done
}

cmd_prepare() {
    [[ -x "$PY" ]] || { log "Creating venv..."; python3 -m venv "$VENV" && "$VENV/bin/pip" install -q -r requirements.txt; }
    [[ -f "$RMLMAPPER" ]] || { echo "Missing rmlmapper.jar at project root"; exit 1; }
    need npx

    compile_yarrrml

    log "IMDB preprocessing..."
    "$PY" preprocessing/preprocess.py >/dev/null

    log "RML mapping for IMDB (01..09)..."
    for f in mappings/0[1-9]_*.rml.ttl; do
        local name out
        name=$(basename "$f" .rml.ttl)
        out="output/${name}.nt"
        java -jar "$RMLMAPPER" -m "$f" -o "$out" -s ntriples -d >/dev/null 2>&1
        printf "  %-25s %s triples\n" "$name" "$(wc -l < "$out")"
    done
}

cmd_ol() {
    [[ -x "$PY" ]] || { echo "Run 'prepare' first to set up venv"; exit 1; }

    if [[ ! -f "$OL_DUMP" ]]; then
        log "Downloading Open Library authors dump (~700 MB)..."
        wget -q --show-progress -O "$OL_DUMP" \
            https://openlibrary.org/data/ol_dump_authors_latest.txt.gz
    fi

    if [[ ! -f data/generated/ol_imdb_sameas.csv ]]; then
        log "Running OL preprocessor (scans 15M+ records, ~few min)..."
        "$PY" preprocessing/ol_preprocess.py \
            --dump "$OL_DUMP" --talent data/talent.csv --outdir data/generated >/dev/null
    fi

    if [[ ! -f data/generated/ol_imdb_sameas_reviewed.csv ]]; then
        log "Auto-curating reviewed sameAs to 5 confirmed authors..."
        awk -F, 'NR==1 || ($14=="high" && ($1=="nm0401076" || $1=="nm0629933" \
            || $1=="nm0001348" || $1=="nm1279581" || $1=="nm0000080"))' \
            data/generated/ol_imdb_sameas.csv > data/generated/ol_imdb_sameas_reviewed.csv
        log "  $(($(wc -l < data/generated/ol_imdb_sameas_reviewed.csv) - 1)) confirmed authors"
    fi

    if [[ ! -f data/generated/ol_author_work.csv ]]; then
        log "Fetching works from OL Search API..."
        "$PY" preprocessing/fetch_ol_works.py \
            --sameas data/generated/ol_imdb_sameas_reviewed.csv \
            --outdir data/generated --max-works 15 >/dev/null
    fi

    if [[ ! -f data/generated/ol_worktype_lookup.csv ]]; then
        log "Building worktype lookup from subjects heuristic..."
        "$PY" - <<'PYEOF'
import csv
def classify(t,s):
    x=((t or "")+" "+(s or "")).lower()
    if "short stor" in x: return "book:ShortStory"
    if "essay" in x: return "book:Essay"
    if any(k in x for k in ["poetry","poesia","poems","poésie"]): return "book:Poetry"
    if any(k in x for k in ["drama","play","theater","theatre"]): return "book:Play"
    if any(k in x for k in ["fiction","novel","roman"]): return "book:Novel"
    return "book:NonFiction"
with open("data/generated/ol_author_work.csv") as f, \
     open("data/generated/ol_worktype_lookup.csv","w",newline="") as o:
    r=csv.DictReader(f); w=csv.writer(o); w.writerow(["ol_work_key","work_type_iri"])
    for row in r: w.writerow([row["ol_work_key"], classify(row["title"], row["subjects"])])
PYEOF
    fi

    log "Running OL works preprocessor..."
    "$PY" preprocessing/ol_preprocess_works.py \
        --works data/generated/ol_author_work.csv \
        --authors data/generated/ol_author.csv \
        --sameas data/generated/ol_imdb_sameas_reviewed.csv \
        --outdir data/generated >/dev/null

    log "RML mapping for books (10)..."
    java -jar "$RMLMAPPER" -m mappings/10_book.rml.ttl \
        -o output/10_book.nt -s ntriples >/dev/null 2>&1
    printf "  10_book                   %s triples\n" "$(wc -l < output/10_book.nt)"
}

cmd_close() {
    [[ -x "$PY" ]] || { echo "Run 'prepare' first"; exit 1; }
    log "Materialising OWL 2 RL closure..."
    "$PY" preprocessing/infer_closure.py 2>/dev/null
}

cmd_serve() {
    [[ -x "$FUSEKI" ]] || { echo "Fuseki not at $FUSEKI_DIR — set FUSEKI_DIR or unzip apache-jena-fuseki-6.0.0.zip"; exit 1; }
    start_fuseki 3030 /culturalworks single
    start_fuseki 3031 /imdb         imdb
    start_fuseki 3032 /books        books
}

cmd_load() {
    log "Loading single endpoint (3030/culturalworks)..."
    drop_all "http://localhost:3030/culturalworks/update" >/dev/null
    bash load_graphs.sh | tail -2

    log "Loading split endpoints (3031/imdb, 3032/books)..."
    drop_all "http://localhost:3031/imdb/update" >/dev/null
    drop_all "http://localhost:3032/books/update" >/dev/null
    bash load_split.sh | tail -3
}

cmd_evaluate() {
    [[ -x "$PY" ]] || { echo "Run 'prepare' first"; exit 1; }
    "$PY" federation_experiment.py "${@:-"--all"}" --out federation_results.json
}

cmd_stop() {
    for pidfile in "$PID_DIR"/*.pid; do
        [[ -f "$pidfile" ]] || continue
        local pid=$(cat "$pidfile") name=$(basename "$pidfile" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping $name (PID $pid)"; kill "$pid"
        fi
        rm -f "$pidfile"
    done
}

cmd_all() {
    cmd_prepare
    cmd_ol
    cmd_close
    cmd_serve
    cmd_load
    cmd_evaluate
}

# -------- dispatch -----------------------------------------------------------

case "${1:-}" in
    prepare|ol|close|serve|load|evaluate|stop|all)
        cmd="cmd_$1"; shift; "$cmd" "$@" ;;
    "" | -h | --help)
        sed -n '2,16p' "$0" ;;
    *)
        echo "Unknown subcommand: $1"; exit 1 ;;
esac