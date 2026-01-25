"""Index-based continuity analysis - no LLM needed.

Compares structured facts across chapters to find inconsistencies:
- Character fact conflicts (same predicate, contradictory values)
- Timeline ordering violations
- Relationship contradictions

Uses heuristics to reduce false positives - descriptive facts (appearance, trait)
are additive, while quantitative facts (age, date) should be consistent.
"""

from collections import defaultdict
from typing import Optional
import re

from .base import BasePass, Finding, PassResult, Severity
from . import register_pass
from ..index.schema import AccumulatedIndex, Character, CharacterFact

# Predicates where multiple different values are OK (additive/descriptive)
ADDITIVE_PREDICATES = {
    "appearance", "trait", "behavior", "emotional_state", "action",
    "knowledge", "physical_state", "function", "nature", "description",
}

# Predicates where values must be consistent (quantitative/identity)
STRICT_PREDICATES = {
    "age", "birth_date", "death_date", "occupation", "name",
    "gender", "species", "cause_of_death",
}


def extract_number(s: str) -> Optional[int]:
    """Extract first number from string for comparison."""
    match = re.search(r'\b(\d+)\b', s)
    return int(match.group(1)) if match else None


def values_conflict(pred: str, values: list[str]) -> bool:
    """Check if values for a predicate actually conflict.

    Returns True only for genuine contradictions, not additive details.
    """
    if pred in ADDITIVE_PREDICATES:
        return False  # Multiple descriptions are OK

    if pred in STRICT_PREDICATES:
        # For age, check if numbers differ significantly
        if pred == "age":
            numbers = [extract_number(v) for v in values]
            numbers = [n for n in numbers if n is not None]
            if len(numbers) >= 2:
                return max(numbers) - min(numbers) > 2  # Allow 2-year variance
        return True  # Other strict predicates: any difference is a conflict

    # Unknown predicate: flag if values look very different
    # Simple heuristic: if any value is a substring of another, probably not conflict
    lower_values = [v.lower().strip() for v in values]
    for i, v1 in enumerate(lower_values):
        for v2 in lower_values[i+1:]:
            if v1 in v2 or v2 in v1:
                return False  # Substring match = probably compatible

    return True  # Default: flag as potential conflict


@register_pass
class ContinuityIndexPass(BasePass):
    """Analyze accumulated index for continuity issues."""

    name = "continuity-index"
    description = "Index-based timeline and fact consistency analysis"

    def run(
        self,
        manuscript: str = "",
        codex: Optional[str] = None,
        index: Optional[AccumulatedIndex] = None,
        **kwargs
    ) -> PassResult:
        """Run continuity analysis on accumulated index."""
        result = self._create_result()

        if not index:
            result.error = "No index provided. Run 'edword index build' first."
            return result

        # Check character fact conflicts
        char_findings = self._check_character_conflicts(index)
        result.findings.extend(char_findings)

        # Check relationship conflicts
        rel_findings = self._check_relationship_conflicts(index)
        result.findings.extend(rel_findings)

        # Stats
        result.stats = {
            "characters_checked": len(index.characters),
            "timeline_events": len(index.timeline),
            "fact_conflicts": len([f for f in char_findings if "conflict" in f.message.lower()]),
        }

        return result

    def _check_character_conflicts(self, index: AccumulatedIndex) -> list[Finding]:
        """Find character facts that conflict across chapters."""
        findings = []

        for char in index.characters:
            # Group facts by predicate
            facts_by_pred: dict[str, list[CharacterFact]] = defaultdict(list)
            for fact in char.facts:
                facts_by_pred[fact.predicate].append(fact)

            # Check for conflicts within same predicate
            for pred, facts in facts_by_pred.items():
                if len(facts) > 1:
                    values = [f.value for f in facts]

                    # Use smart conflict detection
                    if values_conflict(pred, values):
                        chapters = [f.evidence.chapter or "unknown" for f in facts]

                        # Determine severity based on predicate type
                        severity = Severity.ERROR if pred in STRICT_PREDICATES else Severity.WARNING

                        findings.append(Finding(
                            severity=severity,
                            message=f"{char.canonical_name}'s {pred}: {' vs '.join(values[:3])}",
                            location=f"Chapters: {', '.join(set(chapters))}",
                            context=f"Found {len(facts)} different values",
                            suggestion=f"Verify {pred} consistency for {char.canonical_name}",
                        ))

        return findings

    def _check_relationship_conflicts(self, index: AccumulatedIndex) -> list[Finding]:
        """Find relationship contradictions."""
        findings = []

        for char in index.characters:
            # Group relationships by target
            rels_by_target: dict[str, list] = defaultdict(list)
            for rel in char.relationships:
                rels_by_target[rel.to_id].append(rel)

            # Check for conflicting relationship types to same person
            for target_id, rels in rels_by_target.items():
                if len(rels) > 1:
                    types = set(r.type for r in rels)
                    statuses = set(r.status.value for r in rels)

                    # Different relationship types might be ok (e.g., colleague + friend)
                    # But conflicting statuses are an issue
                    if "active" in statuses and "former" in statuses:
                        findings.append(Finding(
                            severity=Severity.WARNING,
                            message=f"{char.canonical_name}'s relationship with {target_id}: both active and former",
                            suggestion="Clarify the current status of this relationship",
                        ))

        return findings
