# M3 Mapping: talent → cw:RealPerson

## Overview

This is the simplest mapping in the project. Each row in `talent.csv` becomes a single `cw:RealPerson` instance in the RDF output.

## YARRRML Syntax Breakdown

### Prefixes
```yaml
prefixes:
  cw: http://localhost:3030/culturalworks/ontology#
  xsd: http://www.w3.org/2001/XMLSchema#
  rdf: http://www.w3.org/1999/02/22-rdf-syntax-ns#
  rdfs: http://www.w3.org/2000/01/rdf-schema#
```

These namespace declarations allow us to write `cw:RealPerson` instead of the full IRI. They will be expanded during compilation.

### Source

```yaml
sources:
  - ['talent.csv~csv']
```

The `~csv` suffix tells the RML engine to treat this as a CSV file. The path is relative to where the mapping is executed.

### Subject (s:)

```yaml
s: http://localhost:3030/culturalworks/person/$(talent_id)
```

This is the IRI template for each person individual. The `$(talent_id)` syntax substitutes the value from the CSV column `talent_id`. 

**Example:** for the row with `talent_id = nm0000080`, the IRI becomes:
```
http://localhost:3030/culturalworks/person/nm0000080
```

This is stable, unique, and uses IMDB's own ID, which is the design decision from M3 requirements.

### Predicates and Objects (po:)

```yaml
po:
  - [rdf:type, cw:RealPerson]
```

This is a shorthand triple: **subject rdf:type cw:RealPerson**. Every person gets this assertion, saying it is of type RealPerson.

```yaml
  - [cw:name, $(talent_name)]
```

A simple property assignment: **person cw:name "Orson Welles"**. `talent_name` is always present in the data.

### Conditional Properties (with condition:)

```yaml
  - p: cw:birthYear
    o: $(birth_year)
    condition: isNotNull($(birth_year))
    datatype: xsd:gYear
```

This is a **conditional property**:
- Only emit the triple if the condition is true
- The condition `isNotNull($(birth_year))` checks if the value is not null (`\N` in the CSV)
- The datatype `xsd:gYear` types the literal as a Gregorian year (not just a plain string or integer)

When the CSV has `\N`, no triple is emitted. When it has `1915`, it becomes:
```
<http://localhost:3030/culturalworks/person/nm0000080> cw:birthYear "1915"^^xsd:gYear .
```

The datatype is critical for temporal reasoning — a reasoner can understand that `"1915"^^xsd:gYear` is a year in the Gregorian calendar, whereas `"1915"^^xsd:integer` would be just a number.

## RDF Output Example

For the first row (`nm0000080, Orson Welles, 1915, 1985`), the output would be:

```turtle
<http://localhost:3030/culturalworks/person/nm0000080> a cw:RealPerson .
<http://localhost:3030/culturalworks/person/nm0000080> cw:name "Orson Welles" .
<http://localhost:3030/culturalworks/person/nm0000080> cw:birthYear "1915"^^xsd:gYear .
<http://localhost:3030/culturalworks/person/nm0000080> cw:deathYear "1985"^^xsd:gYear .
```

For a row with missing death year (`nm0000128, Russell Crowe, 1964, \N`):

```turtle
<http://localhost:3030/culturalworks/person/nm0000128> a cw:RealPerson .
<http://localhost:3030/culturalworks/person/nm0000128> cw:name "Russell Crowe" .
<http://localhost:3030/culturalworks/person/nm0000128> cw:birthYear "1964"^^xsd:gYear .
```

Note: no `deathYear` triple, because the CSV value was null.

## Design Decisions Reflected Here

1. **IRI strategy:** Uses `talent_id` (stable, IMDB-assigned) as the fragment. Consistent with M3 requirements.

2. **Year typing:** Both birth and death years are typed as `xsd:gYear`, not `xsd:integer`. This was a correction in M2 feedback (issue #3). Years should have calendar semantics.

3. **Null handling:** Birth and death years are optional. Rather than emit empty or placeholder values, we skip them entirely with the `condition: isNotNull(...)` pattern. This respects the open-world assumption of RDF.

4. **No extra properties:** We do not invent or infer any properties beyond what appears in the source data. The source has only name, birth year, and death year; the RDF has only those three.

## How to Execute

```bash
# 1. Compile YARRRML to RML
yarrrml-parser -i 01_talent.yarrrml -o 01_talent.rml.ttl

# 2. Run RMLMapper (assuming rmlmapper.jar is in current dir and talent.csv is in data/)
java -jar rmlmapper.jar -m 01_talent.rml.ttl -o talent_output.nt

# 3. View the output (first 20 lines)
head -20 talent_output.nt
```

The output will be in N-Triples format (one triple per line, fully expanded IRIs).

## Next Steps

This mapping is complete and correct. It serves as a template for more complex mappings:
- `talent_role` will be similar but with a `cw:hasProfession` reference to role individuals
- `title_principal` will be more complex, needing reification with conditional roles
- Season synthesis will require preprocessing or more advanced RML features

