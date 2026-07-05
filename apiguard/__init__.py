"""Kryptorious ApiGuard - Breaking change detection for OpenAPI specs.

Detect breaking changes in your OpenAPI 3.x specifications before they reach
production. Use as a CLI tool or integrate into your CI/CD pipeline.
"""

__version__ = "1.0.0"
__author__ = "Kryptorious"
__description__ = "Detect breaking changes in OpenAPI specs before they reach production"

from apiguard.differ import DiffEngine, Change, Severity
from apiguard.parser import parse_spec
from apiguard.rules import Rule, RuleRegistry

__all__ = [
    "DiffEngine",
    "Change",
    "Severity",
    "parse_spec",
    "Rule",
    "RuleRegistry",
]
