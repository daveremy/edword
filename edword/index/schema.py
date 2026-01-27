"""Pydantic models for the chapter index schema.

Defines the seven dimensions extracted from each chapter:
1. Characters - people, their facts, relationships, state changes
2. Timeline - events with temporal ordering
3. Locations - places and who's there
4. Artifacts - significant objects
5. World Facts - world-building details
6. Terminology - defined terms
7. Narrative - foreshadowing, callbacks, etc.

Plus POV/Scene metadata and the wrapper ChapterIndex.
"""

from datetime import datetime
from enum import Enum
from typing import ClassVar, Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Schema Version ---
# Increment when schema changes require re-extraction of indices.
# Old indices without this field default to version 0.
INDEX_SCHEMA_VERSION = 1


# --- Enums ---

class Confidence(str, Enum):
    """Confidence level for extracted facts."""
    HIGH = "high"      # Explicitly stated in text
    MEDIUM = "medium"  # Clearly implied
    LOW = "low"        # Inferred


class RelationshipDirection(str, Enum):
    """Direction of a relationship."""
    TO = "to"
    FROM = "from"
    MUTUAL = "mutual"


class RelationshipStatus(str, Enum):
    """Status of a relationship."""
    ACTIVE = "active"
    FORMER = "former"
    UNCERTAIN = "uncertain"


class NarrativeType(str, Enum):
    """Type of narrative element."""
    FORESHADOWING = "foreshadowing"
    CALLBACK = "callback"
    SETUP = "setup"
    PAYOFF = "payoff"
    RED_HERRING = "red_herring"


class Tense(str, Enum):
    """Narrative tense."""
    PAST = "past"
    PRESENT = "present"


class Voice(str, Enum):
    """Narrative voice/POV."""
    FIRST = "first"
    THIRD_LIMITED = "third_limited"
    THIRD_OMNISCIENT = "third_omniscient"


class SceneBreakType(str, Enum):
    """Type of scene break."""
    SPACE_BREAK = "space_break"
    CHAPTER_BREAK = "chapter_break"
    SECTION = "section"


class WorldFactCategory(str, Enum):
    """Category of world fact."""
    TECHNOLOGY = "technology"
    SOCIETY = "society"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    RULES = "rules"  # Rules of how things work in this world
    OTHER = "other"


# --- Evidence Models ---

class Evidence(BaseModel):
    """Evidence for a fact with source location."""
    quote: Optional[str] = Field(None, description="Exact or close quote from text")
    line: int = Field(0, description="Approximate line number")
    char_span: Optional[tuple[int, int]] = Field(None, description="Character offset range (start, end)")
    chapter: Optional[str] = Field(None, description="Chapter ID for provenance tracking")


# --- Character Models ---

class CharacterFact(BaseModel):
    """A fact about a character."""
    predicate: str = Field(..., description="Type of fact: age, occupation, appearance, trait, etc.")
    value: str = Field(..., description="The fact value")
    confidence: Confidence = Field(Confidence.HIGH)
    evidence: Evidence = Field(default_factory=Evidence)


class Relationship(BaseModel):
    """A relationship between characters."""
    to_id: str = Field(..., description="ID of the related character")
    type: str = Field(..., description="Type of relationship: parent_of, friend, colleague, etc.")
    direction: RelationshipDirection = Field(RelationshipDirection.TO)
    status: RelationshipStatus = Field(RelationshipStatus.ACTIVE)


class StateChange(BaseModel):
    """A change in a character's state within this chapter."""
    model_config = ConfigDict(populate_by_name=True)

    from_state: str = Field(..., alias="from", description="Previous state")
    to_state: str = Field(..., alias="to", description="New state")
    line: int = Field(0)


class Character(BaseModel):
    """A character extracted from a chapter."""
    id: str = Field(..., description="Canonical ID: char_firstname_lastname")
    canonical_name: str = Field(..., description="Full canonical name")
    mentions: list[str] = Field(default_factory=list, description="All name variations used")
    facts: list[CharacterFact] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    state_changes: list[StateChange] = Field(default_factory=list)


# --- Timeline Models ---

class RelativeTimeRef(BaseModel):
    """A relative time reference to another event."""
    event_id: str = Field(..., description="ID of the referenced event")
    offset: str = Field(..., description="Time offset: '2 days after', '1 week before', etc.")


class TimelineEvent(BaseModel):
    """A timeline event extracted from a chapter."""
    id: str = Field(..., description="Canonical ID: evt_short_description")
    event: str = Field(..., description="What happened")
    anchor: Optional[str] = Field(None, description="Absolute date if known")
    time_ref: Optional[str] = Field(None, description="Textual time reference from text")
    relative_to: list[RelativeTimeRef] = Field(default_factory=list)
    ordering_constraints: list[str] = Field(default_factory=list, description="e.g., ['before:evt_x', 'after:evt_y']")
    evidence: Evidence = Field(default_factory=Evidence)


# --- Location Models ---

class Location(BaseModel):
    """A location/setting extracted from a chapter."""
    id: str = Field(..., description="Canonical ID: loc_name")
    name: str = Field(..., description="Location name")
    characters_present: list[str] = Field(default_factory=list, description="Character IDs present")
    scene_context: Optional[str] = Field(None, description="What's happening at this location")
    description: Optional[str] = Field(None, description="Description of the location")
    significance: Optional[str] = Field(None, description="Why this location matters")
    evidence: Evidence = Field(default_factory=Evidence)


# --- Artifact Models ---

class Artifact(BaseModel):
    """A significant object/artifact extracted from a chapter."""
    id: str = Field(..., description="Canonical ID: item_name")
    name: str = Field(..., description="Item name")
    status: Optional[str] = Field(None, description="Current status/condition")
    holder: Optional[str] = Field(None, description="Character ID who has it, or null")
    evidence: Evidence = Field(default_factory=Evidence)


# --- World Fact Models ---

class WorldFact(BaseModel):
    """A world-building fact."""
    category: WorldFactCategory = Field(WorldFactCategory.OTHER)
    fact: str = Field(..., description="The world-building fact")
    confidence: Confidence = Field(Confidence.HIGH)
    evidence: Evidence = Field(default_factory=Evidence)


# --- Terminology Models ---

class Terminology(BaseModel):
    """A defined term in the world."""
    term: str = Field(..., description="The term")
    definition: str = Field(..., description="What it means in this world")
    first_mention: bool = Field(False, description="Is this the first time the term appears?")
    evidence: Evidence = Field(default_factory=Evidence)


# --- Narrative Models ---

class NarrativeElement(BaseModel):
    """A narrative element like foreshadowing or callback."""
    type: NarrativeType = Field(...)
    element: str = Field(..., description="Description of the narrative element")
    references_chapter: Optional[str] = Field(None, description="Chapter referenced (for callbacks/payoffs)")
    evidence: Evidence = Field(default_factory=Evidence)


# --- POV/Scene Models ---

class SceneBreak(BaseModel):
    """A scene break within the chapter."""
    line: int = Field(...)
    type: SceneBreakType = Field(SceneBreakType.SPACE_BREAK)


class POVScene(BaseModel):
    """POV and scene metadata for the chapter."""
    pov_character: Optional[str] = Field(None, description="Character ID of POV character")
    tense: Tense = Field(Tense.PAST)
    voice: Voice = Field(Voice.THIRD_LIMITED)
    scene_breaks: list[SceneBreak] = Field(default_factory=list)


# --- Main Chapter Index ---

class ChapterIndex(BaseModel):
    """Complete index for a single chapter.

    This is what gets extracted from each chapter and saved as JSON.
    """
    # Metadata
    book: str = Field(..., description="Book identifier: book1, book2, etc.")
    chapter: str = Field(..., description="Chapter identifier: chapter-01, etc.")
    source_path: str = Field(..., description="Path to source file")
    source_hash: str = Field(..., description="Hash of source file for change detection")
    extracted_at: datetime = Field(default_factory=datetime.now)

    # Seven dimensions
    characters: list[Character] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    world_facts: list[WorldFact] = Field(default_factory=list)
    terminology: list[Terminology] = Field(default_factory=list)
    narrative: list[NarrativeElement] = Field(default_factory=list)

    # Scene metadata
    pov_scene: POVScene = Field(default_factory=POVScene)

    # Schema version (default 0 for legacy indices without this field)
    schema_version: int = Field(default=0)


# --- Accumulated Index ---

class AccumulatedIndex(BaseModel):
    """Merged index across all chapters in a book.

    This is built by the accumulator from individual ChapterIndex files.
    """
    book: str = Field(...)
    chapters_indexed: list[str] = Field(default_factory=list, description="List of chapter IDs included")
    last_updated: datetime = Field(default_factory=datetime.now)

    # Schema version (default 0 for legacy indices without this field)
    schema_version: int = Field(default=0)

    # Merged dimensions - same structure but accumulated across chapters
    characters: list[Character] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    world_facts: list[WorldFact] = Field(default_factory=list)
    terminology: list[Terminology] = Field(default_factory=list)
    narrative: list[NarrativeElement] = Field(default_factory=list)


# --- Entity List (for pronoun resolution) ---

class EntityList(BaseModel):
    """Minimal entity list passed to extractor for pronoun resolution.

    Contains just IDs and names, not full facts - keeps context small.
    Has a configurable size limit to prevent context bloat for later chapters.
    """
    characters: list[tuple[str, str]] = Field(default_factory=list, description="(id, canonical_name) pairs")
    locations: list[tuple[str, str]] = Field(default_factory=list, description="(id, name) pairs")
    artifacts: list[tuple[str, str]] = Field(default_factory=list, description="(id, name) pairs")

    # Default limits to prevent context bloat
    DEFAULT_CHARACTER_LIMIT: ClassVar[int] = 100
    DEFAULT_LOCATION_LIMIT: ClassVar[int] = 50
    DEFAULT_ARTIFACT_LIMIT: ClassVar[int] = 50

    def to_text(self) -> str:
        """Format entity list as text for prompt."""
        lines = []

        if self.characters:
            lines.append("Characters:")
            for id, name in self.characters:
                lines.append(f"  - {name} ({id})")

        if self.locations:
            lines.append("\nLocations:")
            for id, name in self.locations:
                lines.append(f"  - {name} ({id})")

        if self.artifacts:
            lines.append("\nArtifacts:")
            for id, name in self.artifacts:
                lines.append(f"  - {name} ({id})")

        return "\n".join(lines) if lines else "(No entities from previous chapters)"

    def truncate(
        self,
        max_characters: int = DEFAULT_CHARACTER_LIMIT,
        max_locations: int = DEFAULT_LOCATION_LIMIT,
        max_artifacts: int = DEFAULT_ARTIFACT_LIMIT,
    ) -> "EntityList":
        """Return a truncated copy of this entity list.

        Keeps the most recent entities (assumes they're in insertion order).
        """
        return EntityList(
            characters=self.characters[-max_characters:] if len(self.characters) > max_characters else self.characters,
            locations=self.locations[-max_locations:] if len(self.locations) > max_locations else self.locations,
            artifacts=self.artifacts[-max_artifacts:] if len(self.artifacts) > max_artifacts else self.artifacts,
        )

    @classmethod
    def from_accumulated(
        cls,
        acc: AccumulatedIndex,
        max_characters: int = DEFAULT_CHARACTER_LIMIT,
        max_locations: int = DEFAULT_LOCATION_LIMIT,
        max_artifacts: int = DEFAULT_ARTIFACT_LIMIT,
    ) -> "EntityList":
        """Build entity list from accumulated index with optional limits."""
        characters = [(c.id, c.canonical_name) for c in acc.characters]
        locations = [(l.id, l.name) for l in acc.locations]
        artifacts = [(a.id, a.name) for a in acc.artifacts]

        # Apply limits (keep most recent if over limit)
        if len(characters) > max_characters:
            characters = characters[-max_characters:]
        if len(locations) > max_locations:
            locations = locations[-max_locations:]
        if len(artifacts) > max_artifacts:
            artifacts = artifacts[-max_artifacts:]

        return cls(
            characters=characters,
            locations=locations,
            artifacts=artifacts,
        )
