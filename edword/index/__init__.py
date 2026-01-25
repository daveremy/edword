"""Index module for chapter fact extraction and accumulation."""

from .schema import (
    # Enums
    Confidence,
    RelationshipDirection,
    RelationshipStatus,
    NarrativeType,
    Tense,
    Voice,
    SceneBreakType,
    WorldFactCategory,
    # Models
    Evidence,
    CharacterFact,
    Relationship,
    StateChange,
    Character,
    RelativeTimeRef,
    TimelineEvent,
    Location,
    Artifact,
    WorldFact,
    Terminology,
    NarrativeElement,
    SceneBreak,
    POVScene,
    ChapterIndex,
    AccumulatedIndex,
    EntityList,
)

from .validation import (
    ValidationResult,
    IndexValidationError,
    validate_json,
    validate_chapter_index,
    validate_with_retry,
    format_validation_errors,
    coerce_to_schema,
)

from .extractor import (
    ExtractionConfig,
    ExtractionResult,
    extract_chapter,
    extract_chapter_simple,
    compute_file_hash,
)

from .accumulator import (
    Accumulator,
    AccumulationResult,
    Contradiction,
    accumulate_chapters,
)

from .storage import IndexStorage

__all__ = [
    # Enums
    "Confidence",
    "RelationshipDirection",
    "RelationshipStatus",
    "NarrativeType",
    "Tense",
    "Voice",
    "SceneBreakType",
    "WorldFactCategory",
    # Models
    "Evidence",
    "CharacterFact",
    "Relationship",
    "StateChange",
    "Character",
    "RelativeTimeRef",
    "TimelineEvent",
    "Location",
    "Artifact",
    "WorldFact",
    "Terminology",
    "NarrativeElement",
    "SceneBreak",
    "POVScene",
    "ChapterIndex",
    "AccumulatedIndex",
    "EntityList",
    # Validation
    "ValidationResult",
    "IndexValidationError",
    "validate_json",
    "validate_chapter_index",
    "validate_with_retry",
    "format_validation_errors",
    "coerce_to_schema",
    # Extractor
    "ExtractionConfig",
    "ExtractionResult",
    "extract_chapter",
    "extract_chapter_simple",
    "compute_file_hash",
    # Accumulator
    "Accumulator",
    "AccumulationResult",
    "Contradiction",
    "accumulate_chapters",
    # Storage
    "IndexStorage",
]
