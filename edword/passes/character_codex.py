"""Character codex analysis pass - internal consistency of character files."""

import re
from typing import Optional, List

from .base import BasePass, Finding, PassResult, Severity
from . import register_pass
from ..llm.rlm import RLM


CHARACTER_CODEX_PROMPT = """Analyze this character codex for internal consistency issues.

You are reviewing the CHARACTER FILES ONLY (not the manuscript). Look for:

1. **Duplicate/Confusing Names**
   - Multiple characters with the same last name (could confuse readers)
   - Similar first names that might be confused
   - Flag these as warnings unless they're clearly family members

2. **Age/Timeline Math Errors**
   - Birth years that don't match stated ages
   - "X years ago" references that contradict other dates
   - Ages that don't make sense for the character's described experience

3. **Missing Critical Information**
   - Characters without ages or birth years
   - Missing relationship definitions
   - Incomplete backgrounds for major characters

4. **Internal Contradictions**
   - Facts that contradict within the same character file
   - Relationship descriptions that don't match between characters
   - Timeline events that conflict

5. **Relationship Inconsistencies**
   - Character A says they know Character B, but B's file doesn't mention A
   - Conflicting relationship descriptions (e.g., "close friends" vs "barely knows")

For each issue found, provide:
- The specific problem with quotes/references
- Which character file(s) are affected
- Severity: ERROR (breaks consistency) or WARNING (potential confusion)
- Suggested fix

Format your final answer as a numbered list:
1. [ERROR/WARNING] Brief description
   - Details with quotes
   - Affected: character_name.md
   - Fix: suggested resolution

Be thorough - check ALL character files for these issues."""


@register_pass
class CharacterCodexPass(BasePass):
    """Analyze character codex files for internal consistency."""

    name = "character_codex"
    description = "Codex internal consistency - names, ages, relationships"

    def run(
        self,
        manuscript: str,
        codex: Optional[str] = None,
        **kwargs
    ) -> PassResult:
        """
        Run character codex analysis.

        Note: This pass primarily uses the codex, not the manuscript.
        """
        result = self._create_result()
        config = kwargs.get("config")
        verbose = kwargs.get("verbose", False)

        if not codex:
            result.error = "No codex provided - this pass requires codex files"
            return result

        # Get LLM settings from config
        provider = "claude"
        model = "opus"
        recursive_provider = ""
        recursive_model = "sonnet"
        max_iterations = 25
        timeout = 300

        if config:
            provider = config.llm.provider
            model = config.llm.model
            recursive_provider = config.llm.recursive_provider
            recursive_model = config.llm.recursive_model
            max_iterations = config.llm.max_iterations
            timeout = config.llm.timeout

        # For this pass, we only need the codex (specifically character files)
        # But we'll pass the full codex and let the LLM focus on characters
        context = codex

        # Run RLM analysis
        rlm = RLM(
            provider=provider,
            model=model,
            recursive_provider=recursive_provider or provider,
            recursive_model=recursive_model,
            max_iterations=max_iterations,
            timeout=timeout,
            verbose=verbose,
        )

        try:
            response = rlm.completion(CHARACTER_CODEX_PROMPT, context)
            result.stats = rlm.stats

            # Parse findings from response
            findings = self._parse_findings(response)
            result.findings = findings

        except Exception as e:
            result.error = str(e)

        return result

    def _parse_findings(self, response: str) -> List[Finding]:
        """Parse findings from RLM response."""
        findings = []

        # Split response into lines and look for numbered items
        lines = response.split('\n')
        current_finding = None

        for line in lines:
            # Check for new numbered item - handles multiple formats:
            # "1. [ERROR] message" or "### 1. [ERROR]" or "**1. [WARNING] message**"
            match = re.match(r'^(?:#*\s*)?\*?\*?(?:\d+)\.\s*\[?(ERROR|WARNING|INFO)\]?\s*(.+)', line, re.IGNORECASE)
            if match:
                # Save previous finding if exists
                if current_finding:
                    findings.append(current_finding)

                severity_str = match.group(1).upper()
                message = match.group(2).strip()

                severity = Severity.WARNING
                if severity_str == "ERROR":
                    severity = Severity.ERROR
                elif severity_str == "INFO":
                    severity = Severity.INFO

                current_finding = Finding(
                    severity=severity,
                    message=message,
                )

            elif current_finding and line.strip():
                # Look for location info (Affected:)
                if line.strip().lower().startswith('affected:') or 'file' in line.lower():
                    loc = re.sub(r'^-?\s*(affected|file)s?:\s*', '', line.strip(), flags=re.IGNORECASE)
                    current_finding.location = loc
                # Look for suggestion/fix
                elif line.strip().lower().startswith(('fix:', '- fix:', 'suggestion:')):
                    suggestion = re.sub(r'^-?\s*(fix|suggestion):\s*', '', line.strip(), flags=re.IGNORECASE)
                    current_finding.suggestion = suggestion

        # Don't forget the last finding
        if current_finding:
            findings.append(current_finding)

        return findings
