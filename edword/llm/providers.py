"""CLI-based LLM providers using claude and gemini CLI tools.

Uses stdin for prompts to avoid ARG_MAX shell limits (~262KB).
"""

import subprocess
import shutil
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Optional

# Cache directory for LLM responses
CACHE_DIR = Path.home() / ".edword" / "cache"

# Threshold for using temp file instead of stdin (some CLIs have issues with large stdin)
LARGE_PROMPT_THRESHOLD = 100_000  # 100KB


class ProviderError(Exception):
    """Error calling LLM provider."""
    pass


def _cache_key(provider: str, model: str, prompt: str, context_hash: Optional[str] = None) -> str:
    """Generate cache key from provider, model, prompt, and optional context hash.

    For RLM calls, pass context_hash to ensure different documents don't share cache.
    """
    content = f"{provider}:{model}:{prompt}"
    if context_hash:
        content = f"{content}:{context_hash}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_cached(key: str) -> Optional[str]:
    """Get cached response if it exists."""
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            return data.get("response")
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def _set_cached(key: str, response: str, provider: str, model: str) -> None:
    """Cache a response."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    data = {
        "provider": provider,
        "model": model,
        "response": response,
    }
    cache_file.write_text(json.dumps(data, indent=2))


def clear_cache() -> int:
    """Clear all cached responses. Returns number of files deleted."""
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count


def call_claude(
    prompt: str,
    model: str = "opus",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
    use_cache: bool = True
) -> str:
    """
    Call Claude via the claude CLI tool.

    Uses stdin to pass prompt, avoiding ARG_MAX limits.

    Args:
        prompt: The prompt to send
        model: Model alias - "opus", "sonnet", or full name
        system_prompt: Optional system prompt (prepended to prompt)
        timeout: Timeout in seconds
        use_cache: Whether to use cached responses

    Returns:
        Model response text

    Raises:
        ProviderError: If CLI not found or call fails
    """
    # Build full prompt with system prompt if provided
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

    # Check cache
    if use_cache:
        cache_key = _cache_key("claude", model, full_prompt)
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

    if not shutil.which("claude"):
        raise ProviderError(
            "claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
        )

    try:
        # Use stdin to pass prompt (avoids ARG_MAX limit)
        # claude -p - reads from stdin
        result = subprocess.run(
            ["claude", "-p", "-", "--model", model, "--output-format", "text"],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            raise ProviderError(f"Claude CLI error: {result.stderr}")

        response = result.stdout.strip()

        # Cache the response
        if use_cache:
            _set_cached(cache_key, response, "claude", model)

        return response

    except subprocess.TimeoutExpired:
        raise ProviderError(f"Claude CLI timed out after {timeout}s")


def call_gemini(
    prompt: str,
    model: str = "default",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
    use_cache: bool = True
) -> str:
    """
    Call Gemini via the gemini CLI tool.

    Uses temp file for large prompts to avoid ARG_MAX limits.

    Args:
        prompt: The prompt to send
        model: Model name - "flash", "pro", or full model ID
        system_prompt: Optional system prompt (prepended to prompt)
        timeout: Timeout in seconds
        use_cache: Whether to use cached responses

    Returns:
        Model response text

    Raises:
        ProviderError: If CLI not found or call fails
    """
    # Build full prompt with system prompt if provided
    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

    # Check cache
    if use_cache:
        cache_key = _cache_key("gemini", model, full_prompt)
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

    if not shutil.which("gemini"):
        raise ProviderError("gemini CLI not found")

    # Build base command with model if specified
    base_cmd = ["gemini", "-y"]
    if model and model != "default":
        base_cmd.extend(["-m", model])

    try:
        # For large prompts, use a temp file to avoid ARG_MAX
        # Gemini CLI doesn't support stdin well, so we use -p with file or short prompts
        if len(full_prompt) > LARGE_PROMPT_THRESHOLD:
            # Write to temp file and use @file syntax if supported, or fall back
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(full_prompt)
                temp_path = f.name

            try:
                # Try using the prompt file - gemini may support @file syntax
                # If not, this will still work but with truncation risk
                result = subprocess.run(
                    base_cmd + ["-p", f"@{temp_path}"],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            finally:
                Path(temp_path).unlink(missing_ok=True)
        else:
            result = subprocess.run(
                base_cmd + ["-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        if result.returncode != 0:
            raise ProviderError(f"Gemini CLI error: {result.stderr}")

        # Filter out warning/loading lines from gemini output
        lines = result.stdout.strip().split('\n')
        content_lines = [
            line for line in lines
            if not line.startswith('Warning:')
            and not line.startswith('[ERROR]')
            and not line.startswith('Loading extension')
            and not line.startswith('Loaded cached')
            and not line.startswith('Server ')
            and not line.startswith('YOLO mode')
        ]
        response = '\n'.join(content_lines).strip()

        # Cache the response
        if use_cache:
            _set_cached(cache_key, response, "gemini", model)

        return response

    except subprocess.TimeoutExpired:
        raise ProviderError(f"Gemini CLI timed out after {timeout}s")


def call_model(
    provider: str,
    prompt: str,
    model: str = "opus",
    system_prompt: Optional[str] = None,
    timeout: int = 300,
    use_cache: bool = True
) -> str:
    """
    Call LLM via CLI tool based on provider.

    Args:
        provider: "claude" or "gemini"
        prompt: The prompt to send
        model: Model name (used for claude only)
        system_prompt: Optional system prompt
        timeout: Timeout in seconds
        use_cache: Whether to use cached responses

    Returns:
        Model response text
    """
    if provider == "claude":
        return call_claude(prompt, model=model, system_prompt=system_prompt, timeout=timeout, use_cache=use_cache)
    elif provider == "gemini":
        return call_gemini(prompt, model=model, system_prompt=system_prompt, timeout=timeout, use_cache=use_cache)
    else:
        raise ProviderError(f"Unknown provider: {provider}")
