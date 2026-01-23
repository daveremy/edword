"""Continuity analysis pass - timeline and event consistency."""

import re
from typing import Optional, List

from .base import BasePass, Finding, PassResult, Severity
from . import register_pass
from ..llm.rlm import RLM


CONTINUITY_PROMPT = """Analyze this manuscript for continuity and timeline issues.

Look for:
1. **Age inconsistencies** - Character ages that don't match their birth dates or stated ages elsewhere
2. **Timeline contradictions** - Events that contradict each other or happen in impossible sequences
3. **Date/time errors** - "X months ago" references that don't add up, wrong years, etc.
4. **Character fact changes** - Names, relationships, backgrounds that change unexpectedly
5. **Setting inconsistencies** - Locations, distances, or physical descriptions that change

For each issue found, provide:
- The specific contradiction with quotes from both locations
- Chapter/section where each mention occurs
- Severity: ERROR (breaks story logic) or WARNING (minor inconsistency)
- Suggested fix

Format your final answer as a numbered list of issues, like:
1. [ERROR] Greg's age: Chapter 8 says DOB 1988 (age 36-37), but Chapter 4 says "forty-two years old"
   - Fix: Update DOB to 1983 or change age references
2. [WARNING] Kate's career: Chapter 8 mentions "eight years army intelligence" but codex says 4 years
   - Fix: Change to "four years army intelligence"

If the codex is provided, cross-reference character facts against it.

Be thorough - search the entire document for ALL temporal markers, ages, dates, and character facts."""


@register_pass
class ContinuityPass(BasePass):
    """Analyze manuscript for timeline and continuity issues."""

    name = "continuity"
    description = "Timeline and event consistency analysis"

    def run(
        self,
        manuscript: str,
        codex: Optional[str] = None,
        **kwargs
    ) -> PassResult:
        """
        Run continuity analysis on manuscript.

        Uses RLM to recursively explore the document and find issues.
        """
        result = self._create_result()
        config = kwargs.get("config")
        verbose = kwargs.get("verbose", False)

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

        # Build context - manuscript plus codex if available
        context = manuscript
        if codex:
            context = f"{manuscript}\n\n=== CODEX (Reference Material) ===\n\n{codex}"

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
            response = rlm.completion(CONTINUITY_PROMPT, context)
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
        current_lines = []

        for line in lines:
            # Check for new numbered item
            match = re.match(r'^\d+\.\s*\[?(ERROR|WARNING|INFO)\]?\s*(.+)', line, re.IGNORECASE)
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
                current_lines = [line]

            elif current_finding and line.strip():
                current_lines.append(line)
                # Look for location info
                if "chapter" in line.lower():
                    current_finding.location = line.strip().lstrip('- ')
                # Look for suggestion/fix
                elif line.strip().lower().startswith(('fix:', '- fix:', 'suggestion:')):
                    suggestion = re.sub(r'^-?\s*(fix|suggestion):\s*', '', line.strip(), flags=re.IGNORECASE)
                    current_finding.suggestion = suggestion

        # Don't forget the last finding
        if current_finding:
            findings.append(current_finding)

        return findings
