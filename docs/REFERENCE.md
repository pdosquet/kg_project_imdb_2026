# M3 Mapping Strategy: Quick Reference

## What We're Doing

M3 transforms your IMDB CSV tables into RDF conforming to your M2 ontology. The toolchain is:

```
YARRRML (human-readable YAML)
    ↓ (compile with yarrrml-parser)
RML (W3C standard Turtle format)
    ↓ (execute with RMLMapper)
RDF/Turtle or N-Triples output
```

## The Mapping We've Just Created

### `01_talent.yarrrml` → `talent.csv` to `cw:RealPerson`

**What it does:**
- Each row in `talent.csv` becomes a `cw:RealPerson` instance
- IRI: `http://localhost:3030/culturalworks/person/{talent_id}` (uses IMDB's stable ID)
- Properties: `cw:name` (always), `cw:birthYear` and `cw:deathYear` (optional, typed as `xsd:gYear`)
- Null handling: skip birth/death years if the CSV value is `\N`

**Data flow:**
```
talent.csv (1441 rows)
    ↓
01_talent.yarrrml
    ↓
talent_output.nt (1441 persons × ~3 triples each = ~4,300 triples)
```

**Key design decisions:**
1. **IRI choice:** `talent_id` is stable and IMDB-assigned (M3 requirements)
2. **Year datatype:** `xsd:gYear`, not `xsd:integer` (M2 correction)
3. **Null handling:** `condition: isNotNull(...)` skips empty values (open-world assumption)
4. **No inference:** we map exactly what's in the CSV, nothing more

## Roadmap: All Mappings Needed

In rough order of complexity:

| # | Source | Target | Complexity | Notes |
|---|--------|--------|-----------|-------|
| 1 | `talent` | `cw:RealPerson` | ⭐ Simple | ✅ Done |
| 2 | `title` | `cw:CreativeWork` etc. | ⭐ Simple | Straightforward row→instance |
| 3 | `talent_role` | `cw:hasProfession` | ⭐ Simple | Link to role individuals (lookup) |
| 4 | `title_genre` | `cw:hasGenre` | ⭐ Simple | Link to genre individuals (lookup) |
| 5 | `talent_title` | `cw:associatedWith` | ⭐ Simple | Plain binary property, no reification |
| 6 | `title_aka` | `cw:AlternativeTitle` | ⭐⭐ Medium | Class with properties; skip `is_original_title=1` |
| 7 | `title_aka_title_type` | `cw:hasTitleType` | ⭐⭐ Medium | Join two tables, lookup type individuals |
| 8 | `region` | `cw:Region` / `imdb:X-code` | ⭐⭐ Medium | Branch: ISO codes mint new, X-codes reference existing |
| 9 | `language` | `cw:Language` | ⭐⭐ Medium | Mint individuals from ISO codes |
| 10 | `title_principal` | `film:FilmContribution` | ⭐⭐⭐ Hard | Reified ternary (person-work-role); character portrayal |
| 11 | `title_episode` | Synthesised `cw:WorkVolume` | ⭐⭐⭐ Hard | Season synthesis from composite key |

## Files Created So Far

```
/home/claude/m3_work/
├── 01_talent.yarrrml          ← The mapping (YAML source)
├── 01_talent.rml.ttl          ← Compiled to RML (Turtle format, for reference)
├── 01_TALENT_NOTES.md         ← Explanation of this mapping
├── SETUP.md                   ← Toolchain setup instructions
└── REFERENCE.md               ← This file
```

## Immediate Next Steps

### 1. Verify the Toolchain Works

```bash
cd /home/claude/m3_work

# Copy data files
cp /mnt/project/*.csv data/

# Install tools (if not already done)
npm install -g @rmlio/yarrrml-parser
# (download rmlmapper.jar from GitHub if needed)

# Compile and run the talent mapping
yarrrml-parser -i 01_talent.yarrrml -o 01_talent_compiled.rml.ttl
java -jar rmlmapper.jar -m 01_talent_compiled.rml.ttl -o talent_output.nt

# View the output
head -20 talent_output.nt
wc -l talent_output.nt  # Should be ~4,300 triples
```

### 2. Create the Next Simple Mapping: `02_title.yarrrml`

Key decisions for the `title` mapping:
- **Class logic:** Use `content_type_id` to pick `cw:CreativeWork` vs `cw:WorkSeries` vs `cw:WorkUnit`
- **Work type:** Map `content_type_id` to `film:WorkType` individuals (Movie, TvSeries, TvEpisode, etc.)
- **Years:** Type `start_year` and `end_year` as `xsd:gYear`; only emit `end_year` for series
- **Adult flag:** Type `is_adult` as `xsd:boolean`
- **Runtime:** Type `runtime_minutes` as `xsd:integer`

### 3. Create the Next: `03_talent_role.yarrrml`

This needs a **lookup mapping**:
- Read `talent_role.csv` (talent_id, role_id)
- Join `role_id` with a static role individual mapping table
- Emit: `cw:RealPerson` → `cw:hasProfession` → role individual

Example:
```yaml
mappings:
  TalentRoleMapping:
    sources:
      - ['data/talent_role.csv~csv']
    s: http://localhost:3030/culturalworks/person/$(talent_id)
    po:
      - p: cw:hasProfession
        o: $(role_id)  # but needs to resolve to actual individual IRI!
```

The tricky part: mapping `role_id` (integer) to the actual IRI like `cw:Director`. This can be done in RML with a `parentTriplesMap` (a join), or we can pre-compute a lookup CSV. The approach depends on whether your RMLMapper version supports FnO (YARRRML functions).

## Key Patterns to Remember

### Pattern 1: Simple Property
```yaml
- [predicate, $(column)]
```

### Pattern 2: Optional Property with Condition
```yaml
- p: predicate
  o: $(column)
  condition: isNotNull($(column))
  datatype: xsd:SomeType
```

### Pattern 3: Constant Literal
```yaml
- [predicate, "some literal value"]
```

### Pattern 4: Constant Individual
```yaml
- [rdf:type, SomeClass]
```

### Pattern 5: IRI with Template
```yaml
s: http://localhost:3030/culturalworks/path/$(column)
```

### Pattern 6: Multiple IRIs from One Row (conditionally)
This is for reification and is covered in later mappings.

## Report Structure (for later)

Your M3 report should have these sections:

1. **Introduction:** Why RML, why YARRRML, tool choices
2. **Mapping Organisation:** Explain the directory structure and naming (01_, 02_, etc.)
3. **IRI Strategy:** Justify every IRI pattern (title uses `title_id`, person uses `talent_id`, etc.)
4. **Source-to-Ontology Mappings:** For each table, describe the mapping logic
5. **Null Handling:** How you deal with missing data
6. **Lookup Tables and Role Mapping:** How you resolve role_id → `cw:Director`, etc.
7. **Complex Cases:** Season synthesis, reification, multi-valued character names
8. **Process and Tooling:** What tool you chose, what problems arose, how you solved them
9. **Generated RDF Statistics:** Total triples, breakdown by table

## Common Gotchas

1. **Null values in IMDB:** They use `\N`, not empty strings or NULL. The `isNotNull()` condition handles this.
2. **Datatype matters:** `xsd:gYear` vs `xsd:integer` affects reasoning. Use the M2 types.
3. **URI vs IRI vs URL:** IRIs are IRIs (can have non-ASCII), use angle brackets: `<http://...>`
4. **Relative paths:** RMLMapper looks for CSV files relative to where you run the command
5. **YARRRML indentation:** YAML is whitespace-sensitive. Use 2 spaces, never tabs.

## Questions to Answer in Your Report

- Why did you choose `talent_id` as the IRI fragment for persons?
- Why is `end_year` only emitted for `WorkSeries` and not all titles?
- How do you handle the `actress` → `cw:Actor` merge in the mapping?
- Why do you synthesise seasons instead of having them in the source?
- What was the most complex part of the mapping process?

## Success Criteria

When M3 is done, you should have:

✅ All YARRRML mapping files written and tested
✅ A compiled set of RML files (one per mapping)
✅ RDF output for all tables (in N-Triples or Turtle)
✅ A technical report explaining every choice
✅ Statistics on the generated RDF (triple counts, etc.)
✅ Evidence that the RDF conforms to the M2 ontology

