"""Codex loading and compilation."""

from pathlib import Path
from typing import List, Optional, Dict

from ..discovery import ProjectStructure


def load_codex(
    codex_dir: Path,
    categories: Optional[List[str]] = None
) -> str:
    """
    Load and compile codex files.

    Args:
        codex_dir: Path to codex directory
        categories: Optional list of category subdirectories to include

    Returns:
        Compiled codex text
    """
    if not codex_dir.exists():
        return ""

    files = []

    if categories:
        # Load specific categories
        for category in categories:
            cat_dir = codex_dir / category
            if cat_dir.exists():
                files.extend(sorted(cat_dir.rglob("*.md")))
    else:
        # Load all codex files
        files = sorted(codex_dir.rglob("*.md"))

    # Filter out hidden files and compile
    parts = []
    for f in files:
        if not f.name.startswith("."):
            content = f.read_text()
            # Get relative path for header
            rel_path = f.relative_to(codex_dir)
            header = f"## Codex: {rel_path}"
            parts.append(f"{header}\n\n{content}")

    return "\n\n---\n\n".join(parts)


def load_codex_by_category(codex_dir: Path) -> Dict[str, str]:
    """
    Load codex files organized by category.

    Args:
        codex_dir: Path to codex directory

    Returns:
        Dictionary mapping category name to compiled content
    """
    if not codex_dir.exists():
        return {}

    categories = {}

    for item in codex_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            content = load_codex(codex_dir, categories=[item.name])
            if content:
                categories[item.name] = content

    # Also load root-level files
    root_files = [f for f in codex_dir.iterdir() if f.is_file() and f.suffix == ".md"]
    if root_files:
        parts = []
        for f in sorted(root_files):
            if not f.name.startswith("."):
                content = f.read_text()
                parts.append(f"## {f.stem}\n\n{content}")
        if parts:
            categories["_root"] = "\n\n---\n\n".join(parts)

    return categories


def get_character_codex(codex_dir: Path) -> str:
    """
    Load character-specific codex entries.

    Args:
        codex_dir: Path to codex directory

    Returns:
        Compiled character codex
    """
    return load_codex(codex_dir, categories=["characters"])


def get_timeline_codex(codex_dir: Path) -> str:
    """
    Load timeline-specific codex entries.

    Args:
        codex_dir: Path to codex directory

    Returns:
        Compiled timeline codex
    """
    return load_codex(codex_dir, categories=["timeline"])


def get_codex_stats(codex_dir: Path) -> dict:
    """
    Get statistics about codex.

    Args:
        codex_dir: Path to codex directory

    Returns:
        Dictionary with stats
    """
    if not codex_dir.exists():
        return {"files": 0, "categories": 0, "characters": 0}

    categories = set()
    files = 0
    characters_count = 0

    for f in codex_dir.rglob("*.md"):
        if not f.name.startswith("."):
            files += 1
            # Get category from parent dir
            rel_path = f.relative_to(codex_dir)
            if len(rel_path.parts) > 1:
                categories.add(rel_path.parts[0])

            # Count character files
            if "character" in str(f.parent).lower():
                characters_count += 1

    return {
        "files": files,
        "categories": len(categories),
        "characters": characters_count,
    }
