# M3 Milestone: Getting Started with RML Mappings

## What You Have

This folder contains everything you need to understand and execute the **first M3 mapping** (talent → cw:RealPerson) and the toolchain setup:

### Files Included

1. **`01_talent.yarrrml`** — The actual mapping in YARRRML syntax (human-readable YAML)
2. **`01_talent.rml.ttl`** — The compiled RML version (W3C standard format, for reference)
3. **`01_TALENT_NOTES.md`** — Detailed explanation of this mapping, including:
   - YARRRML syntax breakdown
   - Design decisions explained
   - RDF output examples
4. **`SETUP.md`** — Complete toolchain setup guide:
   - How to install YARRRML and RMLMapper
   - Directory structure recommendations
   - Step-by-step execution instructions
   - Troubleshooting section
5. **`REFERENCE.md`** — Quick reference and roadmap:
   - All mappings you need to create (in order of complexity)
   - Key patterns and gotchas
   - Report structure guidance

---

## Quick Start (5 minutes)

### 1. Read the Mapping

Open **`01_TALENT_NOTES.md`** and read the "YARRRML Syntax Breakdown" section. This shows you:
- What the mapping does
- How the syntax works
- What RDF is produced

### 2. Understand the Data

The `talent.csv` file has 1,441 people:
- `talent_id`: IMDB identifier (e.g., `nm0000080`)
- `talent_name`: Person's name (always present)
- `birth_year`: Birth year (nullable, shown as `\N` in CSV)
- `death_year`: Death year (nullable)

The mapping converts this to RDF triples like:
```turtle
<http://localhost:3030/culturalworks/person/nm0000080> a cw:RealPerson .
<http://localhost:3030/culturalworks/person/nm0000080> cw:name "Orson Welles" .
<http://localhost:3030/culturalworks/person/nm0000080> cw:birthYear "1915"^^xsd:gYear .
<http://localhost:3030/culturalworks/person/nm0000080> cw:deathYear "1985"^^xsd:gYear .
```

### 3. Set Up the Tools (once)

Follow **`SETUP.md`** sections 1–3 to:
- Install YARRRML parser with `npm install -g @rmlio/yarrrml-parser`
- Download RMLMapper JAR from GitHub
- Create a folder structure like:
  ```
  m3_work/
  ├── rmlmapper.jar
  ├── data/           ← CSV files go here
  ├── mappings/       ← YARRRML files go here
  └── output/         ← RDF output goes here
  ```

### 4. Test with Talent (10 minutes)

```bash
cd m3_work

# Copy CSV files
cp /mnt/project/*.csv data/

# Compile YARRRML to RML
yarrrml-parser -i mappings/01_talent.yarrrml -o mappings/01_talent.rml.ttl

# Execute the mapping
java -jar rmlmapper.jar -m mappings/01_talent.rml.ttl -o output/talent.nt

# Check the output
head -20 output/talent.nt
wc -l output/talent.nt  # Should be ~4,300 lines (triples)
```

If this works, you've successfully:
- Compiled YARRRML to RML ✅
- Executed RML mappings ✅
- Generated RDF output ✅

---

## Next: Create More Mappings

Once the talent mapping works, create the other mappings in this order:

### Easy (similar to talent)
- **02_title.yarrrml**: Map `title.csv` to `cw:CreativeWork`
- **03_talent_role.yarrrml**: Map `talent_role.csv` to `cw:hasProfession` links
- **04_title_genre.yarrrml**: Map `title_genre.csv` to `cw:hasGenre` links

### Medium (more properties, conditional logic)
- **05_title_aka.yarrrml**: Map `title_aka.csv` to `cw:AlternativeTitle` (skip `is_original_title=1`)
- **06_region.yarrrml**: Map `region.csv` with branching (ISO → new individual, X-code → existing IRI)
- **07_language.yarrrml**: Map `language.csv` to `cw:Language` individuals

### Hard (reification, synthesis)
- **08_title_principal.yarrrml**: Map to `film:FilmContribution` with character minting
- **09_title_episode.yarrrml**: Synthesise seasons from `title_episode.csv`

See **`REFERENCE.md`** for a roadmap table showing complexity and notes for each.

---

## Key Design Decisions (M2 → M3)

These appear in the talent mapping and carry through to all others:

1. **IRI Strategy**: Use IMDB-assigned IDs (`talent_id`, `title_id`) as stable fragments.
   - Why: They're stable, unique, and source-assigned (better than UUID generation).

2. **Year Typing**: Use `xsd:gYear`, not `xsd:integer`.
   - Why: Calendar semantics enable temporal reasoning (M2 correction #3).

3. **Null Handling**: Emit nothing for null values, don't emit placeholders.
   - Why: RDF open-world assumption — missing data ≠ false data.

4. **Lookup Mapping**: Role IDs resolve to ontology individuals (`cw:Director`), not string lookups.
   - Why: M2 established that roles are pre-populated individuals, not literals.

5. **No Extra Inference**: Map exactly what's in the CSV, nothing more.
   - Why: Keeps mappings transparent and verifiable.

---

## The Talent Mapping Explained (1-minute version)

```yaml
prefixes:
  cw: http://localhost:3030/culturalworks/ontology#
  xsd: http://www.w3.org/2001/XMLSchema#

mappings:
  TalentMapping:
    sources:
      - ['talent.csv~csv']        # Read talent.csv
    s: http://localhost:3030/culturalworks/person/$(talent_id)  # IRI for each person
    po:
      - [rdf:type, cw:RealPerson]              # Every person is a RealPerson
      - [cw:name, $(talent_name)]              # Name from CSV
      - p: cw:birthYear
        o: $(birth_year)
        condition: isNotNull($(birth_year))    # Only if not null
        datatype: xsd:gYear                    # Type as year, not integer
      - p: cw:deathYear
        o: $(death_year)
        condition: isNotNull($(death_year))
        datatype: xsd:gYear
```

**In English:**
- For each row in `talent.csv`:
  - Create an IRI: `person/{talent_id}`
  - Assert it's a `cw:RealPerson`
  - Add their name
  - If birth year is present, add it typed as `xsd:gYear`
  - If death year is present, add it typed as `xsd:gYear`

---

## Common Questions

### Q: Why YARRRML instead of writing RML directly?
**A:** YARRRML is much shorter and easier to read/maintain. The compiler converts it to standard RML automatically. YARRRML is 80% shorter while expressing the same thing.

### Q: What's the difference between RML and YARRRML?
**A:** YARRRML is a YAML syntax for writing RML. It's not a different language — just a friendlier way to write the same RML. The compiler (`yarrrml-parser`) converts YARRRML → RML (Turtle format).

### Q: Do I need to understand RML Turtle syntax?
**A:** No, not if you use YARRRML. But we've included the compiled `01_talent.rml.ttl` file so you can see what it looks like after compilation. It's verbose, which is why YARRRML is better.

### Q: Can I run all mappings at once?
**A:** You can create a bash script to compile and execute all of them in sequence:
```bash
for f in mappings/*.yarrrml; do
  yarrrml-parser -i "$f" -o "${f%.yarrrml}.rml.ttl"
  java -jar rmlmapper.jar -m "${f%.yarrrml}.rml.ttl" -o "output/${f##*/%.yarrrml}.nt"
done
```

### Q: How do I debug if a mapping goes wrong?
**A:** See the **Troubleshooting** section in `SETUP.md`. Common issues:
- CSV file path is wrong (use relative paths from where you run the command)
- Column name doesn't match exactly (case-sensitive)
- YAML indentation is wrong (use 2 spaces, not tabs)
- `isNotNull()` condition syntax — should be `condition: isNotNull($(column_name))`

### Q: What if I have questions about specific mappings?
**A:** Each mapping gets a detailed `.md` file explaining it. See:
- `01_TALENT_NOTES.md` — talent mapping explained
- (future) `02_TITLE_NOTES.md`, `03_ROLE_NOTES.md`, etc.

---

## File Organization

```
📁 Project Structure
├── 00_START_HERE.md          ← You are here
├── 01_talent.yarrrml         ← The mapping itself
├── 01_talent.rml.ttl         ← Compiled version (reference)
├── 01_TALENT_NOTES.md        ← Detailed explanation
├── SETUP.md                  ← Toolchain setup (do this first!)
└── REFERENCE.md              ← Roadmap and patterns

📁 After You Create Directories (following SETUP.md):
m3_work/
├── rmlmapper.jar
├── data/
│   ├── talent.csv
│   ├── title.csv
│   ├── title_principal.csv
│   └── (all other CSVs)
├── mappings/
│   ├── 01_talent.yarrrml          ← Copy from here
│   ├── 02_title.yarrrml           ← Create next
│   ├── 03_talent_role.yarrrml     ← Create after
│   └── (etc.)
└── output/
    ├── talent.nt                  ← Generated
    ├── title.nt                   ← Generated
    └── (etc.)
```

---

## The Learning Path

1. **Read `SETUP.md`** (10 min) — understand the toolchain
2. **Read `01_TALENT_NOTES.md`** (15 min) — understand YARRRML syntax
3. **Run the talent mapping** (5 min) — get it working end-to-end
4. **Create `02_title.yarrrml`** (30 min) — apply the patterns to a new mapping
5. **Create `03_talent_role.yarrrml`** (20 min) — learn about lookup mapping
6. **Create the remaining mappings** (2-3 hours) — progressively harder
7. **Write the M3 report** (2 hours) — document decisions and process

**Total estimated time:** 4-5 hours to create all mappings, plus report writing.

---

## What the Report Should Cover

Once you've created all mappings, your M3 technical report should include:

1. **Tool Choices** — why YARRRML + RMLMapper
2. **Mapping Organisation** — how you structured the mappings
3. **IRI Strategies** — justify each IRI pattern (talent uses talent_id, etc.)
4. **Source-to-Ontology Mappings** — for each table, explain the mapping logic
5. **Null Handling** — how you deal with `\N` values
6. **Lookups and Role Mapping** — how role_id resolves to individuals
7. **Complex Cases** — season synthesis, reification, etc.
8. **Process and Challenges** — what tools you chose, problems encountered, solutions
9. **RDF Statistics** — total triples generated, breakdown by table
10. **Appendix** — include actual YARRRML/RML files

The report ties every mapping decision back to M1 and M2 choices. For example:
- "We use `title_id` as the IRI fragment because M1 established it as the stable primary key."
- "We skip `is_original_title=1` rows because M2's AlternativeTitle justification states the original is already captured as `cw:originalTitle` on the work."
- "We type years as `xsd:gYear` because M2 feedback corrected the initial use of `xsd:integer`."

---

## Success Checklist

By the end of M3, you should have:

- [ ] YARRRML compiler and RMLMapper installed
- [ ] All 9-11 YARRRML mapping files created and tested
- [ ] All source CSVs mapped to RDF output
- [ ] RDF output validated (syntactically correct)
- [ ] Mapping decisions documented (one `.md` file per mapping)
- [ ] M3 technical report written (explaining organisation, IRI strategies, process)
- [ ] All files included in final submission

---

## Next Action

1. **Read `SETUP.md`** — Get your toolchain ready
2. **Read `01_TALENT_NOTES.md`** — Understand how the talent mapping works
3. **Copy `01_talent.yarrrml` to your working directory** and execute it
4. **Create `02_title.yarrrml`** — Apply the same patterns to titles

You've got this! The talent mapping is the simplest and most complete. All others follow the same basic structure, with variations for more complex cases (joins, reification, synthesis).

---

**Questions?** Check the relevant `.md` file:
- **Setup issues?** → `SETUP.md`
- **Syntax or YARRRML questions?** → `01_TALENT_NOTES.md`
- **Roadmap or patterns?** → `REFERENCE.md`

