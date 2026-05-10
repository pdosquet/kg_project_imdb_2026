# Cultural Works KG — IMDB + Open Library

Three-tier RDF knowledge graph (`cw:` / `film:` / `book:` / `imdb:`) over
IMDB and Open Library, with an Apache Jena Fuseki backend and a federated
SPARQL experiment as the M4 demonstrator.

## Setup

### 1. Java 21

Apache Jena Fuseki 6 requires JDK 21+.

```bash
sudo dnf install java-21-openjdk-devel        # RHEL / AlmaLinux / Rocky 10
java -version
```

Set `JAVA_HOME` if not already exported:

```bash
echo 'export JAVA_HOME=/usr/lib/jvm/java-21-openjdk' >> ~/.bashrc
```

### 2. Apache Jena Fuseki

Download and unzip Fuseki 6.0.0 **into the project root** (already
gitignored). The shell scripts expect it at the relative path
`./apache-jena-fuseki-6.0.0/`.

```bash
curl -O https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-6.0.0.zip
unzip apache-jena-fuseki-6.0.0.zip
chmod +x apache-jena-fuseki-6.0.0/fuseki-server
```

You also need `rmlmapper.jar` in the project root to regenerate triples (rmlmapper-8.1.0-r380-all)
from the RML mappings (download from the RMLio releases page; gitignored).

### 3. Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Pipeline

[run_pipeline.sh](run_pipeline.sh) is the one-shot orchestrator. Each step is idempotent — re-running skips work already done.

| Subcommand | What it does |
|---|---|
| `prepare`  | Compile YARRRML → RML, preprocess IMDB CSVs, run RMLMapper for `01..09` (writes `output/0[1-9]_*.nt`). |
| `ol`       | Open Library pipeline: download authors dump, curate sameAs, fetch works, run RMLMapper for `10_book` (writes `output/10_book.nt`). |
| `close`    | Materialise OWL 2 RL closure over the merged ontology + raw triples (writes `output/closed.nt`). See [CLOSURE_STRATEGY.md](CLOSURE_STRATEGY.md). |
| `serve`    | Start three in-memory Fuseki endpoints: `3030/culturalworks` (oracle), `3031/imdb`, `3032/books`. |
| `load`     | `DROP ALL` then load the closed graph into `3030`, and split raw graphs + `sameAs` bridge into `3031` / `3032`. Calls [load_graphs.sh](load_graphs.sh) and [load_split.sh](load_split.sh). |
| `evaluate` | Run [federation_experiment.py](federation_experiment.py) (writes `federation_results.json`). |
| `stop`     | Kill the running Fuseki processes. |
| `all`      | `prepare` + `ol` + `close` + `serve` + `load` + `evaluate`. |

## Typical workflow

```bash
./run_pipeline.sh all          # end-to-end
./run_pipeline.sh evaluate     # re-run the federation experiment only
./run_pipeline.sh stop         # tear down the Fuseki processes
```

## Endpoints (after `load`)

| Endpoint | Triples | Contents |
|---|---:|---|
| `localhost:3030/culturalworks` | ~30 K | OWL 2 RL closure baseline (oracle) — `closed.nt` + 4 ontologies |
| `localhost:3031/imdb`          | ~14 K | Raw IMDB graphs + `owl:sameAs` bridge + `cw`/`film`/`imdb` ontologies |
| `localhost:3032/books`         | ~1 K  | Raw book graph + `cw`/`book` ontologies |

