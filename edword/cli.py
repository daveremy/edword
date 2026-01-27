"""Edword CLI - AI-powered editorial analysis tool."""

import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import load_config, EdwordConfig
from .discovery import discover_project, get_book_by_name, ProjectStructure
from .loaders import compile_manuscript, load_codex
from .common import IndexVersionMismatch

app = typer.Typer(
    name="edword",
    help="AI-powered editorial analysis for book manuscripts.",
    no_args_is_help=True,
)
console = Console()

# Index subcommand group
index_app = typer.Typer(help="Build and manage chapter indices.")
app.add_typer(index_app, name="index")

# Query subcommand group
query_app = typer.Typer(help="Query the manuscript index.")
app.add_typer(query_app, name="query")

# MCP subcommand group
mcp_app = typer.Typer(help="MCP server for AI assistant integration.")
app.add_typer(mcp_app, name="mcp")


def get_config_and_project(
    config_path: Optional[Path] = None
) -> tuple[EdwordConfig, ProjectStructure]:
    """Load config and discover project structure."""
    config = load_config(config_path)
    project = discover_project(
        root=config.project_root or Path.cwd(),
        manuscripts_path=config.paths.manuscripts,
        codex_path=config.paths.codex,
    )
    return config, project


@app.command()
def info(
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
):
    """Show project information and structure."""
    config, project = get_config_and_project(config_path)

    if json_output:
        _output_json({
            "project": {
                "name": config.project_name,
                "root": str(project.root),
            },
            "config": {
                "path": str(config.config_path) if config.config_path else None,
                "found": config.config_path is not None,
            },
            "manuscripts": {
                "directory": str(project.manuscripts_dir) if project.manuscripts_dir else None,
                "found": project.has_manuscripts,
                "books": [
                    {"id": b.name, "chapters": b.chapter_count}
                    for b in project.books
                ],
                "total_chapters": sum(b.chapter_count for b in project.books),
            },
            "codex": {
                "directory": str(project.codex_dir) if project.codex_dir else None,
                "found": project.has_codex,
                "files": len(project.codex_files) if project.codex_files else 0,
            },
            "llm": {
                "provider": config.llm.provider,
                "model": config.llm.model,
                "recursive_model": config.llm.recursive_model,
            },
        })
        return

    # Header
    console.print(Panel(
        f"[bold]{config.project_name}[/bold]",
        title="Edword Project",
        border_style="blue",
    ))

    # Paths
    console.print("\n[bold]Paths:[/bold]")
    console.print(f"  Root: {project.root}")
    if config.config_path:
        console.print(f"  Config: {config.config_path}")
    else:
        console.print("  Config: [dim]not found (using defaults)[/dim]")

    # Manuscripts
    console.print("\n[bold]Manuscripts:[/bold]")
    if project.has_manuscripts:
        console.print(f"  Directory: {project.manuscripts_dir}")
        for book in project.books:
            console.print(f"  - {book.name}: {book.chapter_count} chapters")
    else:
        console.print("  [dim]No manuscripts directory found[/dim]")

    # Codex
    console.print("\n[bold]Codex:[/bold]")
    if project.has_codex:
        console.print(f"  Directory: {project.codex_dir}")
        console.print(f"  Files: {len(project.codex_files)}")
    else:
        console.print("  [dim]No codex directory found[/dim]")

    # LLM config
    console.print("\n[bold]LLM:[/bold]")
    console.print(f"  Provider: {config.llm.provider}")
    console.print(f"  Model: {config.llm.model}")
    console.print(f"  Recursive model: {config.llm.recursive_model}")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
):
    """Initialize edword configuration in current directory."""
    config_path = Path.cwd() / "edword.yaml"

    if config_path.exists() and not force:
        console.print("[red]Error:[/red] edword.yaml already exists. Use --force to overwrite.")
        raise typer.Exit(1)

    # Try to detect project structure
    project = discover_project(Path.cwd())

    config_content = f'''# Edword Configuration
project:
  name: "{project.root.name}"

paths:
  manuscripts: "manuscripts/"
  codex: "codex/"
  reports: ".edword/reports/"

llm:
  provider: "claude"
  model: "opus"
  recursive_model: "sonnet"
  max_iterations: 25

passes:
  continuity:
    enabled: true
  codex_validation:
    enabled: true
  character_voice:
    enabled: true
  prose_quality:
    enabled: true
    filter_words: ["felt", "saw", "heard", "watched", "noticed", "realized", "seemed"]
'''

    config_path.write_text(config_content)
    console.print(f"[green]Created:[/green] {config_path}")

    # Show detected structure
    if project.has_manuscripts:
        console.print(f"[dim]Detected {len(project.books)} book(s) in manuscripts/[/dim]")
    if project.has_codex:
        console.print(f"[dim]Detected {len(project.codex_files)} codex files[/dim]")


@app.command()
def passes():
    """List available analysis passes."""
    table = Table(title="Available Passes")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Status", justify="center")

    # TODO: Load actual passes dynamically
    available_passes = [
        ("continuity", "Timeline and event consistency", True),
        ("codex_validation", "Manuscript matches codex facts", True),
        ("character_voice", "Voice consistency and POV checks", False),
        ("prose_quality", "Filter words, repetition, style", False),
        ("pacing", "Scene length and tension curves", False),
        ("structure", "Story structure and beat analysis", False),
        ("foreshadowing", "Setup and payoff tracking", False),
    ]

    for name, desc, implemented in available_passes:
        status = "[green]Ready[/green]" if implemented else "[dim]Coming soon[/dim]"
        table.add_row(name, desc, status)

    console.print(table)


def _serialize_finding(finding) -> dict:
    """Convert Finding dataclass to JSON-safe dict."""
    return {
        "severity": finding.severity.value,  # Enum -> string
        "message": finding.message,
        "location": finding.location,
        "context": finding.context,
        "suggestion": finding.suggestion,
        "verification": finding.verification,  # CoVe result if verified
    }


def _serialize_pass_result(result) -> dict:
    """Convert PassResult dataclass to JSON-safe dict."""
    return {
        "pass_name": result.pass_name,
        "error": result.error,
        "findings": [_serialize_finding(f) for f in (result.findings or [])],
        "stats": result.stats,
        "summary": {
            "errors": len(result.errors or []),
            "warnings": len(result.warnings or []),
            "info": len(result.infos or []),
        },
    }


def _output_json(data: dict) -> None:
    """Output dict as formatted JSON to stdout."""
    import json
    print(json.dumps(data, indent=2, default=str))


def _make_chapter_result(
    chapter_id: str,
    success: bool,
    status: str,
    time_ms: float = 0,
    llm_calls: int = 0,
    retries: int = 0,
    error: str = None,
) -> dict:
    """Build a chapter result dict for JSON output."""
    result = {
        "id": chapter_id,
        "success": success,
        "status": status,
        "time_ms": time_ms,
        "llm_calls": llm_calls,
        "error": error,
    }
    if retries > 0:
        result["retries"] = retries
    return result


def _extraction_result_to_json(chapter_id: str, result) -> dict:
    """Convert an extraction result to a chapter result dict."""
    timing = result.timing
    return _make_chapter_result(
        chapter_id=chapter_id,
        success=result.success,
        status="extracted" if result.success else "failed",
        time_ms=timing.total_ms if timing else 0,
        llm_calls=timing.llm_call_count if timing else 0,
        retries=result.retries_used,
        error=result.error,
    )


def _chapter_sort_key(item: dict) -> int:
    """Extract chapter number for sorting (e.g., 'chapter-01-foo' -> 1)."""
    import re
    match = re.search(r'\d+', item["id"])
    return int(match.group()) if match else 0


def _serialize_contradiction(c) -> dict:
    """Convert a Contradiction to a JSON-safe dict."""
    return {
        "entity_type": c.entity_type,
        "entity_id": c.entity_id,
        "predicate": c.predicate,
        "chapter1": c.chapter1,
        "value1": c.value1,
        "chapter2": c.chapter2,
        "value2": c.value2,
        "message": c.message,
    }


def _error_json(message: str, json_output: bool) -> None:
    """Output error message, as JSON if requested."""
    if json_output:
        _output_json({"status": "error", "message": message})
    else:
        console.print(f"[red]Error:[/red] {message}")


def handle_version_mismatch(
    e: IndexVersionMismatch,
    config: EdwordConfig,
    book_name: str,
    json_output: bool = False
) -> None:
    """Handle version mismatch with positive messaging. Rebuilds if approved, then exits."""
    if json_output:
        _output_json({
            "status": "upgrade_available",
            "message": "Edword has been upgraded with improved analysis capabilities.",
            "action": f"edword index build --book {e.book_id}",
            "book": e.book_id,
            "index_version": e.index_version,
            "current_version": e.current_version,
        })
        raise typer.Exit(1)

    # Get chapter count for time estimate
    from .discovery import discover_project, get_book_by_name
    project = discover_project(config.project_root)
    selected_book = get_book_by_name(project, book_name)
    chapter_count = selected_book.chapter_count if selected_book else 0

    console.print(Panel(
        f"[cyan]Edword has been upgraded[/cyan] with improved analysis.\n\n"
        f"Rebuild index for [bold]{e.book_id}[/bold] to use new features?\n\n"
        f"[dim]This will re-analyze {chapter_count} chapter(s) using your LLM provider.\n"
        f"Depending on your provider and chapter length, this may take a while.[/dim]",
        title="Index Upgrade Available",
        border_style="cyan",
    ))

    if typer.confirm("Rebuild now?", default=True):
        # Import and run index build
        from .index import IndexStorage, Accumulator, ExtractionConfig, extract_chapter

        if not selected_book:
            console.print(f"[red]Error:[/red] Book '{book_name}' not found")
            raise typer.Exit(1)

        storage = IndexStorage(config.project_root)
        accumulator = Accumulator(selected_book.name)

        extraction_config = ExtractionConfig(
            provider=config.llm.provider,
            model=config.llm.model,
            max_retries=3,
            verbose=False,
        )

        console.print(f"\n[cyan]Rebuilding index for {selected_book.name}...[/cyan]")

        # Use progress bar for rebuild
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=False,
        ) as progress:
            errors = []
            for i, chapter_path in enumerate(selected_book.chapters):
                chapter_id = chapter_path.stem
                task = progress.add_task(
                    f"[cyan]Extracting {chapter_id}[/cyan] ({i+1}/{chapter_count})",
                    total=None
                )

                entity_list = accumulator.get_entity_list()
                result = extract_chapter(
                    chapter_path=chapter_path,
                    book_id=selected_book.name,
                    chapter_id=chapter_id,
                    entity_list=entity_list if entity_list.characters else None,
                    config=extraction_config,
                )

                progress.remove_task(task)

                if result.success:
                    storage.save_chapter_index(result.index)
                    accumulator.add_chapter(result.index)
                    time_info = f" [dim]({result.timing.total_ms/1000:.1f}s)[/dim]" if result.timing else ""
                    console.print(f"  [green]✓[/green] {chapter_id}{time_info}")
                else:
                    errors.append((chapter_id, result.error))
                    console.print(f"  [red]✗[/red] {chapter_id}: {result.error}")

        acc_result = accumulator.get_result()
        storage.save_accumulated_index(acc_result.index)

        if errors:
            console.print(f"\n[yellow]Index rebuilt with {len(errors)} error(s). Please run your command again.[/yellow]")
        else:
            console.print("\n[green]Index rebuilt successfully. Please run your command again.[/green]")

    raise typer.Exit(0)


@app.command()
def analyze(
    pass_names: Optional[List[str]] = typer.Argument(
        None, help="Specific passes to run (default: all enabled)"
    ),
    book: Optional[str] = typer.Option(
        None, "--book", "-b", help="Book to analyze (e.g., 'book1' or '1')"
    ),
    chapters: Optional[str] = typer.Option(
        None, "--chapters", "-ch", help="Chapter range (e.g., '1-8')"
    ),
    no_codex: bool = typer.Option(
        False, "--no-codex", help="Skip loading codex (faster for large codex)"
    ),
    use_index: bool = typer.Option(
        False, "--index", "-i", help="Use accumulated index for analysis (faster, requires 'edword index build' first)"
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Verify ERROR findings with CoVe (Chain-of-Verification)"
    ),
    verify_all: bool = typer.Option(
        False, "--verify-all", help="Verify ALL findings with CoVe, not just errors"
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip verification (fast mode)"
    ),
    verify_model: Optional[str] = typer.Option(
        None, "--verify-model", help="Model to use for verification (default: from config or sonnet)"
    ),
    save: bool = typer.Option(
        False, "--save", "-s", help="Save report to file"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose output"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Run editorial analysis passes on manuscript."""
    config, project = get_config_and_project(config_path)

    # Validate project structure
    if not project.has_manuscripts:
        _error_json("No manuscripts directory found", json_output)
        raise typer.Exit(1)

    if not project.books:
        _error_json("No books found in manuscripts directory", json_output)
        raise typer.Exit(1)

    # Select book
    if book:
        selected_book = get_book_by_name(project, book)
        if not selected_book:
            _error_json(f"Book '{book}' not found. Available: {', '.join(b.name for b in project.books)}", json_output)
            raise typer.Exit(1)
    else:
        selected_book = project.books[0]

    # Parse chapter range
    chapter_range = None
    if chapters:
        try:
            if "-" in chapters:
                start, end = chapters.split("-")
                chapter_range = (int(start), int(end))
            else:
                ch = int(chapters)
                chapter_range = (ch, ch)
        except ValueError:
            _error_json(f"Invalid chapter range: {chapters}", json_output)
            raise typer.Exit(1)

    # Show what we're analyzing (skip for JSON)
    if not json_output:
        console.print(Panel(
            f"[bold]{config.project_name}[/bold]\n"
            f"Book: {selected_book.name} ({selected_book.chapter_count} chapters)"
            + (f"\nChapters: {chapters}" if chapters else ""),
            title="Analyzing",
            border_style="blue",
        ))

    # Compile manuscript
    if not json_output:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Compiling manuscript...", total=None)
            manuscript = compile_manuscript(selected_book, chapter_range)
        console.print(f"[dim]Manuscript: {len(manuscript):,} characters[/dim]")
    else:
        manuscript = compile_manuscript(selected_book, chapter_range)

    # Load codex if available and not disabled
    codex = ""
    if project.has_codex and not no_codex:
        if not json_output:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Loading codex...", total=None)
                codex = load_codex(project.codex_dir)
            console.print(f"[dim]Codex: {len(codex):,} characters[/dim]")
        else:
            codex = load_codex(project.codex_dir)
    elif no_codex and not json_output:
        console.print(f"[dim]Codex: skipped (--no-codex)[/dim]")

    # Load accumulated index if requested
    accumulated_index = None
    if use_index:
        from .index.storage import IndexStorage
        from .index.schema import INDEX_SCHEMA_VERSION
        storage = IndexStorage(config.project_root, str(config.paths.index))
        accumulated_index = storage.load_accumulated_index(selected_book.name)
        if accumulated_index:
            # Check schema version
            index_version = getattr(accumulated_index, 'schema_version', 0)
            if index_version != INDEX_SCHEMA_VERSION:
                handle_version_mismatch(
                    IndexVersionMismatch(selected_book.name, index_version, INDEX_SCHEMA_VERSION),
                    config,
                    selected_book.name,
                    json_output
                )
            if not json_output:
                console.print(f"[dim]Index: {len(accumulated_index.characters)} characters, {len(accumulated_index.timeline)} events[/dim]")
        else:
            if not json_output:
                console.print(f"[yellow]Warning:[/yellow] No index found for {selected_book.name}. Run 'edword index build' first.")

    # Determine which passes to run
    if pass_names:
        passes_to_run = pass_names
    else:
        # Run all enabled passes
        passes_to_run = [
            name for name, pc in config.passes.items()
            if pc.enabled
        ]
        if not passes_to_run:
            passes_to_run = ["continuity"]  # Default

    if not json_output:
        console.print(f"\n[bold]Running passes:[/bold] {', '.join(passes_to_run)}")

    # Import and run passes
    from .passes import run_passes
    results = run_passes(
        passes_to_run,
        manuscript=manuscript,
        codex=codex,
        config=config,
        verbose=verbose,
        index=accumulated_index,
    )

    # Run CoVe verification if requested
    if (verify or verify_all) and not no_verify:
        from .passes.verifier import CoVeVerifier, VerificationVerdict
        from .passes.base import Severity

        # Resolve model from flag > config > default
        resolved_model = (
            verify_model
            or getattr(config.llm, 'recursive_model', None)
            or config.llm.model
            or "sonnet"
        )

        verifier = CoVeVerifier(
            provider=config.llm.provider,
            model=resolved_model,
        )

        if not json_output:
            console.print(f"\n[bold]Verifying findings with CoVe...[/bold] (model: {resolved_model})")

        verified_count = 0
        for result in results:
            if result.error:
                continue

            # Select which findings to verify
            if verify_all:
                findings_to_verify = result.findings
            else:
                findings_to_verify = result.errors  # Only ERROR severity

            for finding in findings_to_verify:
                # Show spinner for interactive mode
                if not json_output:
                    console.print(f"  [dim]Verifying: {finding.message[:50]}...[/dim]", end="\r")

                verification = verifier.verify(finding, selected_book)
                verified_count += 1

                # Attach verification to finding
                finding.verification = {
                    "verdict": verification.verdict.value,
                    "confidence": verification.confidence,
                    "explanation": verification.explanation,
                }

                if not json_output:
                    verdict_color = {
                        "confirmed": "red",
                        "dismissed": "green",
                        "uncertain": "yellow",
                    }.get(verification.verdict.value, "dim")
                    # Clear spinner line and print result
                    console.print(
                        f"  [{verdict_color}]{verification.verdict.value.upper()}[/{verdict_color}] "
                        f"({verification.confidence}) - {finding.message[:60]}   "
                    )

        if not json_output and verified_count > 0:
            console.print(f"[dim]Verified {verified_count} finding(s)[/dim]")

    # JSON output
    if json_output:
        successful_results = [r for r in results if not r.error]
        _output_json({
            "status": "success",
            "book": selected_book.name,
            "passes": [_serialize_pass_result(r) for r in results],
            "summary": {
                "total_errors": sum(len(r.errors or []) for r in successful_results),
                "total_warnings": sum(len(r.warnings or []) for r in successful_results),
                "total_info": sum(len(r.infos or []) for r in successful_results),
            },
        })
        return

    # Display results
    console.print("\n")
    display_results(results, console)

    # Save report if requested
    if save:
        from .reports.markdown import generate_report
        report_dir = config.project_root / config.paths.reports
        report_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"report_{timestamp}.md"

        report_content = generate_report(results, config, selected_book)
        report_path.write_text(report_content)
        console.print(f"\n[green]Report saved:[/green] {report_path}")


def display_results(results: list, console: Console):
    """Display analysis results in terminal."""
    from .passes.base import Severity

    total_errors = 0
    total_warnings = 0
    total_info = 0

    for result in results:
        if result.error:
            console.print(f"[red]{result.pass_name}:[/red] FAILED - {result.error}")
            continue

        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        total_info += len(result.infos)

        console.print(f"\n[bold cyan]{result.pass_name}[/bold cyan] {result.summary()}")

        for finding in result.findings:
            if finding.severity == Severity.ERROR:
                icon = "[red]x[/red]"
            elif finding.severity == Severity.WARNING:
                icon = "[yellow]![/yellow]"
            else:
                icon = "[dim]i[/dim]"

            console.print(f"  {icon} {finding.message}")
            if finding.location:
                console.print(f"    [dim]{finding.location}[/dim]")
            if finding.suggestion:
                console.print(f"    [green]-> {finding.suggestion}[/green]")

    # Summary
    console.print(Panel(
        f"[red]{total_errors}[/red] errors  "
        f"[yellow]{total_warnings}[/yellow] warnings  "
        f"[dim]{total_info}[/dim] info",
        title="Summary",
        border_style="blue" if total_errors == 0 else "red",
    ))


@app.command()
def report(
    action: str = typer.Argument("list", help="Action: list, view, delete"),
    report_id: Optional[str] = typer.Argument(None, help="Report ID or 'latest'"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Manage saved reports."""
    config, _ = get_config_and_project(config_path)
    report_dir = config.project_root / config.paths.reports

    if action == "list":
        if not report_dir.exists():
            console.print("[dim]No reports found[/dim]")
            return

        reports = sorted(report_dir.glob("report_*.md"), reverse=True)
        if not reports:
            console.print("[dim]No reports found[/dim]")
            return

        table = Table(title="Saved Reports")
        table.add_column("Date", style="cyan")
        table.add_column("File")
        table.add_column("Size")

        for r in reports[:10]:  # Show last 10
            # Parse timestamp from filename
            name = r.stem.replace("report_", "")
            try:
                from datetime import datetime
                dt = datetime.strptime(name, "%Y%m%d_%H%M%S")
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = name

            size = f"{r.stat().st_size / 1024:.1f}KB"
            table.add_row(date_str, r.name, size)

        console.print(table)

    elif action == "view":
        if not report_id:
            console.print("[red]Error:[/red] Specify report filename or 'latest'")
            raise typer.Exit(1)

        if report_id == "latest":
            reports = sorted(report_dir.glob("report_*.md"), reverse=True)
            if not reports:
                console.print("[red]Error:[/red] No reports found")
                raise typer.Exit(1)
            report_path = reports[0]
        else:
            report_path = report_dir / report_id
            if not report_path.exists():
                report_path = report_dir / f"report_{report_id}.md"

        if not report_path.exists():
            console.print(f"[red]Error:[/red] Report not found: {report_id}")
            raise typer.Exit(1)

        from rich.markdown import Markdown
        content = report_path.read_text()
        console.print(Markdown(content))

    elif action == "delete":
        # TODO: Implement delete
        console.print("[dim]Delete not yet implemented[/dim]")

    else:
        console.print(f"[red]Error:[/red] Unknown action: {action}")
        raise typer.Exit(1)


# --- Index Commands ---

@index_app.command("build")
def index_build(
    book: Optional[str] = typer.Option(
        None, "--book", "-b", help="Book to index (e.g., 'book1')"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Rebuild even if cached"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose output"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of parallel workers (1=sequential)"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Build chapter index for a book."""
    import time
    import concurrent.futures
    from .index import (
        IndexStorage, Accumulator, ExtractionConfig,
        extract_chapter, EntityList
    )

    build_start = time.perf_counter()
    config, project = get_config_and_project(config_path)

    if not project.has_manuscripts:
        _error_json("No manuscripts directory found", json_output)
        raise typer.Exit(1)

    if not project.books:
        _error_json("No books found", json_output)
        raise typer.Exit(1)

    # Select book
    if book:
        selected_book = get_book_by_name(project, book)
        if not selected_book:
            _error_json(f"Book '{book}' not found. Available: {', '.join(b.name for b in project.books)}", json_output)
            raise typer.Exit(1)
    else:
        selected_book = project.books[0]

    # Initialize storage and accumulator
    storage = IndexStorage(config.project_root)
    accumulator = Accumulator(selected_book.name)

    # Get extraction config from edword config
    extraction_config = ExtractionConfig(
        provider=config.llm.provider,
        model=config.llm.model,  # TODO: Use index-specific model when config supports it
        max_retries=3,
        verbose=verbose,
    )

    if not json_output:
        parallel_info = f" (parallel: {workers} workers)" if workers > 1 else ""
        console.print(Panel(
            f"[bold]{config.project_name}[/bold]\n"
            f"Book: {selected_book.name}\n"
            f"Chapters: {selected_book.chapter_count}{parallel_info}",
            title="Building Index",
            border_style="blue",
        ))

    # Process each chapter
    chapters_indexed = 0
    chapters_skipped = 0
    errors = []

    # JSON output: collect chapter results
    chapter_results_json = []

    # First pass: identify which chapters need extraction
    chapters_to_extract = []  # [(index, chapter_id, chapter_path), ...]
    chapters_to_load = []     # [(index, chapter_id), ...]

    for i, chapter_path in enumerate(selected_book.chapters):
        chapter_id = chapter_path.stem
        if not force and not storage.needs_reindex(selected_book.name, chapter_id, chapter_path):
            chapters_to_load.append((i, chapter_id))
        else:
            chapters_to_extract.append((i, chapter_id, chapter_path))

    if chapters_to_load and not json_output:
        console.print(f"[dim]Skipping {len(chapters_to_load)} cached chapters[/dim]")

    # Results storage: index -> ExtractionResult or loaded ChapterIndex
    results: dict = {}

    # Load cached chapters
    for i, chapter_id in chapters_to_load:
        existing = storage.load_chapter_index(selected_book.name, chapter_id)
        if existing:
            results[i] = ("loaded", existing)
            chapters_skipped += 1
            chapter_results_json.append(
                _make_chapter_result(chapter_id, success=True, status="cached")
            )

    if not chapters_to_extract:
        if not json_output:
            console.print("[dim]All chapters already indexed[/dim]")
    elif workers > 1 and len(chapters_to_extract) > 1:
        # Parallel extraction
        if not json_output:
            console.print(f"[cyan]Extracting {len(chapters_to_extract)} chapters with {workers} workers...[/cyan]")

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all extraction tasks
            futures = {}
            for i, chapter_id, chapter_path in chapters_to_extract:
                future = executor.submit(
                    extract_chapter,
                    chapter_path=chapter_path,
                    book_id=selected_book.name,
                    chapter_id=chapter_id,
                    entity_list=None,  # No entity list in parallel mode
                    config=extraction_config,
                )
                futures[future] = (i, chapter_id, chapter_path)

            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                i, chapter_id, chapter_path = futures[future]
                try:
                    result = future.result()
                    results[i] = ("extracted", result)
                    chapter_results_json.append(_extraction_result_to_json(chapter_id, result))

                    # Show progress (only for non-JSON)
                    if not json_output:
                        if result.success:
                            if result.timing:
                                t = result.timing
                                retries_info = f" [yellow]({result.retries_used} retries)[/yellow]" if result.retries_used > 0 else ""
                                console.print(
                                    f"  [green]✓[/green] {chapter_id}: "
                                    f"[dim]{t.total_ms/1000:.1f}s[/dim] "
                                    f"([cyan]{t.llm_calls_ms/1000:.1f}s[/cyan] LLM × {t.llm_call_count})"
                                    f"{retries_info}"
                                )
                        else:
                            if result.timing:
                                console.print(
                                    f"  [red]✗[/red] {chapter_id}: {result.error} "
                                    f"[dim]({result.timing.total_ms/1000:.1f}s)[/dim]"
                                )
                            else:
                                console.print(f"  [red]✗[/red] {chapter_id}: {result.error}")
                except Exception as e:
                    if not json_output:
                        console.print(f"  [red]✗[/red] {chapter_id}: Exception: {e}")
                    results[i] = ("error", str(e))
                    chapter_results_json.append(
                        _make_chapter_result(chapter_id, success=False, status="exception", error=str(e))
                    )
    else:
        # Sequential extraction (original behavior)
        if json_output:
            # No progress bar for JSON
            for i, chapter_id, chapter_path in chapters_to_extract:
                entity_list = accumulator.get_entity_list()
                result = extract_chapter(
                    chapter_path=chapter_path,
                    book_id=selected_book.name,
                    chapter_id=chapter_id,
                    entity_list=entity_list if entity_list.characters else None,
                    config=extraction_config,
                )
                results[i] = ("extracted", result)
                chapter_results_json.append(_extraction_result_to_json(chapter_id, result))
                # For sequential mode, accumulate immediately to build entity list
                if result.success:
                    storage.save_chapter_index(result.index)
                    accumulator.add_chapter(result.index)
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                for i, chapter_id, chapter_path in chapters_to_extract:
                    task = progress.add_task(
                        f"Indexing {chapter_id}... ({i+1}/{selected_book.chapter_count})",
                        total=None
                    )

                    # Get entity list from accumulated so far (sequential mode only)
                    entity_list = accumulator.get_entity_list()

                    result = extract_chapter(
                        chapter_path=chapter_path,
                        book_id=selected_book.name,
                        chapter_id=chapter_id,
                        entity_list=entity_list if entity_list.characters else None,
                        config=extraction_config,
                    )

                    progress.remove_task(task)
                    results[i] = ("extracted", result)

                    if result.success:
                        if result.timing:
                            t = result.timing
                            retries_info = f" [yellow]({result.retries_used} retries)[/yellow]" if result.retries_used > 0 else ""
                            console.print(
                                f"  [green]✓[/green] {chapter_id}: "
                                f"[dim]{t.total_ms/1000:.1f}s[/dim] "
                                f"([cyan]{t.llm_calls_ms/1000:.1f}s[/cyan] LLM × {t.llm_call_count})"
                                f"{retries_info}"
                            )
                    else:
                        if result.timing:
                            console.print(
                                f"  [red]✗[/red] {chapter_id}: {result.error} "
                                f"[dim]({result.timing.total_ms/1000:.1f}s)[/dim]"
                            )
                        else:
                            console.print(f"  [red]✗[/red] {chapter_id}: {result.error}")

    # Accumulate all results in chapter order (for non-JSON sequential mode, already done above)
    for i in range(len(selected_book.chapters)):
        if i not in results:
            continue

        status, data = results[i]
        chapter_id = selected_book.chapters[i].stem

        if status == "loaded":
            # Already loaded from cache
            accumulator.add_chapter(data)
        elif status == "extracted":
            result = data
            if result.success:
                # Only save if not already saved in sequential JSON mode
                if not json_output or workers > 1:
                    storage.save_chapter_index(result.index)
                    contradictions = accumulator.add_chapter(result.index)
                    if contradictions and verbose and not json_output:
                        for c in contradictions:
                            console.print(f"  [yellow]Contradiction ({chapter_id}):[/yellow] {c.message}")
                chapters_indexed += 1
            else:
                errors.append((chapter_id, result.error))
        elif status == "error":
            errors.append((chapter_id, data))

    # Save accumulated index
    acc_result = accumulator.get_result()
    storage.save_accumulated_index(acc_result.index)

    build_time_ms = (time.perf_counter() - build_start) * 1000

    # JSON output
    if json_output:
        acc_index = acc_result.index
        _output_json({
            "status": "success" if not errors else "partial",
            "book": selected_book.name,
            "chapters_processed": len(selected_book.chapters),
            "chapters_indexed": chapters_indexed,
            "chapters_skipped": chapters_skipped,
            "errors": len(errors),
            "contradictions": len(acc_result.contradictions),
            "contradiction_details": [_serialize_contradiction(c) for c in acc_result.contradictions],
            "total_time_ms": round(build_time_ms, 1),
            "chapters": sorted(chapter_results_json, key=_chapter_sort_key),
            "summary": {
                "characters": len(acc_index.characters) if acc_index else 0,
                "timeline_events": len(acc_index.timeline) if acc_index else 0,
                "locations": len(acc_index.locations) if acc_index else 0,
            },
        })
        return

    # Summary (Rich output)
    console.print()
    if errors:
        console.print(Panel(
            f"[green]{chapters_indexed}[/green] indexed  "
            f"[dim]{chapters_skipped}[/dim] skipped  "
            f"[red]{len(errors)}[/red] errors\n"
            f"[yellow]{len(acc_result.contradictions)}[/yellow] contradictions detected",
            title="Index Build Complete",
            border_style="yellow",
        ))
    else:
        console.print(Panel(
            f"[green]{chapters_indexed}[/green] indexed  "
            f"[dim]{chapters_skipped}[/dim] skipped\n"
            f"[yellow]{len(acc_result.contradictions)}[/yellow] contradictions detected",
            title="Index Build Complete",
            border_style="green",
        ))


@index_app.command("show")
def index_show(
    book: Optional[str] = typer.Option(
        None, "--book", "-b", help="Book to show"
    ),
    chapter: Optional[str] = typer.Option(
        None, "--chapter", "-ch", help="Specific chapter to show"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Show index summary or details."""
    from .index import IndexStorage, INDEX_SCHEMA_VERSION

    config, project = get_config_and_project(config_path)
    storage = IndexStorage(config.project_root)

    # Get stats
    stats = storage.get_stats(book)

    # Check version for each book (don't block for summary view)
    def get_book_version(book_stat: dict) -> tuple[Optional[int], bool]:
        """Return (schema_version, is_current) for a book."""
        if not book_stat.get("has_accumulated"):
            return (None, True)
        acc_index = storage.load_accumulated_index(book_stat["book_id"])
        if not acc_index:
            return (0, False)
        version = getattr(acc_index, 'schema_version', 0)
        return (version, version == INDEX_SCHEMA_VERSION)

    book_versions = {b["book_id"]: get_book_version(b) for b in stats.get("books", [])}

    if not stats["books"]:
        if json_output:
            _output_json({"status": "error", "message": "No indices found"})
        else:
            console.print("[dim]No indices found. Run 'edword index build' first.[/dim]")
        return

    if chapter:
        # Show specific chapter
        book_id = book or (stats["books"][0]["book_id"] if stats["books"] else None)
        if not book_id:
            _error_json("Specify --book", json_output)
            raise typer.Exit(1)

        # Check version before showing chapter details
        version, is_current = book_versions.get(book_id, (None, True))
        if version is not None and not is_current:
            handle_version_mismatch(
                IndexVersionMismatch(book_id, version, INDEX_SCHEMA_VERSION),
                config,
                book_id,
                json_output
            )

        index = storage.load_chapter_index(book_id, chapter)
        if not index:
            _error_json(f"Chapter '{chapter}' not found in index", json_output)
            raise typer.Exit(1)

        if json_output:
            _output_json({
                "book_id": book_id,
                "chapter_id": chapter,
                "source_path": str(index.source_path) if index.source_path else None,
                "extracted_at": str(index.extracted_at) if index.extracted_at else None,
                "characters": [
                    {
                        "id": c.id,
                        "canonical_name": c.canonical_name,
                        "mentions": c.mentions,
                        "facts_count": len(c.facts),
                    }
                    for c in index.characters
                ],
                "timeline_events": len(index.timeline),
                "locations": [{"id": loc.id, "name": loc.name} for loc in index.locations],
                "artifacts": len(index.artifacts),
                "world_facts": len(index.world_facts),
                "terminology": len(index.terminology),
                "narrative_elements": len(index.narrative),
            })
            return

        # Rich output for specific chapter
        console.print(Panel(
            f"[bold]{book_id} / {chapter}[/bold]\n"
            f"Source: {index.source_path}\n"
            f"Extracted: {index.extracted_at}",
            title="Chapter Index",
            border_style="blue",
        ))

        console.print(f"\n[bold]Characters:[/bold] {len(index.characters)}")
        for char in index.characters[:5]:  # Show first 5
            console.print(f"  - {char.canonical_name} ({char.id}): {len(char.facts)} facts")

        console.print(f"\n[bold]Timeline Events:[/bold] {len(index.timeline)}")
        for event in index.timeline[:5]:
            console.print(f"  - {event.event[:60]}...")

        console.print(f"\n[bold]Locations:[/bold] {len(index.locations)}")
        for loc in index.locations[:5]:
            console.print(f"  - {loc.name} ({loc.id})")

        console.print(f"\n[bold]Other:[/bold]")
        console.print(f"  Artifacts: {len(index.artifacts)}")
        console.print(f"  World Facts: {len(index.world_facts)}")
        console.print(f"  Terminology: {len(index.terminology)}")
        console.print(f"  Narrative Elements: {len(index.narrative)}")

    else:
        # Show summary
        if json_output:
            _output_json({
                "books": [
                    {
                        "book_id": b["book_id"],
                        "chapters": b["chapters"],
                        "has_accumulated": b["has_accumulated"],
                        "size_kb": round(b["size_bytes"] / 1024, 1),
                        "schema_version": book_versions.get(b["book_id"], (None, True))[0],
                        "version_current": book_versions.get(b["book_id"], (None, True))[1],
                    }
                    for b in stats["books"]
                ],
                "total_chapters": stats["total_chapters"],
                "total_size_kb": round(stats["total_size_bytes"] / 1024, 1),
                "current_schema_version": INDEX_SCHEMA_VERSION,
            })
            return

        # Rich output for summary
        table = Table(title="Index Summary")
        table.add_column("Book", style="cyan")
        table.add_column("Chapters", justify="right")
        table.add_column("Accumulated", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Size")

        has_outdated = False
        for book_stats in stats["books"]:
            book_id = book_stats["book_id"]
            _, is_current = book_versions.get(book_id, (None, True))
            has_accumulated = book_stats["has_accumulated"]

            # Determine status
            if not has_accumulated:
                status = "[dim]No index[/dim]"
            elif is_current:
                status = "[green]Current[/green]"
            else:
                status = "[yellow]Outdated[/yellow]"
                has_outdated = True

            table.add_row(
                book_id,
                str(len(book_stats["chapters"])),
                "[green]Yes[/green]" if has_accumulated else "[dim]No[/dim]",
                status,
                f"{book_stats['size_bytes'] / 1024:.1f}KB",
            )

        console.print(table)
        console.print(f"\n[dim]Total: {stats['total_chapters']} chapters, {stats['total_size_bytes'] / 1024:.1f}KB[/dim]")

        if has_outdated:
            console.print(f"\n[yellow]Some indices are outdated.[/yellow] Run [cyan]edword index build[/cyan] to upgrade.")


@index_app.command("clear")
def index_clear(
    book: Optional[str] = typer.Option(
        None, "--book", "-b", help="Book to clear (all if not specified)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Clear index files."""
    from .index import IndexStorage

    config, _ = get_config_and_project(config_path)
    storage = IndexStorage(config.project_root)

    if book:
        target = f"book '{book}'"
    else:
        target = "all books"

    if not force:
        confirm = typer.confirm(f"Clear index for {target}?")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            return

    if book:
        count = storage.clear_book(book)
    else:
        count = storage.clear_all()

    console.print(f"[green]Cleared {count} index files[/green]")


# --- Query Commands ---


@query_app.command("character")
def query_character_cmd(
    name: str = typer.Argument(..., help="Character name to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Look up character facts, relationships, and appearances."""
    from .query import query_character, QueryError
    import json

    config, _ = get_config_and_project(config_path)

    try:
        result = query_character(config.project_root, name, book)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except QueryError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    if not result["found"]:
        if "matches" in result and result["matches"]:
            console.print(f"[yellow]Character '{name}' not found. Did you mean:[/yellow]")
            for match in result["matches"]:
                console.print(f"  - {match['canonical_name']} ({match['id']})")
        else:
            console.print(f"[yellow]Character '{name}' not found[/yellow]")
        return

    char = result["character"]
    console.print(f"\n[bold]{char['canonical_name']}[/bold] ({char['id']})")
    console.print("━" * 40)

    mentions = char.get("mentions", [])
    if mentions:
        console.print(f"\nAlso known as: {', '.join(mentions[:10])}")
        if len(mentions) > 10:
            console.print(f"  [dim]... and {len(mentions) - 10} more[/dim]")

    facts = char.get("facts", [])
    if facts:
        console.print("\n[bold]Facts:[/bold]")
        for fact in facts[:15]:
            conf = f" ({fact['confidence']})" if fact.get("confidence") != "high" else ""
            console.print(f"  {fact['predicate']}: {fact['value']}{conf}")
        if len(facts) > 15:
            console.print(f"  [dim]... and {len(facts) - 15} more[/dim]")

    relationships = char.get("relationships", [])
    if relationships:
        console.print("\n[bold]Relationships:[/bold]")
        for rel in relationships[:10]:
            status = f" ({rel['status']})" if rel.get("status") != "active" else ""
            console.print(f"  {rel['type']} → {rel['to_id']}{status}")
        if len(relationships) > 10:
            console.print(f"  [dim]... and {len(relationships) - 10} more[/dim]")


@query_app.command("timeline")
def query_timeline_cmd(
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    chapters: Optional[str] = typer.Option(None, "--chapters", "-ch", help="Chapter range e.g. '1-5'"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit number of events"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Get timeline events."""
    from .query import query_timeline, QueryError
    import json

    config, _ = get_config_and_project(config_path)

    try:
        result = query_timeline(config.project_root, book, chapters, limit)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except (QueryError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    console.print(f"\n[bold]Timeline[/bold] ({result['total_events']} events)")
    console.print("━" * 40)

    if not result["events"]:
        console.print("[dim]No events found[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Event", style="dim", width=50)
    table.add_column("Time Ref", width=20)

    for evt in result["events"][:25]:
        event_text = evt.get("event", "")[:50]
        time_ref = evt.get("time_ref", "") or ""
        table.add_row(event_text, time_ref)

    console.print(table)

    if result["total_events"] > 25:
        console.print(f"\n[dim]... and {result['total_events'] - 25} more events[/dim]")


@query_app.command("location")
def query_location_cmd(
    name: str = typer.Argument(..., help="Location name to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Look up location details."""
    from .query import query_location, QueryError
    import json

    config, _ = get_config_and_project(config_path)

    try:
        result = query_location(config.project_root, name, book)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except QueryError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    if not result["found"]:
        if "matches" in result and result["matches"]:
            console.print(f"[yellow]Location '{name}' not found. Did you mean:[/yellow]")
            for match in result["matches"]:
                console.print(f"  - {match['name']} ({match['id']})")
        else:
            console.print(f"[yellow]Location '{name}' not found[/yellow]")
        return

    loc = result["location"]
    console.print(f"\n[bold]{loc['name']}[/bold] ({loc['id']})")
    console.print("━" * 40)

    if loc.get("description"):
        console.print(f"\n{loc['description']}")

    if loc.get("characters_present"):
        console.print(f"\nCharacters present: {', '.join(loc['characters_present'])}")

    if loc.get("significance"):
        console.print(f"\nSignificance: {loc['significance']}")


@query_app.command("artifact")
def query_artifact_cmd(
    name: str = typer.Argument(..., help="Artifact/item name to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Look up significant items/artifacts."""
    from .query import query_artifact, QueryError
    import json

    config, _ = get_config_and_project(config_path)

    try:
        result = query_artifact(config.project_root, name, book)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except QueryError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    if not result["found"]:
        if "matches" in result and result["matches"]:
            console.print(f"[yellow]Artifact '{name}' not found. Did you mean:[/yellow]")
            for match in result["matches"]:
                console.print(f"  - {match['name']} ({match['id']})")
        else:
            console.print(f"[yellow]Artifact '{name}' not found[/yellow]")
        return

    artifact = result["artifact"]
    console.print(f"\n[bold]{artifact['name']}[/bold] ({artifact['id']})")
    console.print("━" * 40)

    if artifact.get("status"):
        console.print(f"\nStatus: {artifact['status']}")

    if artifact.get("holder"):
        console.print(f"Holder: {artifact['holder']}")


@query_app.command("world")
def query_world_cmd(
    term: str = typer.Argument(..., help="World term or concept to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    as_of: Optional[str] = typer.Option(None, "--as-of", help="Show state as of chapter (e.g., '5' or 'chapter-05')"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Look up world-building facts and terminology."""
    from .query import query_world, QueryError
    import json

    config, _ = get_config_and_project(config_path)

    try:
        result = query_world(config.project_root, term, book, as_of)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except QueryError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    header = f"\n[bold]World: '{term}'[/bold] ({result['total_matches']} matches)"
    if result.get("as_of_chapter"):
        header += f" [dim](as of chapter {result['as_of_chapter']})[/dim]"
    console.print(header)
    console.print("━" * 40)

    if not result["found"]:
        console.print("[dim]No matches found[/dim]")
        return

    if result.get("terminology"):
        console.print("\n[bold]Terminology:[/bold]")
        for t in result["terminology"]:
            chapter_info = f" [dim](ch {t['chapter']})[/dim]" if t.get("chapter") else ""
            console.print(f"  [cyan]{t['term']}[/cyan]: {t['definition']}{chapter_info}")

    if result.get("world_facts"):
        console.print("\n[bold]World Facts:[/bold]")
        for f in result["world_facts"]:
            category = f.get("category", "other")
            chapter_info = f" [dim](ch {f['chapter']})[/dim]" if f.get("chapter") else ""
            console.print(f"  [{category}] {f['fact']}{chapter_info}")


@query_app.command("search")
def query_search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit results per dimension"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Search across all index dimensions."""
    from .query import query_search, QueryError
    import json

    config, _ = get_config_and_project(config_path)

    try:
        result = query_search(config.project_root, query, book, limit)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except QueryError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    console.print(f"\n[bold]Search: '{query}'[/bold] ({result['total_matches']} matches)")
    console.print("━" * 40)

    if result["total_matches"] == 0:
        console.print("[dim]No matches found[/dim]")
        return

    display_limit = 5

    chars = result.get("characters", [])
    if chars:
        console.print("\n[bold]Characters:[/bold]")
        for c in chars[:display_limit]:
            console.print(f"  - {c['canonical_name']}")
        if len(chars) > display_limit:
            console.print(f"  [dim]... and {len(chars) - display_limit} more[/dim]")

    locs = result.get("locations", [])
    if locs:
        console.print("\n[bold]Locations:[/bold]")
        for loc in locs[:display_limit]:
            console.print(f"  - {loc['name']}")
        if len(locs) > display_limit:
            console.print(f"  [dim]... and {len(locs) - display_limit} more[/dim]")

    events = result.get("events", [])
    if events:
        console.print("\n[bold]Events:[/bold]")
        for evt in events[:display_limit]:
            console.print(f"  - {evt['event'][:60]}...")
        if len(events) > display_limit:
            console.print(f"  [dim]... and {len(events) - display_limit} more[/dim]")

    artifacts = result.get("artifacts", [])
    if artifacts:
        console.print("\n[bold]Artifacts:[/bold]")
        for a in artifacts[:display_limit]:
            console.print(f"  - {a['name']}")
        if len(artifacts) > display_limit:
            console.print(f"  [dim]... and {len(artifacts) - display_limit} more[/dim]")

    terms = result.get("terminology", [])
    if terms:
        console.print("\n[bold]Terminology:[/bold]")
        for t in terms[:display_limit]:
            console.print(f"  - {t['term']}")
        if len(terms) > display_limit:
            console.print(f"  [dim]... and {len(terms) - display_limit} more[/dim]")

    facts = result.get("world_facts", [])
    if facts:
        console.print("\n[bold]World Facts:[/bold]")
        for f in facts[:display_limit]:
            console.print(f"  - {f['fact'][:60]}...")
        if len(facts) > display_limit:
            console.print(f"  [dim]... and {len(facts) - display_limit} more[/dim]")


# --- Check Command ---


@app.command("check")
def check_cmd(
    text: Optional[str] = typer.Argument(
        None, help="Text to check for consistency (or use stdin)"
    ),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Check if text contradicts indexed facts.

    Compares new text against the manuscript index to detect inconsistencies.
    Useful for verifying that proposed content doesn't contradict established facts.

    Examples:
        edword check "Greg is 35 years old"
        echo "Maya's blue eyes sparkled" | edword check --json
        cat draft.md | edword check --book book1
    """
    from .check import check_text, CheckError
    import json as json_module

    config, _ = get_config_and_project(config_path)

    # Handle stdin if no text argument
    if text is None:
        if sys.stdin.isatty():
            console.print("[red]Error:[/red] Provide text as argument or via stdin")
            console.print("\n[dim]Usage:[/dim]")
            console.print("  edword check \"Greg is 35 years old\"")
            console.print("  echo \"text\" | edword check --json")
            raise typer.Exit(1)
        text = sys.stdin.read()

    if not text or not text.strip():
        console.print("[red]Error:[/red] Text cannot be empty")
        raise typer.Exit(1)

    try:
        result = check_text(config.project_root, text, book)
    except IndexVersionMismatch as e:
        handle_version_mismatch(e, config, book or e.book_id, json_output)
    except CheckError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        # Use print() not console.print() for clean JSON (per Codex review)
        print(json_module.dumps(result, indent=2, default=str))
        return

    # Human-readable output
    if result["has_conflicts"]:
        conflict_count = len(result["conflicts"])
        console.print(f"\n[red]Found {conflict_count} conflict(s):[/red]")
        console.print("━" * 40)

        for conflict in result["conflicts"]:
            severity = conflict["severity"]
            severity_color = "red" if severity == "error" else "yellow"

            console.print(
                f"\n[{severity_color}]● {conflict['entity_name']}.{conflict['field']}[/{severity_color}]"
            )
            console.print(f"  Index says: [green]{conflict['indexed_value']}[/green]")
            console.print(f"  Text says:  [red]{conflict['text_value']}[/red]")
            console.print(f"  [dim]...{conflict['snippet']}[/dim]")

            if conflict.get("indexed_evidence"):
                evidence = conflict["indexed_evidence"]
                if evidence.get("chapter"):
                    console.print(f"  [dim]Source: {evidence['chapter']}[/dim]")
    else:
        console.print("\n[green]No conflicts found[/green]")
        console.print(
            f"[dim]Checked against {result['characters_checked']} character(s)[/dim]"
        )


# --- MCP Commands ---


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option(
        "stdio", "--transport", "-t", help="Transport type: stdio or sse"
    ),
):
    """Start the MCP server for AI assistant integration.

    Exposes edword tools via the Model Context Protocol, allowing AI assistants
    like Claude to query the manuscript index and check text for consistency.

    Examples:
        edword mcp serve              # Start with stdio transport
        edword mcp serve -t sse       # Start with SSE transport

    For Claude Code, add to .claude/settings.local.json:

        {
          "mcpServers": {
            "edword": {
              "command": "/path/to/edword",
              "args": ["mcp", "serve"],
              "env": {
                "EDWORD_PROJECT_ROOT": "/path/to/your/project"
              }
            }
          }
        }
    """
    try:
        from .mcp import main as mcp_main
    except ImportError as e:
        console.print(
            "[red]Error:[/red] FastMCP not installed. "
            "Install with: pip install edword[mcp]"
        )
        console.print(f"[dim]Details: {e}[/dim]")
        raise typer.Exit(1)

    if transport not in ("stdio", "sse"):
        console.print(f"[red]Error:[/red] Unknown transport: {transport}")
        console.print("Supported transports: stdio, sse")
        raise typer.Exit(1)

    # FastMCP defaults to stdio, which is what we want
    # For SSE, we'd need to configure differently (future enhancement)
    if transport == "sse":
        console.print("[yellow]Warning:[/yellow] SSE transport not yet implemented, using stdio")

    mcp_main()


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
