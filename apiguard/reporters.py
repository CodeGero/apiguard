"""Output reporters for presenting diff results.

Supports four output formats:
- table: Rich terminal table with color coding
- json: Machine-readable JSON output
- markdown: Human-readable Markdown report
- sarif: Static Analysis Results Interchange Format (premium)
"""

from __future__ import annotations

import json as json_lib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apiguard.differ import Change
from apiguard.rules import ChangeCategory, Severity


# Severity color/style mapping for terminal output
_SEVERITY_STYLE: Dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.WARNING: "bold yellow",
    Severity.INFO: "dim",
}

_SEVERITY_ICON: Dict[Severity, str] = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵",
    Severity.WARNING: "⚠️",
    Severity.INFO: "ℹ️",
}

_CATEGORY_LABEL: Dict[ChangeCategory, str] = {
    ChangeCategory.BREAKING: "BREAKING",
    ChangeCategory.NON_BREAKING: "NON-BREAKING",
    ChangeCategory.DEPRECATED: "DEPRECATED",
}


def _format_change_for_table(change: Change) -> Dict[str, Any]:
    """Format a single change for table rendering."""
    return {
        "Severity": _SEVERITY_ICON.get(change.severity, "  ") + " " + change.severity.value.upper(),
        "Rule": change.rule_id,
        "Category": _CATEGORY_LABEL.get(change.category, change.category.value),
        "Path": change.path or "-",
        "Method": change.method or "-",
        "Message": change.message,
    }


def _count_by_severity(changes: List[Change]) -> Dict[str, int]:
    """Count changes grouped by severity."""
    counts: Dict[str, int] = {}
    for change in changes:
        key = change.severity.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_by_category(changes: List[Change]) -> Dict[str, int]:
    """Count changes grouped by category."""
    counts: Dict[str, int] = {}
    for change in changes:
        key = change.category.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def format_table(changes: List[Change], use_rich: bool = True) -> str:
    """Format changes as a rich terminal table.

    Args:
        changes: List of detected changes.
        use_rich: If True, use the Rich library for styled output.
                  Falls back to plain text if Rich is not available.

    Returns:
        Formatted string for terminal output.
    """
    if not changes:
        return "✅ No breaking changes detected.\n"

    if use_rich:
        try:
            return _format_table_rich(changes)
        except ImportError:
            pass

    return _format_table_plain(changes)


def _format_table_rich(changes: List[Change]) -> str:
    """Format using Rich library for styled tables."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from io import StringIO

    console = Console(file=StringIO(), width=120, force_terminal=True)
    table = Table(
        title="🔍 API Breaking Changes Report",
        show_header=True,
        header_style="bold white",
        border_style="dim",
        padding=(0, 1),
    )

    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Severity", width=12)
    table.add_column("Rule", style="dim", width=10)
    table.add_column("Path", width=28)
    table.add_column("Method", width=8)
    table.add_column("Message", width=52)

    severity_order = {
        Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
        Severity.LOW: 3, Severity.WARNING: 4, Severity.INFO: 5,
    }
    sorted_changes = sorted(changes, key=lambda c: (severity_order.get(c.severity, 99), c.path, c.method))

    for i, change in enumerate(sorted_changes, 1):
        style = _SEVERITY_STYLE.get(change.severity, "")
        icon = _SEVERITY_ICON.get(change.severity, "  ")
        sev_text = f"{icon} {change.severity.value.upper()}"
        table.add_row(
            str(i),
            sev_text,
            change.rule_id,
            change.path or "-",
            change.method or "-",
            change.message,
            style=style,
        )

    console.print(table)

    # Summary panel
    counts = _count_by_severity(changes)
    cat_counts = _count_by_category(changes)
    summary_lines = [
        f"Total changes: {len(changes)}",
        f"Breaking: {cat_counts.get('breaking', 0)} | "
        f"Non-breaking: {cat_counts.get('non-breaking', 0)} | "
        f"Deprecated: {cat_counts.get('deprecated', 0)}",
    ]
    for sev in ["critical", "high", "medium", "low", "warning", "info"]:
        if counts.get(sev):
            icon = _SEVERITY_ICON.get(Severity(sev), "")
            summary_lines.append(f"{icon} {sev.upper()}: {counts[sev]}")

    console.print(Panel("\n".join(summary_lines), title="📊 Summary", border_style="dim"))

    return console.file.getvalue()


def _format_table_plain(changes: List[Change]) -> str:
    """Plain text table fallback without Rich."""
    lines = []
    lines.append("=" * 100)
    lines.append("  API Breaking Changes Report")
    lines.append("=" * 100)

    severity_order = {
        Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
        Severity.LOW: 3, Severity.WARNING: 4, Severity.INFO: 5,
    }
    sorted_changes = sorted(changes, key=lambda c: (severity_order.get(c.severity, 99), c.path, c.method))

    for i, change in enumerate(sorted_changes, 1):
        icon = _SEVERITY_ICON.get(change.severity, "")
        lines.append(
            f"  {i:3d}. {icon} [{change.severity.value.upper():8s}] "
            f"{change.rule_id:10s} "
            f"{change.method or '-':6s} {change.path or '-':30s} "
            f"{change.message}"
        )

    lines.append("-" * 100)
    counts = _count_by_severity(changes)
    cat_counts = _count_by_category(changes)
    lines.append(f"  Total: {len(changes)} | Breaking: {cat_counts.get('breaking', 0)} | "
                 f"Non-breaking: {cat_counts.get('non-breaking', 0)} | "
                 f"Deprecated: {cat_counts.get('deprecated', 0)}")
    lines.append("=" * 100)

    return "\n".join(lines) + "\n"


def format_json(changes: List[Change]) -> str:
    """Format changes as a JSON string.

    Returns a JSON object with metadata, summary, and the changes array.
    """
    output = {
        "tool": "kryptorious-apiguard",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_changes": len(changes),
            "by_severity": _count_by_severity(changes),
            "by_category": _count_by_category(changes),
        },
        "changes": [c.to_dict() for c in changes],
    }
    return json_lib.dumps(output, indent=2) + "\n"


def format_markdown(changes: List[Change]) -> str:
    """Format changes as a Markdown report.

    Suitable for GitHub PR comments, CI summaries, etc.
    """
    lines: List[str] = []

    # Header
    lines.append("# 🔍 API Breaking Changes Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Total Changes:** {len(changes)}")
    lines.append("")

    if not changes:
        lines.append("✅ **No breaking changes detected.**")
        return "\n".join(lines) + "\n"

    # Summary badges
    counts = _count_by_severity(changes)
    cat_counts = _count_by_category(changes)
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in sorted(cat_counts.items()):
        emoji = {"breaking": "🔴", "non-breaking": "🟢", "deprecated": "⚠️"}.get(cat, "")
        lines.append(f"| {emoji} {cat.title()} | {count} |")
    lines.append("")

    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    sev_order = ["critical", "high", "medium", "low", "warning", "info"]
    icons = {
        "critical": "🔴", "high": "🟠", "medium": "🟡",
        "low": "🔵", "warning": "⚠️", "info": "ℹ️",
    }
    for sev in sev_order:
        if counts.get(sev):
            lines.append(f"| {icons.get(sev, '')} {sev.upper()} | {counts[sev]} |")
    lines.append("")

    # Changes table
    lines.append("## 📋 Changes")
    lines.append("")
    lines.append("| # | Severity | Rule | Path | Method | Message |")
    lines.append("|---|----------|------|------|--------|---------|")

    severity_order = {
        Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
        Severity.LOW: 3, Severity.WARNING: 4, Severity.INFO: 5,
    }
    sorted_changes = sorted(changes, key=lambda c: (severity_order.get(c.severity, 99), c.path, c.method))

    for i, change in enumerate(sorted_changes, 1):
        icon = _SEVERITY_ICON.get(change.severity, "")
        sev = f"{icon} {change.severity.value.upper()}"
        rule = f"`{change.rule_id}`"
        path = f"`{change.path}`" if change.path else "-"
        method = f"`{change.method}`" if change.method else "-"
        msg = change.message.replace("|", "\\|")
        lines.append(f"| {i} | {sev} | {rule} | {path} | {method} | {msg} |")

    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by [Kryptorious ApiGuard]"
        "(https://kryptorious.gumroad.com/l/jbvet) — "
        "detect breaking changes before they reach production.*"
    )
    lines.append("")

    return "\n".join(lines)


def format_sarif(changes: List[Change], old_spec_path: str = "", new_spec_path: str = "") -> str:
    """Format changes as a SARIF v2.1.0 report.

    SARIF (Static Analysis Results Interchange Format) is a standard format
    for the output of static analysis tools. Compatible with GitHub Code
    Scanning, Azure DevOps, and other CI platforms.

    Args:
        changes: List of detected changes.
        old_spec_path: Path to the old spec file.
        new_spec_path: Path to the new spec file.

    Returns:
        A SARIF v2.1.0 JSON string.
    """
    results: List[Dict[str, Any]] = []

    severity_order = {
        Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
        Severity.LOW: 3, Severity.WARNING: 4, Severity.INFO: 5,
    }
    sorted_changes = sorted(changes, key=lambda c: (severity_order.get(c.severity, 99), c.path, c.method))

    # Map severity to SARIF levels
    sarif_level_map = {
        Severity.CRITICAL: "error",
        Severity.HIGH: "error",
        Severity.MEDIUM: "warning",
        Severity.LOW: "warning",
        Severity.WARNING: "note",
        Severity.INFO: "none",
    }

    for change in sorted_changes:
        result: Dict[str, Any] = {
            "ruleId": change.rule_id,
            "level": sarif_level_map.get(change.severity, "warning"),
            "message": {
                "text": change.message,
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": new_spec_path or "openapi.yaml",
                        },
                        "region": {
                            "snippet": {
                                "text": f"{change.method} {change.path}" if change.method or change.path else change.location,
                            }
                        },
                    }
                }
            ],
            "properties": {
                "severity": change.severity.value,
                "category": change.category.value,
                "path": change.path,
                "method": change.method,
                "location": change.location,
            },
        }
        results.append(result)

    # Build SARIF rules
    rules: List[Dict[str, Any]] = []
    seen_rules: set = set()
    for change in sorted_changes:
        if change.rule_id not in seen_rules:
            seen_rules.add(change.rule_id)
            rules.append({
                "id": change.rule_id,
                "shortDescription": {
                    "text": change.message,
                },
                "defaultConfiguration": {
                    "level": sarif_level_map.get(change.severity, "warning"),
                },
            })

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Kryptorious ApiGuard",
                        "version": "1.0.0",
                        "informationUri": "https://kryptorious.gumroad.com/l/jbvet",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }

    return json_lib.dumps(sarif, indent=2) + "\n"
