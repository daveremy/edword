"""Tagged output parsing for LLM responses.

Extracts structured content from within XML-style tags like:
<EDWORD_INDEX>{"characters": [...]}</EDWORD_INDEX>

This provides reliable extraction even when the LLM includes
additional text before/after the tagged content.
"""

import re
import json
from typing import Optional, Any
from dataclasses import dataclass

# Tag names used in prompts
TAG_INDEX = "EDWORD_INDEX"
TAG_VERIFY = "EDWORD_VERIFY"
TAG_QUESTIONS = "EDWORD_QUESTIONS"
TAG_ANSWER = "EDWORD_ANSWER"
TAG_VERDICT = "EDWORD_VERDICT"


@dataclass
class ParseResult:
    """Result of parsing tagged output."""
    success: bool
    content: Optional[str] = None  # Raw string content within tags
    data: Optional[Any] = None     # Parsed JSON data (if valid)
    error: Optional[str] = None    # Error message if parsing failed
    tag_found: bool = False        # Whether the tag was found at all


def extract_tagged_content(response: str, tag: str) -> ParseResult:
    """Extract content from within XML-style tags.

    Uses the LAST match to handle cases where the LLM includes
    examples in its thinking before the final output.

    Args:
        response: Full LLM response text
        tag: Tag name without brackets (e.g., "EDWORD_INDEX")

    Returns:
        ParseResult with content if found

    Example:
        >>> response = "Here's the data: <EDWORD_INDEX>{...}</EDWORD_INDEX>"
        >>> result = extract_tagged_content(response, "EDWORD_INDEX")
        >>> result.content
        '{...}'
    """
    # Build pattern - handle potential whitespace and attributes
    # Escape tag to handle special regex characters safely
    escaped_tag = re.escape(tag)
    # Allow optional attributes/whitespace in opening tag: <TAG>, <TAG >, <TAG attr="val">
    pattern = rf'<{escaped_tag}(?:\s[^>]*)?>\s*(.*?)\s*</{escaped_tag}>'

    # Find the LAST match (the final output, not examples in thinking)
    # Iterate without materializing full list for memory efficiency
    last_match = None
    for match in re.finditer(pattern, response, re.DOTALL | re.IGNORECASE):
        last_match = match

    if last_match is None:
        return ParseResult(
            success=False,
            tag_found=False,
            error=f"Tag <{tag}> not found in response"
        )

    content = last_match.group(1).strip()

    return ParseResult(
        success=True,
        content=content,
        tag_found=True
    )


def extract_json(response: str, tag: str) -> ParseResult:
    """Extract and parse JSON from within tags.

    Args:
        response: Full LLM response text
        tag: Tag name without brackets

    Returns:
        ParseResult with parsed data if successful
    """
    # First extract the content
    result = extract_tagged_content(response, tag)

    if not result.success:
        return result

    # Try to parse as JSON
    try:
        data = json.loads(result.content)
        return ParseResult(
            success=True,
            content=result.content,
            data=data,
            tag_found=True
        )
    except json.JSONDecodeError as e:
        return ParseResult(
            success=False,
            content=result.content,
            tag_found=True,
            error=f"Invalid JSON: {e}"
        )


def extract_index(response: str) -> ParseResult:
    """Extract index data from <EDWORD_INDEX> tags.

    Convenience wrapper for extract_json with INDEX tag.
    """
    return extract_json(response, TAG_INDEX)


def extract_verification(response: str) -> ParseResult:
    """Extract verification data from <EDWORD_VERIFY> tags.

    Convenience wrapper for extract_json with VERIFY tag.
    """
    return extract_json(response, TAG_VERIFY)


def extract_questions(response: str) -> ParseResult:
    """Extract questions list from <EDWORD_QUESTIONS> tags.

    Convenience wrapper for extract_json with QUESTIONS tag.
    Used by CoVe verification to extract generated questions.
    """
    return extract_json(response, TAG_QUESTIONS)


def extract_answer(response: str) -> ParseResult:
    """Extract answer text from <EDWORD_ANSWER> tags.

    Convenience wrapper for extract_tagged_content with ANSWER tag.
    Used by CoVe verification to extract question answers.
    """
    return extract_tagged_content(response, TAG_ANSWER)


def extract_verdict(response: str) -> ParseResult:
    """Extract verdict data from <EDWORD_VERDICT> tags.

    Convenience wrapper for extract_json with VERDICT tag.
    Used by CoVe verification to extract final judgment.
    """
    return extract_json(response, TAG_VERDICT)


def fallback_json_extraction(response: str) -> ParseResult:
    """Attempt to extract JSON without tags as fallback.

    Tries to find JSON-like content in the response when tags are missing.
    This is less reliable but can recover from LLM not following format.

    Looks for:
    1. Content between ```json and ``` code blocks (uses LAST match)
    2. Individual JSON objects, trying each one
    """
    # Try JSON code block first - use last match in case LLM shows examples
    # Case-insensitive to match ```JSON, ```Json, etc.
    # Allow optional space between ``` and json (e.g., ``` json)
    json_blocks = list(re.finditer(r'```\s*json\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE))
    if json_blocks:
        # Try blocks from last to first
        for block in reversed(json_blocks):
            try:
                content = block.group(1).strip()
                data = json.loads(content)
                # Enforce dict type (same as brace-candidate branch)
                if isinstance(data, dict):
                    return ParseResult(
                        success=True,
                        content=content,
                        data=data,
                        tag_found=False  # Tag wasn't found, we used fallback
                    )
            except json.JSONDecodeError:
                continue

    # Try to find JSON objects by balanced brace matching
    # Find each potential JSON object and try to parse it (prefer later ones)
    candidates = _find_json_candidates(response)

    # Try candidates from last to first
    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate)
            # Additional check: make sure it looks like our schema
            if isinstance(data, dict):
                return ParseResult(
                    success=True,
                    content=candidate,
                    data=data,
                    tag_found=False
                )
        except json.JSONDecodeError:
            continue

    return ParseResult(
        success=False,
        tag_found=False,
        error="No valid JSON found in response"
    )


def _find_json_candidates(text: str) -> list[str]:
    """Find potential JSON objects in text using balanced brace matching.

    Returns list of candidate strings that might be valid JSON.
    """
    candidates = []
    i = 0

    while i < len(text):
        if text[i] == '{':
            # Try to find the matching closing brace
            depth = 0
            start = i
            in_string = False
            escape = False

            for j in range(i, len(text)):
                char = text[j]

                if escape:
                    escape = False
                    continue

                if char == '\\' and in_string:
                    escape = True
                    continue

                if char == '"' and not escape:
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:j + 1])
                        i = j
                        break
            i += 1
        else:
            i += 1

    return candidates


def parse_llm_response(
    response: str,
    tag: str,
    allow_fallback: bool = True
) -> ParseResult:
    """Parse LLM response, trying tagged extraction with optional fallback.

    Args:
        response: Full LLM response text
        tag: Expected tag name
        allow_fallback: If True, try fallback extraction if tag not found

    Returns:
        ParseResult with parsed data
    """
    # Try tagged extraction first
    result = extract_json(response, tag)

    if result.success:
        return result

    # If tag found but JSON invalid, don't fallback
    if result.tag_found:
        return result

    # Tag not found - try fallback if allowed
    if allow_fallback:
        fallback_result = fallback_json_extraction(response)
        if fallback_result.success:
            # Mark that we used fallback (tag_found=False)
            return fallback_result

    return result
