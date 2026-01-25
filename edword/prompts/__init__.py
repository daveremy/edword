"""Prompt templating system for edword.

Loads prompt templates from files and renders them with variables.
Templates use Python string formatting: {variable_name}

Usage:
    from edword.prompts import load_prompt, render_prompt

    # Load and render in one step
    prompt = render_prompt("extract_chapter", chapter_text=text, entity_list=entities)

    # Or load template separately
    template = load_prompt("extract_chapter")
    prompt = template.format(chapter_text=text, entity_list=entities)
"""

from pathlib import Path
from typing import Optional
import re

# Directory containing prompt templates
PROMPTS_DIR = Path(__file__).parent


class PromptNotFoundError(Exception):
    """Prompt template file not found."""
    pass


class PromptRenderError(Exception):
    """Error rendering prompt template."""
    pass


def load_prompt(name: str) -> str:
    """Load a prompt template by name.

    Args:
        name: Template name (without extension). Looks for {name}.md or {name}.txt

    Returns:
        Template content as string

    Raises:
        PromptNotFoundError: If template file not found
        ValueError: If name contains path traversal characters
    """
    # Prevent path traversal attacks
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid prompt name '{name}': path traversal not allowed")

    # Try .md first, then .txt
    prompts_resolved = PROMPTS_DIR.resolve()
    for ext in [".md", ".txt"]:
        path = PROMPTS_DIR / f"{name}{ext}"
        # Additional safety: verify resolved path is within PROMPTS_DIR
        try:
            resolved = path.resolve()
            # Use relative_to() for proper containment check (raises ValueError if not contained)
            resolved.relative_to(prompts_resolved)
        except (OSError, ValueError):
            continue
        if path.is_file():
            return path.read_text(encoding='utf-8')

    raise PromptNotFoundError(
        f"Prompt template '{name}' not found. "
        f"Looked for: {name}.md, {name}.txt in {PROMPTS_DIR}"
    )


def render_prompt(name: str, **kwargs) -> str:
    """Load and render a prompt template with variables.

    Args:
        name: Template name (without extension)
        **kwargs: Variables to substitute in the template

    Returns:
        Rendered prompt string

    Raises:
        PromptNotFoundError: If template not found
        PromptRenderError: If required variable is missing

    Note:
        Templates use Python str.format() syntax:
        - {variable} is a placeholder
        - {{ and }} are escaped braces (literal { and })
        - Use {{ }} in JSON examples to avoid them being treated as placeholders
    """
    template = load_prompt(name)

    # Find all {variable} and {variable:format} placeholders in template
    # This regex matches format fields like {name}, {x:,}, {y:.2f}
    # First remove escaped braces ({{ and }}) before finding placeholders
    cleaned = template.replace('{{', '').replace('}}', '')
    # Match {word} or {word:format_spec} - extract just the variable name
    placeholders = set(re.findall(r'\{(\w+)(?::[^}]*)?\}', cleaned))

    # Check for missing variables
    missing = placeholders - set(kwargs.keys())
    if missing:
        raise PromptRenderError(
            f"Missing variables for template '{name}': {missing}"
        )

    # Render template
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError, IndexError) as e:
        raise PromptRenderError(f"Error rendering template '{name}': {e}")


def list_prompts() -> list[str]:
    """List all available prompt templates.

    Returns:
        List of template names (without extensions)
    """
    prompts = []
    for path in PROMPTS_DIR.glob("*.md"):
        prompts.append(path.stem)
    for path in PROMPTS_DIR.glob("*.txt"):
        if path.stem not in prompts:
            prompts.append(path.stem)
    return sorted(prompts)


def get_prompt_path(name: str) -> Optional[Path]:
    """Get the file path for a prompt template.

    Args:
        name: Template name

    Returns:
        Path to template file, or None if not found

    Raises:
        ValueError: If name contains path traversal characters
    """
    # Prevent path traversal attacks (same checks as load_prompt)
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid prompt name '{name}': path traversal not allowed")

    prompts_resolved = PROMPTS_DIR.resolve()
    for ext in [".md", ".txt"]:
        path = PROMPTS_DIR / f"{name}{ext}"
        # Verify resolved path is within PROMPTS_DIR
        try:
            resolved = path.resolve()
            resolved.relative_to(prompts_resolved)
        except (OSError, ValueError):
            continue
        if path.is_file():
            return path
    return None
