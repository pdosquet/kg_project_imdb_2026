# Setup Guide: YARRRML + RMLMapper

This document explains how to set up your toolchain for M3 mappings.

## Prerequisites

- **Node.js** (v14+) — needed for YARRRML compiler
- **Java** (v11+) — needed for RMLMapper
- **Git** (optional, for downloading RMLMapper)

Check versions:
```bash
node --version
java -version
```

## 1. Install YARRRML Parser

YARRRML is a YAML-based syntax that compiles to RML (the standard W3C format).

```bash
npm install -g @rmlio/yarrrml-parser
```

Test the installation:
```bash
yarrrml-parser --help
```

You should see usage information. If not, you may need to use `npx`:
```bash
npx @rmlio/yarrrml-parser --help
```

## 2. Download RMLMapper

RMLMapper is a Java application that executes RML mappings against CSV/database sources.

**Option A: Download pre-built JAR**

Visit: https://github.com/RMLio/rmlmapper-java/releases

Download the latest `rmlmapper.jar` file and place it in your working directory.

**Option B: Build from source (if JAR not available)**

```bash
git clone https://github.com/RMLio/rmlmapper-java.git
cd rmlmapper-java
mvn clean package -DskipTests
# JAR will be in target/rmlmapper-*-all.jar
cp target/rmlmapper-*-all.jar ../rmlmapper.jar
```

Test the installation:
```bash
java -jar rmlmapper.jar --help
```

## 3. Directory Structure

Organize your M3 work like this:

```
m3_work/
├── rmlmapper.jar              # RMLMapper executable
├── data/
│   ├── talent.csv
│   ├── title.csv
│   ├── title_episode.csv
│   ├── title_principal.csv
│   ├── talent_role.csv
│   ├── talent_title.csv
│   ├── title_aka.csv
│   ├── title_genre.csv
│   ├── genre.csv
│   ├── role.csv
│   ├── language.csv
│   ├── region.csv
│   ├── title_type.csv
│   └── content_type.csv
├── mappings/
│   ├── 01_talent.yarrrml
│   ├── 02_title.yarrrml
│   ├── 03_talent_role.yarrrml
│   ├── ...
│   └── (compiled .rml.ttl files will be generated here)
├── output/
│   ├── talent.nt
│   ├── title.nt
│   ├── ...
│   └── (all RDF outputs go here)
└── docs/
    ├── 01_TALENT_NOTES.md
    ├── SETUP.md (this file)
    └── (process descriptions for each mapping)
```

## 4. Copy CSV Data

Copy all your CSV files from `/mnt/project/` to `m3_work/data/`:

```bash
cp /mnt/project/*.csv m3_work/data/
```

## 5. Execution Pipeline

For each YARRRML mapping file:

```bash
cd m3_work

# Step 1: Compile YARRRML to RML
yarrrml-parser -i mappings/01_talent.yarrrml -o mappings/01_talent.rml.ttl

# Step 2: Execute the mapping
java -jar rmlmapper.jar \
  -m mappings/01_talent.rml.ttl \
  -o output/talent.nt

# Step 3: Verify output
head -20 output/talent.nt
```

Or as a one-liner (if using npx):

```bash
npx @rmlio/yarrrml-parser -i mappings/01_talent.yarrrml -o mappings/01_talent.rml.ttl && \
java -jar rmlmapper.jar -m mappings/01_talent.rml.ttl -o output/talent.nt && \
head -20 output/talent.nt
```

## 6. RMLMapper Output Formats

By default, RMLMapper outputs N-Triples (`.nt`). You can also produce:

- **Turtle** (`.ttl`, more human-readable):
  ```bash
  java -jar rmlmapper.jar -m mapping.rml.ttl -o output.ttl -s turtle
  ```

- **RDF/XML** (`.rdf`):
  ```bash
  java -jar rmlmapper.jar -m mapping.rml.ttl -o output.rdf -s rdfxml
  ```

For M3, N-Triples is fine for testing; you can convert to Turtle for the final deliverable.

## 7. Troubleshooting

### "yarrrml-parser: command not found"

Use `npx` instead:
```bash
npx @rmlio/yarrrml-parser -i mappings/01_talent.yarrrml -o mappings/01_talent.rml.ttl
```

### "No source file found at: talent.csv"

RMLMapper looks for source files **relative to the current working directory**. Make sure:
1. You're executing from `m3_work/`
2. Your `data/` folder exists and contains all CSVs
3. Your YARRRML `sources:` references use the correct relative path:
   ```yaml
   sources:
     - ['data/talent.csv~csv']  # note the data/ prefix if running from m3_work root
   ```

### RMLMapper runs very slowly or hangs

This can happen with large CSV files. Common causes:
- The CSV file is not being parsed correctly (wrong encoding, line endings)
- RMLMapper is trying to load the entire file into memory

For very large mappings, you can run RMLMapper with more memory:
```bash
java -Xmx4g -jar rmlmapper.jar -m mapping.rml.ttl -o output.nt
```

### "Condition evaluation failed"

If you get errors about condition syntax, check:
- Condition syntax is correct: `condition: isNotNull($(column_name))`
- The column name matches exactly (case-sensitive)
- The YARRRML is valid YAML (indentation matters!)

### Output file is empty or very small

Check:
1. Does the mapping compile without errors?
2. Are the source files being read? (Add `echo` statements or check file sizes)
3. Is the IRI template correct? Try a simpler template first:
   ```yaml
   s: http://example.org/person/$(talent_id)
   ```

## 8. Validating the Output

Once you have RDF output, you can validate it:

**Check for syntax errors:**
```bash
# Using Riot (part of Apache Jena)
riot --check output/talent.nt
```

**Convert to readable Turtle:**
```bash
riot --output=turtle output/talent.nt > output/talent.ttl
```

**Count triples:**
```bash
wc -l output/talent.nt
```

**Inspect a specific triple:**
```bash
grep "nm0000080" output/talent.nt
```

Should output something like:
```
<http://localhost:3030/culturalworks/person/nm0000080> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://localhost:3030/culturalworks/ontology#RealPerson> .
<http://localhost:3030/culturalworks/person/nm0000080> <http://localhost:3030/culturalworks/ontology#name> "Orson Welles" .
```

## 9. Next Steps

Once you have this working for `talent`:

1. Test with a simpler file first to validate the setup
2. Create `02_title.yarrrml` for works
3. Create `03_talent_role.yarrrml` for profession links
4. Work up to the complex ones (episode synthesis, reification)

The same pipeline applies to all mappings — only the YARRRML content changes.

