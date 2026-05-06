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

## Shell scripts

| Script | Purpose |
|---|---|
| [load_graphs.sh](load_graphs.sh) | **Single-endpoint topology.** POSTs every `ontologies/*.ttl` and `output/*.nt` file into one Fuseki dataset at `http://localhost:3030/culturalworks`, then prints the total triple count. Used for the baseline / oracle in the federation experiment. |
| [fuseki_two_endpoints.sh](fuseki_two_endpoints.sh) | **Launches two in-memory Fuseki servers** for the split topology: IMDB on port 3030 (`/imdb`) and Books on port 3031 (`/books`). Runs in the foreground; Ctrl+C stops both. |
| [load_split.sh](load_split.sh) | **Two-endpoint loader.** Loads the `cw:` + `film:` + `imdb:` ontologies and IMDB data into port 3030, the `cw:` + `book:` ontologies and book data into port 3031, and places the `owl:sameAs` bridge triples on the IMDB side so it can federate to the book endpoint. |

## Typical workflow

```bash
# Single-endpoint baseline
./apache-jena-fuseki-6.0.0/fuseki-server --mem --port 3030 /culturalworks &
bash load_graphs.sh

# Two-endpoint topology (separate terminal)
bash fuseki_two_endpoints.sh
bash load_split.sh

# Run the federation experiment
python3 federation_experiment.py --all --out results.json
```

