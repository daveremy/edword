"""Accumulator for merging chapter indices.

Python-based deterministic merge that:
- Combines facts from multiple chapters
- Resolves entities by canonical ID
- Detects cross-chapter contradictions
- Produces AccumulatedIndex for analysis
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

from .schema import (
    ChapterIndex,
    AccumulatedIndex,
    EntityList,
    Character,
    CharacterFact,
    TimelineEvent,
    Location,
    Artifact,
    WorldFact,
    Terminology,
    NarrativeElement,
    Confidence,
)


@dataclass
class Contradiction:
    """A detected contradiction between chapters."""
    entity_type: str  # "character", "timeline", etc.
    entity_id: str
    predicate: str
    chapter1: str
    value1: str
    chapter2: str
    value2: str
    message: str


@dataclass
class AccumulationResult:
    """Result of accumulating chapter indices."""
    index: AccumulatedIndex
    contradictions: list[Contradiction] = field(default_factory=list)
    chapters_processed: int = 0


class Accumulator:
    """Accumulates chapter indices into a merged index.

    Usage:
        acc = Accumulator(book_id="book1")
        acc.add_chapter(chapter1_index)
        acc.add_chapter(chapter2_index)
        result = acc.get_result()
    """

    def __init__(self, book_id: str):
        self.book_id = book_id
        self._chapters: list[str] = []
        self._contradictions: list[Contradiction] = []

        # Merged data keyed by ID
        self._characters: dict[str, Character] = {}
        self._locations: dict[str, Location] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._terminology: dict[str, Terminology] = {}

        # Lists (not deduplicated by ID)
        self._timeline: list[TimelineEvent] = []
        self._world_facts: list[WorldFact] = []
        self._narrative: list[NarrativeElement] = []

    def add_chapter(self, index: ChapterIndex) -> list[Contradiction]:
        """Add a chapter index to the accumulated index.

        Args:
            index: ChapterIndex to merge

        Returns:
            List of contradictions detected during merge
        """
        chapter_id = index.chapter
        self._chapters.append(chapter_id)
        new_contradictions = []

        # Merge characters
        for char in index.characters:
            contradictions = self._merge_character(char, chapter_id)
            new_contradictions.extend(contradictions)

        # Merge locations
        for loc in index.locations:
            self._merge_location(loc, chapter_id)

        # Merge artifacts
        for art in index.artifacts:
            self._merge_artifact(art, chapter_id)

        # Merge terminology
        for term in index.terminology:
            self._merge_terminology(term, chapter_id)

        # Append timeline events (with deduplication by ID)
        for event in index.timeline:
            if not self._has_timeline_event(event):
                self._timeline.append(event.model_copy(deep=True))

        # Append world facts (copy to avoid mutation)
        for fact in index.world_facts:
            if not self._is_duplicate_world_fact(fact):
                self._world_facts.append(fact.model_copy(deep=True))

        # Append narrative elements (copy to avoid mutation)
        for elem in index.narrative:
            self._narrative.append(elem.model_copy(deep=True))

        self._contradictions.extend(new_contradictions)
        return new_contradictions

    def _merge_character(self, char: Character, chapter_id: str) -> list[Contradiction]:
        """Merge a character, detecting contradictions."""
        contradictions = []

        if char.id not in self._characters:
            # New character - store a deep copy to avoid mutating original
            self._characters[char.id] = char.model_copy(deep=True)
        else:
            # Existing character - merge facts
            existing = self._characters[char.id]

            # Merge mentions
            for mention in char.mentions:
                if mention not in existing.mentions:
                    existing.mentions.append(mention)

            # Merge facts, checking for contradictions
            for new_fact in char.facts:
                contradiction = self._check_fact_contradiction(
                    char.id, new_fact, existing.facts, chapter_id
                )
                if contradiction:
                    contradictions.append(contradiction)
                else:
                    # Add fact if not duplicate (copy to avoid mutation)
                    if not self._is_duplicate_fact(new_fact, existing.facts):
                        existing.facts.append(new_fact.model_copy(deep=True))

            # Merge relationships (copy to avoid mutation)
            for rel in char.relationships:
                if not self._has_relationship(existing.relationships, rel):
                    existing.relationships.append(rel.model_copy(deep=True))

            # Merge state changes (copy to avoid mutation)
            for sc in char.state_changes:
                existing.state_changes.append(sc.model_copy(deep=True))

        return contradictions

    def _check_fact_contradiction(
        self,
        char_id: str,
        new_fact: CharacterFact,
        existing_facts: list[CharacterFact],
        chapter_id: str,
    ) -> Optional[Contradiction]:
        """Check if a new fact contradicts existing facts."""
        for existing in existing_facts:
            # Same predicate, different value = potential contradiction
            if existing.predicate == new_fact.predicate:
                if existing.value != new_fact.value:
                    # Both high confidence = real contradiction
                    if existing.confidence == Confidence.HIGH and new_fact.confidence == Confidence.HIGH:
                        # Get source chapter from evidence if available
                        source_chapter = existing.evidence.chapter if existing.evidence and existing.evidence.chapter else "earlier"
                        return Contradiction(
                            entity_type="character",
                            entity_id=char_id,
                            predicate=new_fact.predicate,
                            chapter1=source_chapter,
                            value1=existing.value,
                            chapter2=chapter_id,
                            value2=new_fact.value,
                            message=f"Character {char_id} has conflicting {new_fact.predicate}: '{existing.value}' vs '{new_fact.value}'",
                        )
        return None

    def _is_duplicate_fact(self, new_fact: CharacterFact, existing_facts: list[CharacterFact]) -> bool:
        """Check if fact is a duplicate (same predicate and value)."""
        for existing in existing_facts:
            if existing.predicate == new_fact.predicate and existing.value == new_fact.value:
                return True
        return False

    def _has_relationship(self, existing: list, new_rel) -> bool:
        """Check if relationship already exists (same target, type, direction, status)."""
        for rel in existing:
            if (rel.to_id == new_rel.to_id and
                rel.type == new_rel.type and
                rel.direction == new_rel.direction and
                rel.status == new_rel.status):
                return True
        return False

    def _has_timeline_event(self, event: TimelineEvent) -> bool:
        """Check if timeline event already exists (by ID)."""
        for existing in self._timeline:
            if existing.id == event.id:
                return True
        return False

    def _is_duplicate_world_fact(self, fact: WorldFact) -> bool:
        """Check if world fact is a duplicate (same category and fact text)."""
        for existing in self._world_facts:
            if existing.category == fact.category and existing.fact == fact.fact:
                return True
        return False

    def _merge_location(self, loc: Location, chapter_id: str):
        """Merge a location."""
        if loc.id not in self._locations:
            # Store a deep copy to avoid mutating original
            self._locations[loc.id] = loc.model_copy(deep=True)
        else:
            existing = self._locations[loc.id]
            # Merge characters present (union)
            for char_id in loc.characters_present:
                if char_id not in existing.characters_present:
                    existing.characters_present.append(char_id)
            # Update description/significance if newly provided
            if loc.description and not existing.description:
                existing.description = loc.description
            if loc.significance and not existing.significance:
                existing.significance = loc.significance

    def _merge_artifact(self, art: Artifact, chapter_id: str):
        """Merge an artifact."""
        if art.id not in self._artifacts:
            # Store a deep copy to avoid mutating original
            self._artifacts[art.id] = art.model_copy(deep=True)
        else:
            # Update status/holder to latest (None is meaningful - e.g., no longer held)
            existing = self._artifacts[art.id]
            # Always update status/holder from the newer chapter
            # (later chapters have more recent state)
            existing.status = art.status
            existing.holder = art.holder

    def _merge_terminology(self, term: Terminology, chapter_id: str):
        """Merge terminology."""
        # Use term text as key
        key = term.term.lower()
        if key not in self._terminology:
            # Store a deep copy to avoid mutating original
            self._terminology[key] = term.model_copy(deep=True)

    def get_result(self) -> AccumulationResult:
        """Get the accumulated index and contradictions."""
        index = AccumulatedIndex(
            book=self.book_id,
            chapters_indexed=self._chapters.copy(),
            last_updated=datetime.now(),
            characters=list(self._characters.values()),
            timeline=self._timeline.copy(),
            locations=list(self._locations.values()),
            artifacts=list(self._artifacts.values()),
            world_facts=self._world_facts.copy(),
            terminology=list(self._terminology.values()),
            narrative=self._narrative.copy(),
        )

        return AccumulationResult(
            index=index,
            contradictions=self._contradictions.copy(),
            chapters_processed=len(self._chapters),
        )

    def get_entity_list(self) -> EntityList:
        """Get entity list for passing to next chapter extraction."""
        return EntityList(
            characters=[(c.id, c.canonical_name) for c in self._characters.values()],
            locations=[(l.id, l.name) for l in self._locations.values()],
            artifacts=[(a.id, a.name) for a in self._artifacts.values()],
        )


def accumulate_chapters(chapters: list[ChapterIndex], book_id: str) -> AccumulationResult:
    """Convenience function to accumulate a list of chapter indices.

    Args:
        chapters: List of ChapterIndex objects in order
        book_id: Book identifier

    Returns:
        AccumulationResult with merged index
    """
    acc = Accumulator(book_id)
    for chapter in chapters:
        acc.add_chapter(chapter)
    return acc.get_result()
