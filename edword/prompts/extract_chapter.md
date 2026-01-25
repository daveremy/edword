# Chapter Fact Extraction

You are extracting structured facts from a book chapter for editorial analysis.

## Your Task

Read the chapter text below and extract ALL facts into the JSON schema provided. Be thorough but accurate - only extract facts that are explicitly stated or clearly implied in the text.

## Known Entities (for reference)

These entities have been identified in previous chapters. Use their canonical IDs when referencing them:

{entity_list}

If you encounter a new entity not in this list, create a new ID following the pattern:
- Characters: `char_firstname_lastname` (lowercase, underscores)
- Locations: `loc_name` (lowercase, underscores)
- Artifacts: `item_name` (lowercase, underscores)

## Chapter Text

```
{chapter_text}
```

## Output Schema

Extract facts into these seven dimensions. For each fact, include:
- The exact quote or close paraphrase as evidence
- Line number (approximate is fine)
- Character span if possible (start, end)
- Confidence: "high" (explicitly stated), "medium" (clearly implied), "low" (inferred)

Output your response inside `<EDWORD_INDEX>` tags as valid JSON:

<EDWORD_INDEX>
{{
  "characters": [
    {{
      "id": "char_firstname_lastname",
      "canonical_name": "Full Name",
      "mentions": ["Name", "nickname", "title"],
      "facts": [
        {{
          "predicate": "age|occupation|appearance|trait|etc",
          "value": "the fact value",
          "confidence": "high|medium|low",
          "evidence": {{"quote": "exact quote", "line": 123}}
        }}
      ],
      "relationships": [
        {{"to_id": "char_other", "type": "relationship_type", "direction": "to|from|mutual", "status": "active|former|uncertain"}}
      ],
      "state_changes": [
        {{"from": "previous state", "to": "new state", "line": 123}}
      ]
    }}
  ],

  "timeline": [
    {{
      "id": "evt_short_description",
      "event": "What happened",
      "anchor": "absolute date if known, else null",
      "time_ref": "textual time reference",
      "relative_to": [{{"event_id": "evt_xxx", "offset": "X days/hours before/after"}}],
      "ordering_constraints": ["before:evt_xxx", "after:evt_yyy"],
      "evidence": {{"line": 123}}
    }}
  ],

  "locations": [
    {{
      "id": "loc_name",
      "name": "Location Name",
      "characters_present": ["char_id1", "char_id2"],
      "scene_context": "what's happening here",
      "description": "physical description if provided",
      "significance": "why this location matters (optional)",
      "evidence": {{"line": 123}}
    }}
  ],

  "artifacts": [
    {{
      "id": "item_name",
      "name": "Item Name",
      "status": "current status",
      "holder": "char_id or null",
      "evidence": {{"line": 123}}
    }}
  ],

  "world_facts": [
    {{
      "category": "technology|society|history|geography|rules|other",
      "fact": "the world-building fact",
      "confidence": "high|medium|low",
      "evidence": {{"quote": "exact quote", "line": 123}}
    }}
  ],

  "terminology": [
    {{
      "term": "The Term",
      "definition": "what it means in this world",
      "first_mention": true,
      "evidence": {{"line": 123}}
    }}
  ],

  "narrative": [
    {{
      "type": "foreshadowing|callback|setup|payoff|red_herring",
      "element": "description of the narrative element",
      "references_chapter": "chapter name if callback/payoff, else null",
      "evidence": {{"line": 123}}
    }}
  ],

  "pov_scene": {{
    "pov_character": "char_id",
    "tense": "past|present",
    "voice": "first|third_limited|third_omniscient",
    "scene_breaks": [{{"line": 123, "type": "space_break|chapter_break|section"}}]
  }}
}}
</EDWORD_INDEX>

## CRITICAL: Enum Values (use EXACTLY these values)

- **confidence**: `"high"`, `"medium"`, or `"low"` only
- **relationship.status**: `"active"`, `"former"`, or `"uncertain"` only
- **relationship.direction**: `"to"`, `"from"`, or `"mutual"` only
- **world_facts.category**: `"technology"`, `"society"`, `"history"`, `"geography"`, `"rules"`, or `"other"` only
- **narrative.type**: `"foreshadowing"`, `"callback"`, `"setup"`, `"payoff"`, or `"red_herring"` only
- **pov_scene.tense**: `"past"` or `"present"` only
- **pov_scene.voice**: `"first"`, `"third_limited"`, or `"third_omniscient"` only

## Guidelines

1. **Be thorough**: Extract every character mention, every time reference, every location
2. **Be accurate**: Only include facts actually in the text, not assumptions
3. **Use IDs consistently**: Reference existing entity IDs from the entity list
4. **Include evidence**: Every fact should have a quote or line reference
5. **Note confidence**: Mark inferred facts as "low" confidence
6. **Capture relationships**: Note who interacts with whom and how
7. **Track state changes**: If a character's situation changes, note before/after
8. **Use exact enum values**: See CRITICAL section above - use only the listed values

Extract the facts now.
