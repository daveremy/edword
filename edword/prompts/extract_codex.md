# Codex Fact Extraction

You are extracting structured facts from a codex (world bible) file. The codex contains the canonical "ground truth" for a book project.

## Your Task

Read the codex content below and extract ALL facts into the JSON schema. Codex facts are considered authoritative - mark them as "high" confidence unless the codex itself indicates uncertainty.

## Codex Content

File: {file_path}

```
{codex_text}
```

## Output Schema

Extract facts relevant to the codex file type. Output inside `<EDWORD_INDEX>` tags as valid JSON.

For character files, focus on: facts, relationships, timeline of their life
For location files, focus on: description, history, significance
For timeline files, focus on: events with dates/ordering
For concept files, focus on: world_facts, terminology

<EDWORD_INDEX>
{{
  "characters": [
    {{
      "id": "char_firstname_lastname",
      "canonical_name": "Full Name",
      "mentions": ["aliases", "titles"],
      "facts": [
        {{
          "predicate": "birth_date|age|occupation|appearance|trait|backstory|etc",
          "value": "the fact value",
          "confidence": "high",
          "evidence": {{"quote": "from codex", "line": 0}}
        }}
      ],
      "relationships": [
        {{"to_id": "char_other", "type": "relationship_type", "direction": "to|from", "status": "active|former"}}
      ]
    }}
  ],

  "timeline": [
    {{
      "event": "What happened",
      "anchor": "absolute date if known",
      "time_ref": "textual reference",
      "ordering_constraints": ["before:evt_xxx", "after:evt_yyy"],
      "evidence": {{"line": 0}}
    }}
  ],

  "locations": [
    {{
      "id": "loc_name",
      "name": "Location Name",
      "description": "what this place is",
      "significance": "why it matters",
      "evidence": {{"line": 0}}
    }}
  ],

  "world_facts": [
    {{
      "category": "technology|society|history|geography|rules|other",
      "fact": "the world-building fact",
      "confidence": "high",
      "evidence": {{"quote": "from codex", "line": 0}}
    }}
  ],

  "terminology": [
    {{
      "term": "The Term",
      "definition": "canonical definition",
      "evidence": {{"line": 0}}
    }}
  ]
}}
</EDWORD_INDEX>

## Guidelines

1. **Codex is authoritative**: These are the canonical facts to validate manuscripts against
2. **Extract everything**: Every fact, date, relationship, detail matters for validation
3. **Create IDs**: Use consistent ID patterns (char_*, loc_*, item_*)
4. **Note relationships**: Especially important for character files
5. **Capture timeline**: Birth dates, ages, event dates are critical for continuity

Extract the facts now.
