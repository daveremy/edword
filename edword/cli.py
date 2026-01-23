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


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
