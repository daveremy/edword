"""Common utilities shared across edword modules."""

from pathlib import Path
from typing import Optional

from .discovery import discover_project, get_book_by_name
from .index.schema import AccumulatedIndex
from .index.storage import IndexStorage


class EdwordError(Exception):
    """Base exception for edword operations."""

    pass


class IndexError(EdwordError):
    """Error related to index operations."""

    pass


def load_index(
    project_root: Path, book: Optional[str] = None
) -> tuple[AccumulatedIndex, str]:
    """Load accumulated index, using discovery for default book.

    This is the canonical implementation used by both query and check modules.

    Args:
        project_root: Project root directory
        book: Book name (optional, defaults to first book)

    Returns:
        Tuple of (AccumulatedIndex, book_id)

    Raises:
        IndexError: If no books found, book doesn't exist, or no index
    """
    project = discover_project(project_root)

    if not project.books:
        raise IndexError("No books found in project")

    # Determine book_id
    if book:
        book_info = get_book_by_name(project, book)
        if not book_info:
            available = [b.name for b in project.books]
            raise IndexError(f"Book '{book}' not found. Available: {available}")
        book_id = book_info.name
    else:
        book_id = project.books[0].name

    # Load index
    storage = IndexStorage(project_root)
    index = storage.load_accumulated_index(book_id)

    if index is None:
        raise IndexError(f"No index for '{book_id}'. Run 'edword index build' first.")

    return index, book_id
