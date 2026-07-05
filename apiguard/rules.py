"""Breaking change rule definitions for OpenAPI semantic diffing.

Each rule describes a type of change that can occur between two API specs,
along with its default severity and the detection logic.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class Severity(enum.Enum):
    """Severity of a detected change."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    WARNING = "warning"
    INFO = "info"

    def __lt__(self, other: "Severity") -> bool:
        order = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.WARNING: 2,
            Severity.MEDIUM: 3,
            Severity.HIGH: 4,
            Severity.CRITICAL: 5,
        }
        return order[self] < order[other]

    def __le__(self, other: "Severity") -> bool:
        return self < other or self == other

    def __gt__(self, other: "Severity") -> bool:
        return not self <= other

    def __ge__(self, other: "Severity") -> bool:
        return not self < other


class ChangeCategory(enum.Enum):
    """Category of change detected."""

    BREAKING = "breaking"
    NON_BREAKING = "non-breaking"
    DEPRECATED = "deprecated"


@dataclass
class Rule:
    """A single breaking change detection rule.

    Attributes:
        id: Unique rule identifier (e.g. 'PATH-001').
        name: Human-readable rule name.
        description: Detailed description of what the rule detects.
        severity: Default severity for violations.
        category: The change category.
        check_fn: Function that performs the check. Signature:
            (old_spec, new_spec, old_endpoints, new_endpoints) -> List[Change]
    """

    id: str
    name: str
    description: str
    severity: Severity
    category: ChangeCategory
    check_fn: Callable[..., List["Change"]] = field(repr=False)


class RuleRegistry:
    """Registry of all breaking change detection rules.

    Rules can be enabled/disabled individually and filtered by severity.
    """

    def __init__(self) -> None:
        self._rules: Dict[str, Rule] = {}
        self._disabled: Set[str] = set()

    def register(self, rule: Rule) -> None:
        """Register a rule."""
        if rule.id in self._rules:
            raise ValueError(f"Duplicate rule ID: {rule.id}")
        self._rules[rule.id] = rule

    def disable(self, rule_id: str) -> None:
        """Disable a rule by ID."""
        self._disabled.add(rule_id)

    def enable(self, rule_id: str) -> None:
        """Enable a previously disabled rule."""
        self._disabled.discard(rule_id)

    def get_active_rules(
        self, min_severity: Optional[Severity] = None
    ) -> List[Rule]:
        """Get all active rules, optionally filtered by minimum severity."""
        active = [r for rid, r in self._rules.items() if rid not in self._disabled]
        if min_severity is not None:
            active = [r for r in active if r.severity >= min_severity]
        return active

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def active_count(self) -> int:
        return len(self._rules) - len(self._disabled)


# Forward reference for Change (will be defined in differ.py)
# We use a lazy import to avoid circular dependencies
Change = None  # type: ignore


def _get_change_type() -> type:
    """Lazy import of Change to avoid circular dependency."""
    global Change
    if Change is None:
        from apiguard.differ import Change as _Change

        Change = _Change
    return Change
