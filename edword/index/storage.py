"""Storage layer for index JSON files.

Handles saving/loading ChapterIndex and AccumulatedIndex to disk.
Manages the .edword/index/ directory structure.

Uses atomic writes (write to temp, then rename) for data safety.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .schema import ChapterIndex, AccumulatedIndex, INDEX_SCHEMA_VERSION
from .extractor import compute_file_hash


class IndexStorage:
    """Manages index file storage.

    Directory structure:
        .edword/
        ├── index/
        │   ├── book1/
        │   │   ├── chapter-01.json
        │   │   ├── chapter-02.json
        │   │   └── accumulated.json
        │   └── book2/
        │       └── ...
        └── hashes.json  # Track source file hashes for incremental
    """

    def __init__(self, root: Path, index_dir: str = ".edword/index"):
        """Initialize storage.

        Args:
            root: Project root directory
            index_dir: Relative path to index directory
        """
        self.root = Path(root)
        self.index_path = self.root / index_dir
        self._hashes_path = self.root / ".edword" / "hashes.json"

    def ensure_dirs(self, book_id: str):
        """Ensure index directories exist."""
        book_path = self.index_path / book_id
        book_path.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, content: str):
        """Write content to file atomically (write to temp, then rename).

        This prevents partial writes from corrupting data if interrupted.
        """
        # Create temp file in the same directory (same filesystem for atomic rename)
        dir_path = path.parent
        dir_path.mkdir(parents=True, exist_ok=True)

        # Write to temp file
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            # Atomic rename (on POSIX systems)
            os.replace(tmp_path, path)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # --- Chapter Index ---

    def save_chapter_index(self, index: ChapterIndex):
        """Save a chapter index to disk (atomic write)."""
        self.ensure_dirs(index.book)

        path = self._chapter_path(index.book, index.chapter)
        data = index.model_dump(mode="json")
        content = json.dumps(data, indent=2, default=str)

        self._atomic_write(path, content)

        # Update hash tracking
        self._update_hash(index.book, index.chapter, index.source_hash)

    def load_chapter_index(self, book_id: str, chapter_id: str) -> Optional[ChapterIndex]:
        """Load a chapter index from disk."""
        path = self._chapter_path(book_id, chapter_id)

        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding='utf-8'))
        return ChapterIndex.model_validate(data)

    def chapter_exists(self, book_id: str, chapter_id: str) -> bool:
        """Check if chapter index exists."""
        return self._chapter_path(book_id, chapter_id).exists()

    def list_chapter_indices(self, book_id: str) -> list[str]:
        """List all chapter IDs that have been indexed."""
        book_path = self.index_path / book_id
        if not book_path.exists():
            return []

        chapters = []
        for path in sorted(book_path.glob("*.json")):
            if path.stem != "accumulated":
                chapters.append(path.stem)
        return chapters

    def delete_chapter_index(self, book_id: str, chapter_id: str) -> bool:
        """Delete a chapter index and its hash entry."""
        path = self._chapter_path(book_id, chapter_id)
        if path.exists():
            path.unlink()
            # Also remove the hash entry to avoid stale metadata
            self._delete_hash(book_id, chapter_id)
            return True
        return False

    def _delete_hash(self, book_id: str, chapter_id: str):
        """Remove hash entry for a deleted chapter."""
        hashes = self._load_hashes()
        if book_id in hashes and chapter_id in hashes[book_id]:
            del hashes[book_id][chapter_id]
            # Clean up empty book entry
            if not hashes[book_id]:
                del hashes[book_id]
            self._save_hashes(hashes)

    def _chapter_path(self, book_id: str, chapter_id: str) -> Path:
        """Get path to chapter index file."""
        return self.index_path / book_id / f"{chapter_id}.json"

    # --- Accumulated Index ---

    def save_accumulated_index(self, index: AccumulatedIndex):
        """Save accumulated index to disk (atomic write)."""
        self.ensure_dirs(index.book)

        path = self._accumulated_path(index.book)
        data = index.model_dump(mode="json")
        content = json.dumps(data, indent=2, default=str)

        self._atomic_write(path, content)

    def load_accumulated_index(self, book_id: str) -> Optional[AccumulatedIndex]:
        """Load accumulated index from disk."""
        path = self._accumulated_path(book_id)

        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding='utf-8'))
        return AccumulatedIndex.model_validate(data)

    def _accumulated_path(self, book_id: str) -> Path:
        """Get path to accumulated index file."""
        return self.index_path / book_id / "accumulated.json"

    # --- Hash Tracking (for incremental) ---

    def _load_hashes(self) -> dict:
        """Load hash tracking file."""
        if not self._hashes_path.exists():
            return {}
        try:
            return json.loads(self._hashes_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            # Corrupted file - return empty and let next save overwrite
            return {}

    def _save_hashes(self, hashes: dict):
        """Save hash tracking file (atomic write)."""
        content = json.dumps(hashes, indent=2)
        self._atomic_write(self._hashes_path, content)

    def _update_hash(self, book_id: str, chapter_id: str, source_hash: str):
        """Update hash for a chapter."""
        hashes = self._load_hashes()
        if book_id not in hashes:
            hashes[book_id] = {}
        hashes[book_id][chapter_id] = source_hash
        self._save_hashes(hashes)

    def get_stored_hash(self, book_id: str, chapter_id: str) -> Optional[str]:
        """Get stored hash for a chapter."""
        hashes = self._load_hashes()
        return hashes.get(book_id, {}).get(chapter_id)

    def needs_reindex(self, book_id: str, chapter_id: str, source_path: Path) -> bool:
        """Check if chapter needs re-indexing based on source file hash AND schema version."""
        # Check basic prerequisites
        if not self.chapter_exists(book_id, chapter_id):
            return True

        stored_hash = self.get_stored_hash(book_id, chapter_id)
        if not stored_hash:
            return True

        # Check if source file has changed
        if stored_hash != compute_file_hash(source_path):
            return True

        # Check schema version (handles breaking changes)
        try:
            index = self.load_chapter_index(book_id, chapter_id)
            return index is None or getattr(index, 'schema_version', 0) < INDEX_SCHEMA_VERSION
        except ValidationError:
            return True

    # --- Bulk Operations ---

    def clear_book(self, book_id: str) -> int:
        """Clear all index files for a book. Returns count of files deleted."""
        book_path = self.index_path / book_id
        if not book_path.exists():
            return 0

        count = 0
        for path in book_path.glob("*.json"):
            path.unlink()
            count += 1

        # Remove empty directory
        if not any(book_path.iterdir()):
            book_path.rmdir()

        # Clear hashes
        hashes = self._load_hashes()
        if book_id in hashes:
            del hashes[book_id]
            self._save_hashes(hashes)

        return count

    def clear_all(self) -> int:
        """Clear all index files. Returns count of files deleted."""
        if not self.index_path.exists():
            return 0

        count = 0
        for book_path in self.index_path.iterdir():
            if book_path.is_dir():
                for path in book_path.glob("*.json"):
                    path.unlink()
                    count += 1
                if not any(book_path.iterdir()):
                    book_path.rmdir()

        # Clear all hashes
        if self._hashes_path.exists():
            self._hashes_path.unlink()

        return count

    def get_stats(self, book_id: Optional[str] = None) -> dict:
        """Get statistics about stored indices."""
        stats = {
            "books": [],
            "total_chapters": 0,
            "total_size_bytes": 0,
        }

        if not self.index_path.exists():
            return stats

        for book_path in sorted(self.index_path.iterdir()):
            if not book_path.is_dir():
                continue

            if book_id and book_path.name != book_id:
                continue

            book_stats = {
                "book_id": book_path.name,
                "chapters": [],
                "has_accumulated": False,
                "size_bytes": 0,
            }

            for path in sorted(book_path.glob("*.json")):
                size = path.stat().st_size
                book_stats["size_bytes"] += size
                stats["total_size_bytes"] += size

                if path.stem == "accumulated":
                    book_stats["has_accumulated"] = True
                else:
                    book_stats["chapters"].append(path.stem)
                    stats["total_chapters"] += 1

            stats["books"].append(book_stats)

        return stats
