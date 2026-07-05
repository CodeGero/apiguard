"""Click-based CLI for Kryptorious ApiGuard.

Usage:
    apiguard diff old.yaml new.yaml
    apiguard validate spec.yaml
    apiguard version
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from apiguard.differ import DiffEngine
from apiguard.parser import parse_spec, validate_spec, SpecParseError
from apiguard.reporters import format_table, format_json, format_markdown, format_sarif
from apiguard.rules import Severity

__version__ = "1.0.0"


def _resolve_severity(value: str) -> Optional[Severity]:
    """Convert severity string to Severity enum."""
    if value == "error":
        return Severity.HIGH  # "error" means HIGH and above
    if value == "warning":
        return Severity.WARNING
    if value == "info":
        return Severity.INFO
    return None


def _resolve_fail_severity(value: str) -> Severity:
    """Convert fail-on string to minimum severity for exit code."""
    mapping = {
        "error": Severity.HIGH,
        "warning": Severity.WARNING,
    }
    return mapping.get(value, Severity.HIGH)


def _print_error(message: str) -> None:
    """Print a styled error message."""
    try:
        click.secho(f"✖ {message}", fg="red", bold=True, err=True)
    except Exception:
        click.echo(f"ERROR: {message}", err=True)


def _print_success(message: str) -> None:
    """Print a styled success message."""
    try:
        click.secho(f"✓ {message}", fg="green", bold=True)
    except Exception:
        click.echo(f"SUCCESS: {message}")


def _print_warning(message: str) -> None:
    """Print a styled warning message."""
    try:
        click.secho(f"⚠ {message}", fg="yellow")
    except Exception:
        click.echo(f"WARNING: {message}")


@click.group()
@click.version_option(version=__version__, prog_name="apiguard")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Kryptorious ApiGuard — Detect breaking changes in OpenAPI specs.

    Compare two OpenAPI 3.x specifications and identify breaking changes,
    non-breaking changes, and deprecations before they reach production.
    """
    ctx.ensure_object(dict)


@main.command("diff")
@click.argument("old_spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("new_spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["table", "json", "markdown", "sarif"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--severity", "-s",
    type=click.Choice(["error", "warning", "info"], case_sensitive=False),
    default="warning",
    help="Minimum severity to report (default: warning)",
)
@click.option(
    "--fail-on",
    type=click.Choice(["error", "warning"], case_sensitive=False),
    default="error",
    help="Exit non-zero when changes at or above this severity are found (default: error)",
)
@click.option(
    "--output", "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write output to file instead of stdout",
)
@click.option(
    "--no-color",
    is_flag=True,
    default=False,
    help="Disable colored output",
)
def diff_command(
    old_spec: Path,
    new_spec: Path,
    output_format: str,
    severity: str,
    fail_on: str,
    output: Optional[Path],
    no_color: bool,
) -> None:
    """Compare two OpenAPI specs and report breaking changes.

    \b
    OLD_SPEC  Path to the original (baseline) OpenAPI spec
    NEW_SPEC  Path to the updated OpenAPI spec
    """
    # Read and parse specs
    try:
        old = parse_spec(str(old_spec))
    except SpecParseError as e:
        _print_error(f"Failed to parse old spec '{old_spec}': {e}")
        raise SystemExit(2)
    except Exception as e:
        _print_error(f"Failed to read old spec '{old_spec}': {e}")
        raise SystemExit(2)

    try:
        new = parse_spec(str(new_spec))
    except SpecParseError as e:
        _print_error(f"Failed to parse new spec '{new_spec}': {e}")
        raise SystemExit(2)
    except Exception as e:
        _print_error(f"Failed to read new spec '{new_spec}': {e}")
        raise SystemExit(2)

    # Determine severity filter
    min_sev = _resolve_severity(severity)

    # Run the diff
    engine = DiffEngine()
    changes = engine.diff(old, new, min_severity=min_sev)

    # Format output
    if output_format == "table":
        result = format_table(changes, use_rich=not no_color)
    elif output_format == "json":
        result = format_json(changes)
    elif output_format == "markdown":
        result = format_markdown(changes)
    elif output_format == "sarif":
        result = format_sarif(changes, str(old_spec), str(new_spec))
    else:
        result = format_table(changes, use_rich=not no_color)

    # Write to file or stdout
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result, encoding="utf-8")
        _print_success(f"Report written to {output}")
    else:
        click.echo(result, nl=False)

    # Determine exit code
    fail_sev = _resolve_fail_severity(fail_on)
    critical_changes = [c for c in changes if c.severity >= fail_sev]

    if critical_changes:
        count = len(critical_changes)
        # Don't pollute structured output (JSON/SARIF) with messages
        if output_format in ("table", "markdown"):
            click.echo(
                click.style(f"✖ Found {count} change(s) at or above {fail_on} severity", fg="red", bold=True),
                err=True,
            )
        raise SystemExit(1)

    if changes:
        # Changes exist but below fail threshold
        pass

    raise SystemExit(0)


@main.command("validate")
@click.argument("spec_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat warnings as errors",
)
def validate_command(spec_path: Path, strict: bool) -> None:
    """Validate a single OpenAPI spec for structural correctness.

    Checks that the spec is well-formed and follows OpenAPI 3.x conventions.
    """
    try:
        spec = parse_spec(str(spec_path))
    except SpecParseError as e:
        _print_error(f"Invalid spec: {e}")
        raise SystemExit(2)

    warnings = validate_spec(spec)

    # Print spec info
    info = spec.get("info", {})
    title = info.get("title", "Unknown")
    version = info.get("version", "unknown")
    openapi_version = spec.get("openapi", "unknown")

    click.echo()
    click.secho(f"  Title: {title}", bold=True)
    click.echo(f"  Version: {version}")
    click.echo(f"  OpenAPI: {openapi_version}")

    paths = spec.get("paths", {})
    endpoint_count = sum(
        1 for p in paths.values() if isinstance(p, dict)
        for m in p if m.lower() in {"get", "post", "put", "delete", "patch", "options", "head", "trace"}
    ) if isinstance(paths, dict) else 0
    click.echo(f"  Endpoints: {endpoint_count}")
    click.echo()

    if warnings:
        if strict:
            for warning in warnings:
                _print_error(warning)
            _print_error(f"Validation failed with {len(warnings)} issue(s) in strict mode")
            raise SystemExit(1)
        else:
            for warning in warnings:
                _print_warning(warning)
            _print_warning(f"Found {len(warnings)} issue(s)")
    else:
        _print_success("Spec is valid")


@main.command("version")
def version_command() -> None:
    """Show the version and exit."""
    click.echo(f"Kryptorious ApiGuard v{__version__}")
    click.echo("https://kryptorious.gumroad.com/l/jbvet")
