"""Index-based codex validation - compare manuscript index against codex.

This pass loads the codex files directly and compares character facts,
relationships, and other details against what was extracted from the manuscript.

Requires: codex files in standard format (character YAML/MD files)
"""

import re
from pathlib import Path
from typing import Optional
import yaml

from .base import BasePass, Finding, PassResult, Severity
from . import register_pass
from ..index.schema import AccumulatedIndex


def parse_codex_characters(codex_dir: Path) -> dict:
    """Parse character files from codex directory.

    Returns dict mapping character name (lowercase) to their facts.
    """
    characters = {}

    # Look for character files in various locations
    char_dirs = [
        codex_dir / "characters",
        codex_dir / "people",
        codex_dir,
    ]

    for char_dir in char_dirs:
        if not char_dir.exists():
            continue

        for path in char_dir.glob("*.md"):
            char_data = parse_character_md(path)
            if char_data and char_data.get("name"):
                name_key = char_data["name"].lower()
                characters[name_key] = char_data

        for path in char_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(path.read_text())
                if data and isinstance(data, dict):
                    name = data.get("name", path.stem)
                    characters[name.lower()] = data
            except Exception:
                pass

    return characters


def parse_character_md(path: Path) -> dict:
    """Parse character info from markdown file."""
    content = path.read_text()
    data = {"name": path.stem.replace("-", " ").title()}

    # Extract from YAML frontmatter first
    frontmatter_match = re.match(r'^---\n(.+?)\n---', content, re.DOTALL)
    if frontmatter_match:
        try:
            fm_data = yaml.safe_load(frontmatter_match.group(1))
            if fm_data:
                data.update(fm_data)
        except Exception:
            pass

    # Extract name from header
    name_match = re.search(r'^#\s+(.+?)(?:\s*\(|$)', content, re.MULTILINE)
    if name_match:
        data["name"] = name_match.group(1).strip()

    # Extract structured fields from markdown body (various formats)
    # Format: **Age:** 45 or - **Age:** 45 or **Age**: 45
    patterns = {
        "age": r'[-*]*\s*\*\*Age[:\s]*\*\*[:\s]*(\d+)',
        "birth_date": r'[-*]*\s*\*\*(?:Birth|DOB|Born)[:\s]*\*\*[:\s]*([^\n]+)',
        "occupation": r'[-*]*\s*\*\*(?:Role|Occupation|Job)[:\s]*\*\*[:\s]*([^\n]+)',
        "affiliation": r'[-*]*\s*\*\*(?:Affiliation|Organization)[:\s]*\*\*[:\s]*([^\n]+)',
    }

    for field, pattern in patterns.items():
        # Don't overwrite frontmatter values
        if field in data and data[field]:
            continue
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            data[field] = match.group(1).strip()

    # Also check for age_book1 in frontmatter and map to age
    if "age_book1" in data and "age" not in data:
        data["age"] = str(data["age_book1"])

    return data


def normalize_name(name: str) -> str:
    """Normalize character name for matching."""
    # Remove titles and honorifics
    name = re.sub(r'^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Prof\.?)\s+', '', name, flags=re.IGNORECASE)
    return name.lower().strip()


@register_pass
class CodexValidationIndexPass(BasePass):
    """Validate manuscript index against codex reference material."""

    name = "codex-validation-index"
    description = "Compare extracted facts against codex ground truth"

    def run(
        self,
        manuscript: str = "",
        codex: Optional[str] = None,
        index: Optional[AccumulatedIndex] = None,
        **kwargs
    ) -> PassResult:
        """Run codex validation on accumulated index."""
        result = self._create_result()
        config = kwargs.get("config")

        if not index:
            result.error = "No index provided. Run 'edword index build' first."
            return result

        # Get codex directory from config
        codex_dir = None
        if config and config.project_root:
            codex_dir = config.project_root / config.paths.codex

        if not codex_dir or not codex_dir.exists():
            result.error = f"Codex directory not found: {codex_dir}"
            return result

        # Parse codex characters
        codex_chars = parse_codex_characters(codex_dir)

        if not codex_chars:
            result.error = "No character data found in codex"
            return result

        result.stats["codex_characters"] = len(codex_chars)
        result.stats["index_characters"] = len(index.characters)

        # Compare each indexed character against codex
        for char in index.characters:
            findings = self._validate_character(char, codex_chars)
            result.findings.extend(findings)

        result.stats["mismatches"] = len(result.findings)
        return result

    def _validate_character(self, char, codex_chars: dict) -> list[Finding]:
        """Validate a single character against codex."""
        findings = []

        # Try to find matching codex entry
        char_name = normalize_name(char.canonical_name)
        codex_entry = codex_chars.get(char_name)

        # Also try first name only - but prefer entries that have 'age' (actual characters)
        if not codex_entry:
            first_name = char_name.split()[0] if ' ' in char_name else char_name
            best_match = None
            for codex_name, entry in codex_chars.items():
                # Skip entries that are clearly not character profiles (no age, "entities", etc.)
                if "entities" in codex_name or "internal system" in codex_name:
                    continue
                if first_name in codex_name or codex_name in char_name:
                    # Prefer entries with age data (more likely to be the character)
                    if "age" in entry:
                        best_match = entry
                        break
                    elif not best_match:
                        best_match = entry
            codex_entry = best_match

        if not codex_entry:
            # Character not in codex - might be minor character, don't flag
            return findings

        # Fields to compare (factual, not meta)
        # Skip: status (means different things), role (narrative vs plot), etc.
        comparable_fields = {"age", "birth_date", "death_date", "occupation", "affiliation"}

        for fact in char.facts:
            pred = fact.predicate.lower()
            value = fact.value

            # Only compare specific factual fields
            if pred not in comparable_fields:
                continue

            # Check if codex has this field
            codex_value = codex_entry.get(pred)
            if not codex_value:
                continue

            # Compare values
            if not self._values_match(pred, value, str(codex_value)):
                findings.append(Finding(
                    severity=Severity.ERROR,
                    message=f"{char.canonical_name}'s {pred}: manuscript says '{value}' but codex says '{codex_value}'",
                    location=f"Codex: {codex_entry.get('name', 'unknown')}",
                    suggestion=f"Update manuscript or codex to match",
                ))

        return findings

    def _values_match(self, pred: str, manuscript_val: str, codex_val: str) -> bool:
        """Check if manuscript and codex values match (with fuzzy matching)."""
        m = manuscript_val.lower().strip()
        c = codex_val.lower().strip()

        # Exact match
        if m == c:
            return True

        # Number extraction for age
        if pred == "age":
            m_num = self._extract_age(m)
            c_num = self._extract_age(c)
            if m_num and c_num:
                return abs(m_num - c_num) <= 1
            # Handle age ranges like "preteen to early teen" for age 12
            if c_num and any(word in m for word in ["preteen", "early teen", "tween", "twelve"]):
                return 10 <= c_num <= 14

        # Substring match
        if m in c or c in m:
            return True

        return False

    def _extract_age(self, s: str) -> Optional[int]:
        """Extract age number from string, handling spelled-out numbers."""
        word_to_num = {
            "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
            "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45,
            "forties": 45, "early forties": 42, "mid-forties": 45,
        }
        s_lower = s.lower()
        for word, num in word_to_num.items():
            if word in s_lower:
                return num
        match = re.search(r'\d+', s)
        return int(match.group()) if match else None
