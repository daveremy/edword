"""Manuscript loading and compilation."""

from pathlib import Path
from typing import Optional, List, Tuple

from ..discovery import BookInfo, ProjectStructure, discover_chapters


def compile_manuscript(
    book: BookInfo,
    chapter_range: Optional[Tuple[int, int]] = None,
    include_headers: bool = True
) -> str:
    """
    Compile manuscript from chapter files.

    Args:
        book: BookInfo with chapter paths
        chapter_range: Optional (start, end) chapter numbers (1-indexed, inclusive)
        include_headers: Add chapter headers between sections

    Returns:
        Compiled manuscript text
    """
    chapters = book.chapters

    if chapter_range:
        start, end = chapter_range
        chapters = filter_chapters_by_range(chapters, start, end)

    parts = []
    for chapter_path in chapters:
        content = chapter_path.read_text()

        if include_headers:
            # Extract or generate chapter header
            header = extract_chapter_header(chapter_path, content)
            if header and not content.strip().startswith("#"):
                parts.append(f"# {header}\n\n{content}")
            else:
                parts.append(content)
        else:
            parts.append(content)

    return "\n\n---\n\n".join(parts)


def filter_chapters_by_range(
    chapters: List[Path],
    start: int,
    end: int
) -> List[Path]:
    """
    Filter chapters to a specific range.

    Args:
        chapters: List of chapter paths
        start: Start chapter number (1-indexed)
        end: End chapter number (inclusive)

    Returns:
        Filtered list of chapter paths
    """
    import re

    filtered = []
    for chapter_path in chapters:
        name = chapter_path.stem.lower()
        numbers = re.findall(r'\d+', name)
        if numbers:
            chapter_num = int(numbers[0])
            if start <= chapter_num <= end:
                filtered.append(chapter_path)

    return filtered


def extract_chapter_header(path: Path, content: str) -> str:
    """
    Extract or generate chapter header.

    Args:
        path: Chapter file path
        content: Chapter content

    Returns:
        Chapter header string
    """
    import re

    # Look for existing header in content
    header_match = re.match(r'^#\s+(.+)$', content.strip(), re.MULTILINE)
    if header_match:
        return header_match.group(1)

    # Generate from filename
    name = path.stem
    # chapter-08b-the-watcher -> Chapter 8B: The Watcher
    parts = name.replace("_", "-").split("-")

    # Find chapter number part
    for i, part in enumerate(parts):
        if part.lower().startswith("chapter") or part.lower().startswith("ch"):
            continue
        if re.match(r'\d+[a-z]?', part.lower()):
            num = part.upper()
            title_parts = parts[i+1:] if i+1 < len(parts) else []
            title = " ".join(word.capitalize() for word in title_parts)
            if title:
                return f"Chapter {num}: {title}"
            return f"Chapter {num}"

    return path.stem


def get_manuscript_stats(manuscript: str) -> dict:
    """
    Get statistics about compiled manuscript.

    Args:
        manuscript: Compiled manuscript text

    Returns:
        Dictionary with stats
    """
    import re

    words = len(manuscript.split())
    chars = len(manuscript)
    chapters = len(re.findall(r'^#\s+Chapter', manuscript, re.MULTILINE))

    return {
        "characters": chars,
        "words": words,
        "chapters": chapters,
        "pages_approx": words // 250,  # ~250 words per page
    }
