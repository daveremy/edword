"""Check operations for real-time consistency checking.

Compares new text against the accumulated index to detect contradictions.
Focuses on high-confidence extractions: character ages and physical traits.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, Optional

from .common import EdwordError, IndexError as CommonIndexError, load_index
from .index.schema import AccumulatedIndex, Character

# Optional: fuzzy matching for value comparison
try:
    from rapidfuzz import fuzz

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


class CheckError(EdwordError):
    """Error during check operation."""

    pass


# --- Named Types for Better Type Safety ---


class FactResult(NamedTuple):
    """Result from looking up an indexed fact."""

    value: str
    evidence: Optional[dict]


# --- Dataclasses ---


@dataclass
class Conflict:
    """A detected contradiction between text and index."""

    entity_type: str  # "character"
    entity_name: str  # "Greg Walsh"
    field: str  # "age", "eye_color", "hair_color"
    indexed_value: str  # "45"
    text_value: str  # "35"
    severity: str  # "error", "warning"
    confidence: float  # 0.0-1.0
    snippet: str  # Context: "Greg's blue eyes sparkled..."
    indexed_evidence: Optional[dict] = None  # quote, line, chapter from index

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "field": self.field,
            "indexed_value": self.indexed_value,
            "text_value": self.text_value,
            "severity": self.severity,
            "confidence": self.confidence,
            "snippet": self.snippet,
            "indexed_evidence": self.indexed_evidence,
        }


@dataclass
class CharacterMention:
    """A character mention found in text."""

    character: Character
    matched_text: str
    start_pos: int
    end_pos: int


# --- Index Loading ---


def _load_index(
    project_root: Path, book: Optional[str] = None
) -> tuple[AccumulatedIndex, str]:
    """Load accumulated index, using discovery for default book.

    Args:
        project_root: Project root directory
        book: Book name (optional, defaults to first book)

    Returns:
        Tuple of (AccumulatedIndex, book_id)

    Raises:
        CheckError: If no books found, book doesn't exist, or no index
    """
    try:
        return load_index(project_root, book)
    except CommonIndexError as e:
        raise CheckError(str(e)) from e


# --- Text Processing Helpers ---


# Sentence-ending abbreviations that shouldn't split
ABBREVIATIONS = frozenset(
    {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc", "e.g", "i.e"}
)


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Split text into sentences with their positions.

    Returns:
        List of (sentence_text, start_pos, end_pos)
    """
    sentences = []
    last_end = 0

    i = 0
    while i < len(text):
        char = text[i]

        # Check for sentence-ending punctuation
        if char in ".!?":
            is_sentence_end = False

            # Period needs more checks
            if char == ".":
                # Check for abbreviation (word before period)
                word_start = i - 1
                while word_start >= 0 and text[word_start].isalpha():
                    word_start -= 1
                word_start += 1
                word_before = text[word_start:i].lower()

                # Not a sentence end if it's an abbreviation
                if word_before in ABBREVIATIONS:
                    i += 1
                    continue

                # Check if followed by space + capital or end
                if i + 1 >= len(text):
                    is_sentence_end = True
                elif text[i + 1] in " \n\t":
                    # Check if next non-space char is capital or it's end of text
                    j = i + 1
                    while j < len(text) and text[j] in " \n\t":
                        j += 1
                    if j >= len(text) or text[j].isupper():
                        is_sentence_end = True
            else:
                # ! or ? - check if followed by space or end
                if i + 1 >= len(text):
                    is_sentence_end = True
                elif text[i + 1] in " \n\t":
                    is_sentence_end = True

            if is_sentence_end:
                end_pos = i + 1
                sentence = text[last_end:end_pos].strip()
                if sentence:
                    sentences.append((sentence, last_end, end_pos))
                last_end = end_pos

        i += 1

    # Handle remaining text
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            sentences.append((remaining, last_end, len(text)))

    # If no sentences found, treat whole text as one
    if not sentences:
        sentences = [(text.strip(), 0, len(text))]

    return sentences


def _normalize(text: str) -> str:
    """Normalize text for matching (lowercase, stripped)."""
    return text.lower().strip()


def _find_character_mentions(
    text: str, characters: list[Character]
) -> list[CharacterMention]:
    """Find which characters are mentioned in the text.

    Uses single-pass regex for O(N) performance instead of O(N*M).
    Matches longest names first to handle overlaps like "Greg Walsh" vs "Greg".
    Only matches proper names (canonical_name and mentions), no pronouns.

    Returns:
        List of CharacterMention objects, sorted by position
    """
    if not characters:
        return []

    # Build map from lowercase name -> list of (original_name, character)
    # Using list because multiple characters might share a name (unlikely but possible)
    name_to_chars: dict[str, list[tuple[str, Character]]] = {}

    for char in characters:
        names_to_check = [char.canonical_name] + char.mentions
        for name in names_to_check:
            if not name or len(name) < 2:
                continue
            name_lower = name.lower()
            if name_lower not in name_to_chars:
                name_to_chars[name_lower] = []
            name_to_chars[name_lower].append((name, char))

    if not name_to_chars:
        return []

    # Sort names by length (descending) to match longest first
    sorted_names = sorted(name_to_chars.keys(), key=len, reverse=True)

    # Build single regex pattern with all names
    # Escape each name and join with |
    pattern_str = "|".join(re.escape(n) for n in sorted_names)
    pattern = re.compile(r"\b(" + pattern_str + r")\b", re.IGNORECASE)

    mentions = []
    for match in pattern.finditer(text):
        matched_text = match.group()
        matched_lower = matched_text.lower()

        # Look up character(s) for this name
        char_list = name_to_chars.get(matched_lower)
        if char_list:
            # Use first character if multiple match same name
            original_name, char = char_list[0]
            mentions.append(
                CharacterMention(
                    character=char,
                    matched_text=matched_text,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    return mentions


def _get_mention_window(
    text: str, sentences: list[tuple[str, int, int]], mention_start: int, mention_end: int
) -> str:
    """Get the sentence containing the mention.

    Returns the full sentence text for scoped extraction.
    Falls back to surrounding context with word boundaries preserved.
    """
    for sentence, sent_start, sent_end in sentences:
        if sent_start <= mention_start and mention_end <= sent_end:
            return sentence

    # Fallback: expand to nearest whitespace boundaries (not arbitrary char positions)
    start = max(0, mention_start - 50)
    end = min(len(text), mention_end + 50)

    # Expand start to word boundary
    while start > 0 and not text[start - 1].isspace():
        start -= 1

    # Expand end to word boundary
    while end < len(text) and not text[end].isspace():
        end += 1

    return text[start:end].strip()


# --- Negation Detection ---


# Compile negation patterns at module level for performance
NEGATION_WORDS = [
    r"\bnot\b",
    r"\bno\b",
    r"\bnever\b",
    r"\bwithout\b",
    r"\bformer\b",
    r"\bformerly\b",
    r"\bex-",
    r"\bused to\b",
    r"\bhad been\b",
    r"\bno longer\b",
    r"\bwasn't\b",
    r"\bisn't\b",
    r"\bweren't\b",
    r"\baren't\b",
]
NEGATION_PATTERN = re.compile("|".join(NEGATION_WORDS), re.IGNORECASE)

# Number of words to check for negation proximity
NEGATION_PROXIMITY_WORDS = 4


def _has_negation_near(text: str, target_start: int, target_end: int) -> bool:
    """Check if negation words appear near or inside the target span (proximity-based).

    Returns True if:
    1. Negation is inside the target span, OR
    2. Negation is within NEGATION_PROXIMITY_WORDS of the target

    This avoids false negatives like "He was not happy, but his blue eyes shone."
    """
    text_lower = text.lower()

    # Find all negation matches in the text
    for match in NEGATION_PATTERN.finditer(text_lower):
        neg_start, neg_end = match.start(), match.end()

        # Check if negation is INSIDE the target span
        if target_start <= neg_start and neg_end <= target_end:
            return True

        # Check if negation overlaps with target span
        if neg_start < target_end and neg_end > target_start:
            return True

        # Check if negation is close to target (before)
        if neg_end <= target_start:
            between = text[neg_end:target_start]
            word_count = len(between.split())
            if word_count <= NEGATION_PROXIMITY_WORDS:
                return True

        # Check if negation is close to target (after)
        elif neg_start >= target_end:
            between = text[target_end:neg_start]
            word_count = len(between.split())
            if word_count <= NEGATION_PROXIMITY_WORDS:
                return True

    return False


def _has_negation(window: str) -> bool:
    """Check if window contains any negation words.

    Simple window-wide check. Use _has_negation_near for proximity-based
    detection that avoids false positives from distant negations.
    """
    return NEGATION_PATTERN.search(window.lower()) is not None


# --- Age Extraction ---


def _extract_age_in_window(
    window: str, name: str
) -> Optional[tuple[int, float, int, int]]:
    """Extract age claim from window if attributed to name.

    High-confidence patterns only:
    - "[Name] is/was [N] years old"
    - "[Name], [N]," (appositive)
    - "[N]-year-old [Name]"

    Returns:
        (age, confidence, match_start, match_end) or None
    """
    name_escaped = re.escape(name)

    # Pattern 1: "[Name] is/was [N] years old"
    pattern1 = (
        rf"\b{name_escaped}\b[^.]*?\b(?:is|was|turned|turns)\s+(\d{{1,3}})\s*"
        rf"(?:years?\s*old|y\.?o\.?)?"
    )
    match = re.search(pattern1, window, re.IGNORECASE)
    if match:
        age = int(match.group(1))
        if 0 < age < 150:
            return (age, 0.9, match.start(), match.end())

    # Pattern 2: "[Name], [N]," (appositive)
    pattern2 = rf"\b{name_escaped}\b\s*,\s*(\d{{1,3}})\s*,"
    match = re.search(pattern2, window, re.IGNORECASE)
    if match:
        age = int(match.group(1))
        if 0 < age < 150:
            return (age, 0.8, match.start(), match.end())

    # Pattern 3: "[N]-year-old [Name]"
    pattern3 = rf"(\d{{1,3}})\s*-?\s*year\s*-?\s*old\s+{name_escaped}\b"
    match = re.search(pattern3, window, re.IGNORECASE)
    if match:
        age = int(match.group(1))
        if 0 < age < 150:
            return (age, 0.85, match.start(), match.end())

    return None


# --- Physical Trait Extraction ---


# Common color words for eyes/hair
COLORS = frozenset({
    "black", "brown", "blue", "green", "gray", "grey", "hazel", "amber",
    "blonde", "blond", "red", "auburn", "white", "silver", "dark", "light",
    "golden", "chestnut",
})

COLOR_PATTERN = "|".join(COLORS)


def _extract_trait_in_window(
    window: str, name: str
) -> list[tuple[str, str, float, int, int]]:
    """Extract physical trait claims attributed to name.

    High-confidence patterns only:
    - "[Name]'s [color] eyes/hair"
    - "[Name] had/has [color] eyes/hair"

    Returns:
        [(trait_type, value, confidence, match_start, match_end), ...]
    """
    traits = []
    name_escaped = re.escape(name)

    # Pattern 1: "[Name]'s [color] eyes/hair"
    pattern1 = (
        rf"\b{name_escaped}'s\s+(?:(?:\w+)\s+)?({COLOR_PATTERN})\s+(eyes?|hair)"
    )
    for match in re.finditer(pattern1, window, re.IGNORECASE):
        color = match.group(1).lower()
        feature = match.group(2).lower()
        trait_type = "eye_color" if "eye" in feature else "hair_color"
        traits.append((trait_type, color, 0.9, match.start(), match.end()))

    # Pattern 2: "[Name] had/has [color] eyes/hair"
    pattern2 = (
        rf"\b{name_escaped}\b[^.]*?\b(?:had|has|have|with)\s+"
        rf"(?:(?:\w+)\s+)?({COLOR_PATTERN})\s+(eyes?|hair)"
    )
    for match in re.finditer(pattern2, window, re.IGNORECASE):
        color = match.group(1).lower()
        feature = match.group(2).lower()
        trait_type = "eye_color" if "eye" in feature else "hair_color"
        # Avoid duplicates from pattern1
        if not any(t[0] == trait_type and t[1] == color for t in traits):
            traits.append((trait_type, color, 0.8, match.start(), match.end()))

    return traits


# --- Value Comparison ---


def _values_match(indexed: str, found: str) -> bool:
    """Compare values with fuzzy matching if rapidfuzz available."""
    indexed_lower = indexed.lower().strip()
    found_lower = found.lower().strip()

    # Exact match
    if indexed_lower == found_lower:
        return True

    # Handle numeric comparison for ages
    try:
        if int(indexed_lower) == int(found_lower):
            return True
    except ValueError:
        pass

    # Fuzzy match if rapidfuzz available
    if HAS_RAPIDFUZZ:
        ratio = fuzz.token_set_ratio(indexed_lower, found_lower)
        return ratio > 80

    return False


# --- Character Fact Checking ---


def _truncate_snippet(text: str, max_length: int = 100) -> str:
    """Truncate text for snippet display, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def _get_indexed_fact(character: Character, predicate: str) -> Optional[FactResult]:
    """Get a fact value and evidence from indexed character.

    Returns:
        FactResult(value, evidence_dict) or None
    """
    for fact in character.facts:
        if fact.predicate.lower() == predicate.lower():
            evidence_dict = None
            if fact.evidence:
                evidence_dict = {
                    "quote": fact.evidence.quote,
                    "line": fact.evidence.line,
                    "chapter": fact.evidence.chapter,
                }
            return FactResult(value=fact.value, evidence=evidence_dict)
    return None


def _check_character_in_window(
    window: str, character: Character, mention_text: str
) -> list[Conflict]:
    """Check if window contradicts known facts about character.

    Uses proximity-based negation detection to avoid false negatives.
    """
    conflicts = []

    # Check age
    age_result = _extract_age_in_window(window, mention_text)
    if age_result:
        found_age, confidence, match_start, match_end = age_result

        # Skip claims with nearby negation
        if not _has_negation_near(window, match_start, match_end):
            indexed_age = _get_indexed_fact(character, "age")
            if indexed_age and not _values_match(indexed_age.value, str(found_age)):
                conflicts.append(
                    Conflict(
                        entity_type="character",
                        entity_name=character.canonical_name,
                        field="age",
                        indexed_value=indexed_age.value,
                        text_value=str(found_age),
                        severity="error",
                        confidence=confidence,
                        snippet=_truncate_snippet(window),
                        indexed_evidence=indexed_age.evidence,
                    )
                )

    # Check physical traits
    traits = _extract_trait_in_window(window, mention_text)
    for trait_type, trait_value, confidence, match_start, match_end in traits:
        # Skip claims with nearby negation
        if _has_negation_near(window, match_start, match_end):
            continue

        indexed_trait = _get_indexed_fact(character, trait_type)
        if indexed_trait and not _values_match(indexed_trait.value, trait_value):
            conflicts.append(
                Conflict(
                    entity_type="character",
                    entity_name=character.canonical_name,
                    field=trait_type,
                    indexed_value=indexed_trait.value,
                    text_value=trait_value,
                    severity="warning",
                    confidence=confidence,
                    snippet=_truncate_snippet(window),
                    indexed_evidence=indexed_trait.evidence,
                )
            )

    return conflicts


def _deduplicate_conflicts(conflicts: list[Conflict]) -> list[Conflict]:
    """Remove duplicate conflicts based on (character, field, text_value).

    Keeps the first occurrence (highest confidence since we process in order).
    """
    seen = set()
    unique = []

    for c in conflicts:
        key = (c.entity_name, c.field, c.text_value)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# --- Main Check Function ---


def check_text(
    project_root: Path,
    text: str,
    book: Optional[str] = None,
) -> dict[str, Any]:
    """Check text for contradictions against indexed facts.

    Args:
        project_root: Project root directory
        text: Text to check for consistency
        book: Book name (optional, defaults to first book)

    Returns:
        {
            "has_conflicts": bool,
            "conflicts": [...],
            "characters_checked": int,
            "text_length": int,
            "book": str
        }

    Raises:
        CheckError: If text is empty or index cannot be loaded
    """
    if not text or not text.strip():
        raise CheckError("Text cannot be empty")

    # Load index
    index, book_id = _load_index(project_root, book)

    if not index.characters:
        return {
            "has_conflicts": False,
            "conflicts": [],
            "characters_checked": 0,
            "text_length": len(text),
            "book": book_id,
        }

    # Split text into sentences for mention window scoping
    sentences = _split_sentences(text)

    # Find character mentions (single-pass, O(N) algorithm)
    mentions = _find_character_mentions(text, index.characters)

    # Track which characters we checked
    checked_characters = set()
    conflicts = []

    # Check each mention
    for mention in mentions:
        checked_characters.add(mention.character.id)

        # Get the sentence containing this mention
        window = _get_mention_window(
            text, sentences, mention.start_pos, mention.end_pos
        )

        # Check for conflicts
        new_conflicts = _check_character_in_window(
            window, mention.character, mention.matched_text
        )
        conflicts.extend(new_conflicts)

    # Deduplicate conflicts
    conflicts = _deduplicate_conflicts(conflicts)

    return {
        "has_conflicts": len(conflicts) > 0,
        "conflicts": [c.to_dict() for c in conflicts],
        "characters_checked": len(checked_characters),
        "text_length": len(text),
        "book": book_id,
    }
