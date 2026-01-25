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
):
    """Show project information and structure."""
    config, project = get_config_and_project(config_path)

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
    save: bool = typer.Option(
        False, "--save", "-s", help="Save report to file"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose output"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Run editorial analysis passes on manuscript."""
    config, project = get_config_and_project(config_path)

    # Validate project structure
    if not project.has_manuscripts:
        console.print("[red]Error:[/red] No manuscripts directory found")
        raise typer.Exit(1)

    if not project.books:
        console.print("[red]Error:[/red] No books found in manuscripts directory")
        raise typer.Exit(1)

    # Select book
    if book:
        selected_book = get_book_by_name(project, book)
        if not selected_book:
            console.print(f"[red]Error:[/red] Book '{book}' not found")
            console.print(f"Available: {', '.join(b.name for b in project.books)}")
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
            console.print(f"[red]Error:[/red] Invalid chapter range: {chapters}")
            raise typer.Exit(1)

    # Show what we're analyzing
    console.print(Panel(
        f"[bold]{config.project_name}[/bold]\n"
        f"Book: {selected_book.name} ({selected_book.chapter_count} chapters)"
        + (f"\nChapters: {chapters}" if chapters else ""),
        title="Analyzing",
        border_style="blue",
    ))

    # Compile manuscript
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Compiling manuscript...", total=None)
        manuscript = compile_manuscript(selected_book, chapter_range)

    console.print(f"[dim]Manuscript: {len(manuscript):,} characters[/dim]")

    # Load codex if available and not disabled
    codex = ""
    if project.has_codex and not no_codex:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Loading codex...", total=None)
            codex = load_codex(project.codex_dir)
        console.print(f"[dim]Codex: {len(codex):,} characters[/dim]")
    elif no_codex:
        console.print(f"[dim]Codex: skipped (--no-codex)[/dim]")

    # Load accumulated index if requested
    accumulated_index = None
    if use_index:
        from .index.storage import IndexStorage
        storage = IndexStorage(config.project_root, str(config.paths.index))
        accumulated_index = storage.load_accumulated_index(selected_book.name)
        if accumulated_index:
            console.print(f"[dim]Index: {len(accumulated_index.characters)} characters, {len(accumulated_index.timeline)} events[/dim]")
        else:
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
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Build chapter index for a book."""
    import concurrent.futures
    from .index import (
        IndexStorage, Accumulator, ExtractionConfig,
        extract_chapter, EntityList
    )

    config, project = get_config_and_project(config_path)

    if not project.has_manuscripts:
        console.print("[red]Error:[/red] No manuscripts directory found")
        raise typer.Exit(1)

    if not project.books:
        console.print("[red]Error:[/red] No books found")
        raise typer.Exit(1)

    # Select book
    if book:
        selected_book = get_book_by_name(project, book)
        if not selected_book:
            console.print(f"[red]Error:[/red] Book '{book}' not found")
            console.print(f"Available: {', '.join(b.name for b in project.books)}")
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

    # First pass: identify which chapters need extraction
    chapters_to_extract = []  # [(index, chapter_id, chapter_path), ...]
    chapters_to_load = []     # [(index, chapter_id), ...]

    for i, chapter_path in enumerate(selected_book.chapters):
        chapter_id = chapter_path.stem
        if not force and not storage.needs_reindex(selected_book.name, chapter_id, chapter_path):
            chapters_to_load.append((i, chapter_id))
        else:
            chapters_to_extract.append((i, chapter_id, chapter_path))

    if chapters_to_load:
        console.print(f"[dim]Skipping {len(chapters_to_load)} cached chapters[/dim]")

    # Results storage: index -> ExtractionResult or loaded ChapterIndex
    results: dict = {}

    # Load cached chapters
    for i, chapter_id in chapters_to_load:
        existing = storage.load_chapter_index(selected_book.name, chapter_id)
        if existing:
            results[i] = ("loaded", existing)
            chapters_skipped += 1

    if not chapters_to_extract:
        console.print("[dim]All chapters already indexed[/dim]")
    elif workers > 1 and len(chapters_to_extract) > 1:
        # Parallel extraction
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

                    # Show progress
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
                    console.print(f"  [red]✗[/red] {chapter_id}: Exception: {e}")
                    results[i] = ("error", str(e))
    else:
        # Sequential extraction (original behavior)
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

    # Accumulate all results in chapter order
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
                storage.save_chapter_index(result.index)
                contradictions = accumulator.add_chapter(result.index)
                chapters_indexed += 1
                if contradictions and verbose:
                    for c in contradictions:
                        console.print(f"  [yellow]Contradiction ({chapter_id}):[/yellow] {c.message}")
            else:
                errors.append((chapter_id, result.error))
        elif status == "error":
            errors.append((chapter_id, data))

    # Save accumulated index
    acc_result = accumulator.get_result()
    storage.save_accumulated_index(acc_result.index)

    # Summary
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
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Show index summary or details."""
    from .index import IndexStorage

    config, project = get_config_and_project(config_path)
    storage = IndexStorage(config.project_root)

    # Get stats
    stats = storage.get_stats(book)

    if not stats["books"]:
        console.print("[dim]No indices found. Run 'edword index build' first.[/dim]")
        return

    if chapter:
        # Show specific chapter
        book_id = book or (stats["books"][0]["book_id"] if stats["books"] else None)
        if not book_id:
            console.print("[red]Error:[/red] Specify --book")
            raise typer.Exit(1)

        index = storage.load_chapter_index(book_id, chapter)
        if not index:
            console.print(f"[red]Error:[/red] Chapter '{chapter}' not found in index")
            raise typer.Exit(1)

        # Show chapter details
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
        table = Table(title="Index Summary")
        table.add_column("Book", style="cyan")
        table.add_column("Chapters", justify="right")
        table.add_column("Accumulated", justify="center")
        table.add_column("Size")

        for book_stats in stats["books"]:
            table.add_row(
                book_stats["book_id"],
                str(len(book_stats["chapters"])),
                "[green]Yes[/green]" if book_stats["has_accumulated"] else "[dim]No[/dim]",
                f"{book_stats['size_bytes'] / 1024:.1f}KB",
            )

        console.print(table)
        console.print(f"\n[dim]Total: {stats['total_chapters']} chapters, {stats['total_size_bytes'] / 1024:.1f}KB[/dim]")


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


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
