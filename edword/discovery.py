"""Project structure discovery and auto-detection."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class BookInfo:
    """Information about a discovered book."""
    name: str
    path: Path
    chapters: List[Path] = field(default_factory=list)

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)


@dataclass
class ProjectStructure:
    """Discovered project structure."""
    root: Path
    manuscripts_dir: Optional[Path] = None
    codex_dir: Optional[Path] = None
    books: List[BookInfo] = field(default_factory=list)
    codex_files: List[Path] = field(default_factory=list)

    @property
    def has_manuscripts(self) -> bool:
        return self.manuscripts_dir is not None and self.manuscripts_dir.exists()

    @property
    def has_codex(self) -> bool:
        return self.codex_dir is not None and self.codex_dir.exists()


def discover_project(
    root: Path,
    manuscripts_path: str = "manuscripts/",
    codex_path: str = "codex/"
) -> ProjectStructure:
    """
    Discover project structure from root directory.

    Args:
        root: Project root directory
        manuscripts_path: Relative path to manuscripts
        codex_path: Relative path to codex

    Returns:
        ProjectStructure with discovered content
    """
    root = Path(root).resolve()
    structure = ProjectStructure(root=root)

    # Find manuscripts directory
    manuscripts_dir = root / manuscripts_path
    if manuscripts_dir.exists():
        structure.manuscripts_dir = manuscripts_dir
        structure.books = discover_books(manuscripts_dir)

    # Find codex directory
    codex_dir = root / codex_path
    if codex_dir.exists():
        structure.codex_dir = codex_dir
        structure.codex_files = discover_codex_files(codex_dir)

    return structure


def discover_books(manuscripts_dir: Path) -> List[BookInfo]:
    """
    Discover books in manuscripts directory.

    Looks for subdirectories named book*, or chapter files directly.

    Args:
        manuscripts_dir: Path to manuscripts directory

    Returns:
        List of discovered books
    """
    books = []

    # Look for book subdirectories
    book_dirs = sorted([
        d for d in manuscripts_dir.iterdir()
        if d.is_dir() and d.name.lower().startswith("book")
    ])

    if book_dirs:
        for book_dir in book_dirs:
            chapters = discover_chapters(book_dir)
            if chapters:
                books.append(BookInfo(
                    name=book_dir.name,
                    path=book_dir,
                    chapters=chapters
                ))
    else:
        # No book subdirs - look for chapters directly
        chapters = discover_chapters(manuscripts_dir)
        if chapters:
            books.append(BookInfo(
                name="book1",
                path=manuscripts_dir,
                chapters=chapters
            ))

    return books


def discover_chapters(book_dir: Path) -> List[Path]:
    """
    Discover chapter files in a book directory.

    Looks in chapters/ subdirectory or directly in book dir.

    Args:
        book_dir: Path to book directory

    Returns:
        Sorted list of chapter file paths
    """
    chapters = []

    # Check for chapters subdirectory
    chapters_dir = book_dir / "chapters"
    if chapters_dir.exists():
        search_dir = chapters_dir
    else:
        search_dir = book_dir

    # Find markdown files that look like chapters
    for f in search_dir.iterdir():
        if f.is_file() and f.suffix.lower() in [".md", ".txt"]:
            name_lower = f.stem.lower()
            # Match chapter-01, ch01, chapter_1, etc.
            if (
                name_lower.startswith("chapter") or
                name_lower.startswith("ch") or
                name_lower.startswith("chap")
            ):
                chapters.append(f)

    # Sort by chapter number if possible
    def chapter_sort_key(path: Path) -> tuple:
        import re
        name = path.stem.lower()
        # Extract numbers from name
        numbers = re.findall(r'\d+', name)
        if numbers:
            # Handle multi-part chapters like 08a, 08b
            suffix = re.search(r'[a-z]$', name)
            suffix_ord = ord(suffix.group()) if suffix else 0
            return (int(numbers[0]), suffix_ord)
        return (999, 0)

    return sorted(chapters, key=chapter_sort_key)


def discover_codex_files(codex_dir: Path) -> List[Path]:
    """
    Discover all markdown files in codex directory.

    Args:
        codex_dir: Path to codex directory

    Returns:
        List of codex file paths
    """
    codex_files = []

    for f in codex_dir.rglob("*.md"):
        if not f.name.startswith("."):
            codex_files.append(f)

    return sorted(codex_files)


def get_book_by_name(
    structure: ProjectStructure,
    name: str
) -> Optional[BookInfo]:
    """
    Get a book by name (case-insensitive, partial match).

    Args:
        structure: Project structure
        name: Book name to find (e.g., "book1", "1")

    Returns:
        BookInfo or None
    """
    name_lower = name.lower()

    for book in structure.books:
        if book.name.lower() == name_lower:
            return book
        # Allow "1" to match "book1"
        if name_lower.isdigit() and book.name.lower() == f"book{name_lower}":
            return book

    return None
