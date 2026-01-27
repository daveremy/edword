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


class IndexVersionMismatch(EdwordError):
    """Index schema version doesn't match current version."""

    def __init__(self, book_id: str, index_version: int, current_version: int):
        self.book_id = book_id
        self.index_version = index_version
        self.current_version = current_version
        super().__init__(
            f"Index for '{book_id}' uses schema v{index_version}, "
            f"current is v{current_version}."
        )


def load_index(
    project_root: Path,
    book: Optional[str] = None,
    check_version: bool = True,
) -> tuple[AccumulatedIndex, str]:
    """Load accumulated index, using discovery for default book.

    This is the canonical implementation used by both query and check modules.

    Args:
        project_root: Project root directory
        book: Book name (optional, defaults to first book)
        check_version: Whether to check schema version (default True)

    Returns:
        Tuple of (AccumulatedIndex, book_id)

    Raises:
        IndexError: If no books found, book doesn't exist, or no index
        IndexVersionMismatch: If index schema version doesn't match current version
    """
    from .index.schema import INDEX_SCHEMA_VERSION

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

    # Check schema version
    if check_version:
        index_version = getattr(index, 'schema_version', 0)  # Missing = v0
        if index_version != INDEX_SCHEMA_VERSION:
            raise IndexVersionMismatch(book_id, index_version, INDEX_SCHEMA_VERSION)

    return index, book_id
