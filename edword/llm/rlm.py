"""
Recursive Language Model implementation using CLI tools.

Uses the REPL pattern: LLM writes Python code to explore large documents,
system executes code and returns output, LLM continues until FINAL().

Key feature: recursive_llm() function allows splitting large documents
into chunks and processing them recursively. Variables persist between
iterations within the same REPL session.
"""

import re
import io
import sys
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

from .providers import call_model, ProviderError


class RLMError(Exception):
    """Base error for RLM."""
    pass


class MaxIterationsError(RLMError):
    """Max iterations exceeded."""
    pass


class MaxDepthError(RLMError):
    """Max recursion depth exceeded."""
    pass


@dataclass
class RLMStats:
    """Statistics from an RLM run."""
    calls: int = 0
    iterations: int = 0
    recursive_calls: int = 0


def build_system_prompt(context_size: int, depth: int = 0) -> str:
    """Build the RLM system prompt."""
    return f"""You are executing Python code to analyze a document. I will run your code and show you the output.

CRITICAL: You MUST respond with a Python code block. Your code will be executed and the output shown to you.

The variable `context` contains the document ({context_size:,} characters). Write code to explore it.

EXAMPLE RESPONSE FORMAT:
```python
print(context[:500])  # See first 500 chars
```

AVAILABLE (already imported, do NOT use import statements):
- context: str - the document to analyze
- re: regex module (use re.findall, re.search directly)
- print, len, str, int, list, dict, range, enumerate, zip, sorted, min, max, sum

When you have your final answer, write: FINAL("your answer here")

DO NOT use import statements. DO NOT ask questions. Just write Python code in a ```python block."""


def extract_code(response: str) -> Optional[str]:
    """Extract Python code from LLM response."""
    # Normalize line endings
    response = response.replace('\r\n', '\n')

    # Look for ```python or ```py code blocks (case insensitive)
    pattern = r'```(?:python|py|Python|PY)\s*\n(.*?)```'
    matches = re.findall(pattern, response, re.DOTALL)
    if matches:
        return matches[-1].strip()

    # Look for ``` code blocks (no language specified)
    pattern = r'```\s*\n(.*?)```'
    matches = re.findall(pattern, response, re.DOTALL)
    if matches:
        code = matches[-1].strip()
        # Basic heuristic: looks like Python?
        if any(kw in code for kw in ['print(', 're.', 'context', '=', 'for ', 'if ']):
            return code

    return None


def extract_final(response: str) -> Optional[str]:
    """Extract FINAL() answer from response."""
    # Non-greedy patterns that require closing parenthesis
    patterns = [
        r'FINAL\s*\(\s*"""(.*?)"""\s*\)',      # FINAL("""...""")
        r"FINAL\s*\(\s*'''(.*?)'''\s*\)",      # FINAL('''...''')
        r'FINAL\s*\(\s*"([^"]*)"\s*\)',        # FINAL("...")
        r"FINAL\s*\(\s*'([^']*)'\s*\)",        # FINAL('...')
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


# Safe builtins that are always available in the REPL
SAFE_BUILTINS = {
    're': re,
    'print': print,
    'len': len,
    'str': str,
    'int': int,
    'float': float,
    'list': list,
    'dict': dict,
    'set': set,
    'tuple': tuple,
    'range': range,
    'enumerate': enumerate,
    'zip': zip,
    'sorted': sorted,
    'reversed': reversed,
    'min': min,
    'max': max,
    'sum': sum,
    'any': any,
    'all': all,
    'abs': abs,
    'round': round,
    '__builtins__': {},  # Disable dangerous builtins
}


def execute_code(code: str, env: Dict[str, Any], timeout_seconds: int = 30) -> str:
    """
    Execute Python code in a restricted environment with timeout.

    Args:
        code: Python code to execute
        env: Environment dict with context, recursive_llm, etc.
              This dict is MUTATED to persist variables between calls.
        timeout_seconds: Maximum execution time (default 30s)

    Returns:
        Captured stdout output or error message
    """
    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Code execution timed out after {timeout_seconds}s")

    # Build execution environment - env is mutated to persist variables
    # Only add safe builtins if not already present
    for key, value in SAFE_BUILTINS.items():
        if key not in env:
            env[key] = value

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    # Set timeout (Unix only - on Windows this is a no-op)
    old_handler = None
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)

    try:
        exec(code, env)
        output = captured.getvalue()
    except TimeoutError as e:
        output = f"Error: {e}"
    except Exception as e:
        output = f"Error: {type(e).__name__}: {e}"
    finally:
        # Cancel timeout
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
            if old_handler:
                signal.signal(signal.SIGALRM, old_handler)
        sys.stdout = old_stdout

    # Truncate if too long
    max_output = 4000
    if len(output) > max_output:
        output = output[:max_output] + f"\n... (truncated, {len(output)} chars total)"

    return output.strip() if output.strip() else "(no output)"


class RLM:
    """
    Recursive Language Model using CLI tools.

    Analyzes large documents by storing them as a variable and letting
    the LLM explore via Python code execution. Supports recursive calls
    for processing document chunks.
    """

    def __init__(
        self,
        provider: str = "claude",
        model: str = "opus",
        recursive_provider: Optional[str] = None,
        recursive_model: Optional[str] = None,
        max_iterations: int = 25,
        max_depth: int = 3,
        timeout: int = 300,
        verbose: bool = False,
        _depth: int = 0,
        _parent_stats: Optional[RLMStats] = None,
    ):
        """
        Initialize RLM.

        Args:
            provider: LLM provider ("claude" or "gemini")
            model: Primary model for analysis
            recursive_provider: Provider for recursive calls (defaults to provider)
            recursive_model: Model for recursive calls (defaults to model)
            max_iterations: Maximum REPL iterations
            max_depth: Maximum recursion depth
            timeout: Timeout per LLM call in seconds
            verbose: Print debug output
            _depth: Internal - current recursion depth
            _parent_stats: Internal - parent stats for aggregation
        """
        self.provider = provider
        self.model = model
        self.recursive_provider = recursive_provider or provider
        self.recursive_model = recursive_model or model
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.timeout = timeout
        self.verbose = verbose
        self._depth = _depth
        self._stats = _parent_stats or RLMStats()

    def _make_recursive_fn(self) -> Callable[[str, str], str]:
        """Create the recursive_llm function for the REPL environment."""
        def recursive_llm(query: str, sub_context: str) -> str:
            """
            Process a sub-context with a query recursively.

            Args:
                query: The question to ask about the sub-context
                sub_context: A chunk of the document to analyze

            Returns:
                The answer from analyzing the sub-context
            """
            if self._depth >= self.max_depth:
                return f"[Max recursion depth {self.max_depth} reached - returning summary of {len(sub_context)} chars]"

            if len(sub_context) < 50:
                return "[Sub-context too small to analyze]"

            self._stats.recursive_calls += 1

            if self.verbose:
                print(f"  [Recursive call depth={self._depth + 1}, context={len(sub_context)} chars]", file=sys.stderr)

            # Create child RLM with increased depth
            # Use recursive_provider for all recursive calls
            child_rlm = RLM(
                provider=self.recursive_provider,
                model=self.recursive_model,
                recursive_provider=self.recursive_provider,
                recursive_model=self.recursive_model,
                max_iterations=min(10, self.max_iterations),  # Fewer iterations for sub-tasks
                max_depth=self.max_depth,
                timeout=self.timeout,
                verbose=self.verbose,
                _depth=self._depth + 1,
                _parent_stats=self._stats,
            )

            try:
                return child_rlm.completion(query, sub_context)
            except Exception as e:
                return f"[Error in recursive call: {e}]"

        return recursive_llm

    def completion(self, query: str, context: str) -> str:
        """
        Process a query against the context document.

        Args:
            query: The question/task to perform
            context: The document to analyze

        Returns:
            The final answer

        Raises:
            MaxIterationsError: If max iterations exceeded
            MaxDepthError: If max recursion depth exceeded
            RLMError: On other errors
        """
        if self._depth == 0:
            self._stats = RLMStats()

        system_prompt = build_system_prompt(len(context), self._depth)

        # Build initial prompt - document is NOT included
        full_prompt = f"""{system_prompt}

QUERY: {query}

Write Python code to explore the `context` variable and find the answer. Use FINAL("answer") when done."""

        # Build REPL environment
        env = {
            'context': context,
            'recursive_llm': self._make_recursive_fn(),
        }

        conversation: list[str] = []

        for iteration in range(self.max_iterations):
            self._stats.iterations += 1

            if self.verbose:
                depth_prefix = "  " * self._depth
                print(f"{depth_prefix}--- Iteration {iteration + 1} (depth={self._depth}) ---", file=sys.stderr)

            # Build prompt with conversation history
            if conversation:
                prompt = full_prompt + "\n\n" + "\n\n".join(conversation) + "\n\nContinue:"
            else:
                prompt = full_prompt

            # Call LLM
            # Always use the instance's configured provider/model
            # (Child RLMs are initialized with recursive_provider/model in __init__)
            self._stats.calls += 1
            try:
                # Disable caching for RLM - conversation changes each iteration
                response = call_model(
                    self.provider,
                    prompt,
                    model=self.model,
                    timeout=self.timeout,
                    use_cache=False
                )
            except ProviderError as e:
                raise RLMError(f"LLM call failed: {e}")

            if self.verbose:
                print(f"Response preview: {response[:200]}...", file=sys.stderr)

            # Check for FINAL answer
            final_answer = extract_final(response)
            if final_answer:
                return final_answer

            # Extract and execute code
            code = extract_code(response)
            if code:
                if self.verbose:
                    print(f"Executing:\n{code[:500]}...", file=sys.stderr)

                output = execute_code(code, env)

                if self.verbose:
                    print(f"Output: {output[:500]}...", file=sys.stderr)

                conversation.append(
                    f"Your code:\n```python\n{code}\n```\n\nOutput:\n{output}"
                )
            else:
                # No code found, prompt to continue
                conversation.append(
                    f"Your response: {response}\n\n"
                    "Please write Python code to explore the document, "
                    "or use FINAL() if you have the answer."
                )

        raise MaxIterationsError(
            f"Max iterations ({self.max_iterations}) exceeded without FINAL()"
        )

    @property
    def stats(self) -> Dict[str, int]:
        """Get statistics from the last run."""
        return {
            'calls': self._stats.calls,
            'iterations': self._stats.iterations,
            'recursive_calls': self._stats.recursive_calls,
        }
