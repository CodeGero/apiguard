"""Semantic diff engine for OpenAPI specifications.

The core engine that compares two OpenAPI specs and identifies
breaking changes, non-breaking changes, and deprecations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from apiguard.parser import (
    extract_endpoints,
    get_parameters,
    get_request_body,
    get_responses,
    get_schema_properties,
    get_schema_type,
    get_required_properties,
    is_deprecated,
)
from apiguard.rules import ChangeCategory, Rule, RuleRegistry, Severity


@dataclass
class Change:
    """Represents a single detected change between two specs.

    Attributes:
        rule_id: The rule that detected this change (e.g. 'PATH-001').
        message: Human-readable description of the change.
        severity: Severity level of the change.
        category: Whether this is breaking, non-breaking, or deprecated.
        path: The API path affected (e.g. '/pets/{petId}').
        method: The HTTP method affected (e.g. 'GET').
        location: The location of the change (path, parameter, response, request_body, schema).
        old_value: Optional old value for reference.
        new_value: Optional new value for reference.
    """

    rule_id: str
    message: str
    severity: Severity
    category: ChangeCategory
    path: str = ""
    method: str = ""
    location: str = ""
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "path": self.path,
            "method": self.method,
            "location": self.location,
            "old_value": str(self.old_value) if self.old_value is not None else None,
            "new_value": str(self.new_value) if self.new_value is not None else None,
        }


class DiffEngine:
    """Engine for detecting differences between two OpenAPI specs.

    Usage:
        engine = DiffEngine()
        changes = engine.diff(old_spec, new_spec)
    """

    def __init__(self) -> None:
        self.registry = RuleRegistry()

    def diff(
        self,
        old_spec: Dict[str, Any],
        new_spec: Dict[str, Any],
        min_severity: Optional[Severity] = None,
    ) -> List[Change]:
        """Compare two OpenAPI specs and return all detected changes.

        Args:
            old_spec: The original (old) OpenAPI spec.
            new_spec: The new (updated) OpenAPI spec.
            min_severity: Optional minimum severity filter.

        Returns:
            A list of Change objects describing all differences found.
        """
        changes: List[Change] = []

        old_endpoints = extract_endpoints(old_spec)
        new_endpoints = extract_endpoints(new_spec)

        # === PATH-LEVEL CHANGES ===
        changes.extend(self._detect_removed_endpoints(old_endpoints, new_endpoints))
        changes.extend(self._detect_added_endpoints(old_endpoints, new_endpoints))
        changes.extend(self._detect_deprecated_endpoints(old_spec, new_spec))

        # === PER-ENDPOINT CHANGES ===
        # Check modified endpoints
        common_keys = set(old_endpoints.keys()) & set(new_endpoints.keys())
        for key in sorted(common_keys):
            old_op = old_endpoints[key]
            new_op = new_endpoints[key]
            method, path = key.split(":", 1)

            changes.extend(self._detect_parameter_changes(old_op, new_op, path, method))
            changes.extend(self._detect_response_changes(old_op, new_op, path, method, old_spec, new_spec))
            changes.extend(self._detect_request_body_changes(old_op, new_op, path, method))

        # Check new endpoints
        new_keys = set(new_endpoints.keys()) - set(old_endpoints.keys())
        for key in sorted(new_keys):
            new_op = new_endpoints[key]
            method, path = key.split(":", 1)
            changes.extend(self._detect_new_endpoint_details(new_op, path, method))

        # Filter by minimum severity if specified
        if min_severity is not None:
            changes = [c for c in changes if c.severity >= min_severity]

        return changes

    # ============================================================
    # PATH-LEVEL DETECTION
    # ============================================================

    def _detect_removed_endpoints(
        self,
        old_endpoints: Dict[str, Any],
        new_endpoints: Dict[str, Any],
    ) -> List[Change]:
        """Detect removed endpoints (CRITICAL)."""
        changes: List[Change] = []
        removed = set(old_endpoints.keys()) - set(new_endpoints.keys())
        for key in sorted(removed):
            method, path = key.split(":", 1)
            changes.append(
                Change(
                    rule_id="PATH-001",
                    message=f"Removed endpoint: {method} {path}",
                    severity=Severity.CRITICAL,
                    category=ChangeCategory.BREAKING,
                    path=path,
                    method=method,
                    location="endpoint",
                )
            )
        return changes

    def _detect_added_endpoints(
        self,
        old_endpoints: Dict[str, Any],
        new_endpoints: Dict[str, Any],
    ) -> List[Change]:
        """Detect added endpoints (INFO)."""
        changes: List[Change] = []
        added = set(new_endpoints.keys()) - set(old_endpoints.keys())
        for key in sorted(added):
            method, path = key.split(":", 1)
            changes.append(
                Change(
                    rule_id="PATH-002",
                    message=f"Added endpoint: {method} {path}",
                    severity=Severity.INFO,
                    category=ChangeCategory.NON_BREAKING,
                    path=path,
                    method=method,
                    location="endpoint",
                )
            )
        return changes

    def _detect_deprecated_endpoints(
        self,
        old_spec: Dict[str, Any],
        new_spec: Dict[str, Any],
    ) -> List[Change]:
        """Detect endpoints newly marked as deprecated (WARNING)."""
        changes: List[Change] = []
        old_endpoints = extract_endpoints(old_spec)
        new_endpoints = extract_endpoints(new_spec)

        for key, new_op in new_endpoints.items():
            old_op = old_endpoints.get(key, {})
            if not is_deprecated(old_op) and is_deprecated(new_op):
                method, path = key.split(":", 1)
                changes.append(
                    Change(
                        rule_id="DEPR-001",
                        message=f"Endpoint marked as deprecated: {method} {path}",
                        severity=Severity.WARNING,
                        category=ChangeCategory.DEPRECATED,
                        path=path,
                        method=method,
                        location="endpoint",
                    )
                )
        return changes

    # ============================================================
    # PARAMETER-LEVEL DETECTION
    # ============================================================

    def _detect_parameter_changes(
        self,
        old_op: Dict[str, Any],
        new_op: Dict[str, Any],
        path: str,
        method: str,
    ) -> List[Change]:
        """Detect all parameter-related changes."""
        changes: List[Change] = []

        old_params = {p.get("name"): p for p in get_parameters(old_op) if isinstance(p, dict) and p.get("name")}
        new_params = {p.get("name"): p for p in get_parameters(new_op) if isinstance(p, dict) and p.get("name")}

        # Removed parameters
        for name, param in old_params.items():
            if name not in new_params:
                loc = param.get("in", "unknown")
                required = param.get("required", False)
                if loc == "path" and required:
                    changes.append(
                        Change(
                            rule_id="PARAM-001",
                            message=f"Removed required path parameter '{name}'",
                            severity=Severity.CRITICAL,
                            category=ChangeCategory.BREAKING,
                            path=path,
                            method=method,
                            location=f"parameter:{loc}",
                            old_value=name,
                        )
                    )
                else:
                    sev = Severity.HIGH if required else Severity.MEDIUM
                    changes.append(
                        Change(
                            rule_id="PARAM-002",
                            message=f"Removed {'required ' if required else ''}parameter '{name}' (in {loc})",
                            severity=sev,
                            category=ChangeCategory.BREAKING,
                            path=path,
                            method=method,
                            location=f"parameter:{loc}",
                            old_value=name,
                        )
                    )

        # Added required parameters (breaking)
        for name, param in new_params.items():
            if name not in old_params:
                required = param.get("required", False)
                if required:
                    loc = param.get("in", "unknown")
                    changes.append(
                        Change(
                            rule_id="PARAM-003",
                            message=f"Added required parameter '{name}' (in {loc})",
                            severity=Severity.HIGH,
                            category=ChangeCategory.BREAKING,
                            path=path,
                            method=method,
                            location=f"parameter:{loc}",
                            new_value=name,
                        )
                    )
                else:
                    # Added optional parameter (non-breaking)
                    loc = param.get("in", "unknown")
                    changes.append(
                        Change(
                            rule_id="PARAM-004",
                            message=f"Added optional parameter '{name}' (in {loc})",
                            severity=Severity.INFO,
                            category=ChangeCategory.NON_BREAKING,
                            path=path,
                            method=method,
                            location=f"parameter:{loc}",
                            new_value=name,
                        )
                    )

        # Modified parameters (both exist)
        for name in set(old_params.keys()) & set(new_params.keys()):
            old_param = old_params[name]
            new_param = new_params[name]

            # Type change
            old_type = old_param.get("schema", {}).get("type") if isinstance(old_param.get("schema"), dict) else None
            new_type = new_param.get("schema", {}).get("type") if isinstance(new_param.get("schema"), dict) else None
            if old_type and new_type and old_type != new_type:
                changes.append(
                    Change(
                        rule_id="PARAM-005",
                        message=f"Changed parameter '{name}' type from '{old_type}' to '{new_type}'",
                        severity=Severity.HIGH,
                        category=ChangeCategory.BREAKING,
                        path=path,
                        method=method,
                        location=f"parameter",
                        old_value=old_type,
                        new_value=new_type,
                    )
                )

            # Location change
            old_loc = old_param.get("in")
            new_loc = new_param.get("in")
            if old_loc and new_loc and old_loc != new_loc:
                changes.append(
                    Change(
                        rule_id="PARAM-006",
                        message=f"Changed parameter '{name}' location from '{old_loc}' to '{new_loc}'",
                        severity=Severity.HIGH,
                        category=ChangeCategory.BREAKING,
                        path=path,
                        method=method,
                        location="parameter",
                        old_value=old_loc,
                        new_value=new_loc,
                    )
                )

            # Enum value changes
            old_schema = old_param.get("schema", {})
            new_schema = new_param.get("schema", {})
            old_enum = old_schema.get("enum") if isinstance(old_schema, dict) else None
            new_enum = new_schema.get("enum") if isinstance(new_schema, dict) else None
            if old_enum and new_enum:
                removed_enums = set(old_enum) - set(new_enum)
                added_enums = set(new_enum) - set(old_enum)
                if removed_enums:
                    changes.append(
                        Change(
                            rule_id="PARAM-007",
                            message=f"Removed enum value(s) from parameter '{name}': {sorted(removed_enums)}",
                            severity=Severity.MEDIUM,
                            category=ChangeCategory.BREAKING,
                            path=path,
                            method=method,
                            location="parameter",
                            old_value=sorted(removed_enums),
                        )
                    )
                if added_enums:
                    changes.append(
                        Change(
                            rule_id="PARAM-007a",
                            message=f"Added enum value(s) to parameter '{name}': {sorted(added_enums)}",
                            severity=Severity.INFO,
                            category=ChangeCategory.NON_BREAKING,
                            path=path,
                            method=method,
                            location="parameter",
                            new_value=sorted(added_enums),
                        )
                    )

            # Deprecation
            if not is_deprecated(old_param) and is_deprecated(new_param):
                changes.append(
                    Change(
                        rule_id="DEPR-002",
                        message=f"Parameter '{name}' marked as deprecated",
                        severity=Severity.WARNING,
                        category=ChangeCategory.DEPRECATED,
                        path=path,
                        method=method,
                        location="parameter",
                    )
                )

        return changes

    # ============================================================
    # RESPONSE-LEVEL DETECTION
    # ============================================================

    def _detect_response_changes(
        self,
        old_op: Dict[str, Any],
        new_op: Dict[str, Any],
        path: str,
        method: str,
        old_spec: Dict[str, Any],
        new_spec: Dict[str, Any],
    ) -> List[Change]:
        """Detect all response-related changes."""
        changes: List[Change] = []

        old_responses = get_responses(old_op, old_spec)
        new_responses = get_responses(new_op, new_spec)

        # Removed response status codes
        for status in old_responses:
            if status not in new_responses:
                sev = Severity.CRITICAL if status.startswith("2") else Severity.HIGH
                changes.append(
                    Change(
                        rule_id="RESP-001",
                        message=f"Removed response status {status}",
                        severity=sev,
                        category=ChangeCategory.BREAKING,
                        path=path,
                        method=method,
                        location=f"response:{status}",
                        old_value=status,
                    )
                )

        # Added response status codes
        for status in new_responses:
            if status not in old_responses:
                changes.append(
                    Change(
                        rule_id="RESP-002",
                        message=f"Added response status {status}",
                        severity=Severity.INFO,
                        category=ChangeCategory.NON_BREAKING,
                        path=path,
                        method=method,
                        location=f"response:{status}",
                        new_value=status,
                    )
                )

        # Modified response schemas
        for status in set(old_responses.keys()) & set(new_responses.keys()):
            old_schema = old_responses[status]
            new_schema = new_responses[status]

            # Skip if either schema is None (description-only)
            if old_schema is None or new_schema is None:
                continue

            # Schema type change
            old_type = get_schema_type(old_schema)
            new_type = get_schema_type(new_schema)
            if old_type and new_type and old_type != new_type:
                changes.append(
                    Change(
                        rule_id="RESP-003",
                        message=f"Changed response {status} schema type from '{old_type}' to '{new_type}'",
                        severity=Severity.HIGH,
                        category=ChangeCategory.BREAKING,
                        path=path,
                        method=method,
                        location=f"response:{status}",
                        old_value=old_type,
                        new_value=new_type,
                    )
                )

            # Property-level changes
            old_props = get_schema_properties(old_schema)
            new_props = get_schema_properties(new_schema)
            old_required = get_required_properties(old_schema)
            new_required = get_required_properties(new_schema)

            # Removed required properties
            for prop_name in old_required:
                if prop_name in new_required:
                    # Still required — check type
                    if prop_name in old_props and prop_name in new_props:
                        old_ptype = old_props[prop_name].get("type") if isinstance(old_props[prop_name], dict) else None
                        new_ptype = new_props[prop_name].get("type") if isinstance(new_props[prop_name], dict) else None
                        if old_ptype and new_ptype and old_ptype != new_ptype:
                            changes.append(
                                Change(
                                    rule_id="RESP-004",
                                    message=f"Changed response property '{prop_name}' type from '{old_ptype}' to '{new_ptype}'",
                                    severity=Severity.MEDIUM,
                                    category=ChangeCategory.BREAKING,
                                    path=path,
                                    method=method,
                                    location=f"response:{status}.{prop_name}",
                                    old_value=old_ptype,
                                    new_value=new_ptype,
                                )
                            )
                else:
                    # No longer required
                    if prop_name not in new_props:
                        # Completely removed
                        changes.append(
                            Change(
                                rule_id="RESP-005",
                                message=f"Removed required response property '{prop_name}' from {status}",
                                severity=Severity.HIGH,
                                category=ChangeCategory.BREAKING,
                                path=path,
                                method=method,
                                location=f"response:{status}.{prop_name}",
                                old_value=prop_name,
                            )
                        )
                    else:
                        # Changed from required to optional
                        changes.append(
                            Change(
                                rule_id="RESP-006",
                                message=f"Response property '{prop_name}' changed from required to optional",
                                severity=Severity.LOW,
                                category=ChangeCategory.NON_BREAKING,
                                path=path,
                                method=method,
                                location=f"response:{status}.{prop_name}",
                            )
                        )

            # Added optional properties
            for prop_name in new_props:
                if prop_name not in old_props:
                    changes.append(
                        Change(
                            rule_id="RESP-007",
                            message=f"Added response property '{prop_name}' to {status}",
                            severity=Severity.INFO,
                            category=ChangeCategory.NON_BREAKING,
                            path=path,
                            method=method,
                            location=f"response:{status}.{prop_name}",
                            new_value=prop_name,
                        )
                    )

        return changes

    # ============================================================
    # REQUEST BODY DETECTION
    # ============================================================

    def _detect_request_body_changes(
        self,
        old_op: Dict[str, Any],
        new_op: Dict[str, Any],
        path: str,
        method: str,
    ) -> List[Change]:
        """Detect request body changes."""
        changes: List[Change] = []

        old_body = get_request_body(old_op)
        new_body = get_request_body(new_op)

        # Check if request body was added or removed
        if old_body and not new_body:
            changes.append(
                Change(
                    rule_id="BODY-001",
                    message="Removed request body",
                    severity=Severity.CRITICAL,
                    category=ChangeCategory.BREAKING,
                    path=path,
                    method=method,
                    location="requestBody",
                )
            )
            return changes

        if not old_body and new_body:
            required = new_body.get("required", False)
            changes.append(
                Change(
                    rule_id="BODY-002",
                    message=f"Added {'required ' if required else ''}request body",
                    severity=Severity.HIGH if required else Severity.INFO,
                    category=ChangeCategory.BREAKING if required else ChangeCategory.NON_BREAKING,
                    path=path,
                    method=method,
                    location="requestBody",
                )
            )
            return changes

        if not old_body or not new_body:
            return changes

        # Both exist — compare
        old_schema = old_body.get("schema")
        new_schema = new_body.get("schema")
        old_props = old_body.get("properties", {})
        new_props = new_body.get("properties", {})
        old_required = old_body.get("required_props", set())
        new_required = new_body.get("required_props", set())

        # Type change
        if old_schema and new_schema:
            old_type = get_schema_type(old_schema)
            new_type = get_schema_type(new_schema)
            if old_type and new_type and old_type != new_type:
                changes.append(
                    Change(
                        rule_id="BODY-003",
                        message=f"Changed request body type from '{old_type}' to '{new_type}'",
                        severity=Severity.HIGH,
                        category=ChangeCategory.BREAKING,
                        path=path,
                        method=method,
                        location="requestBody",
                        old_value=old_type,
                        new_value=new_type,
                    )
                )

        # Required -> optional change
        old_body_required = old_body.get("required", False)
        new_body_required = new_body.get("required", False)
        if old_body_required and not new_body_required:
            changes.append(
                Change(
                    rule_id="BODY-004",
                    message="Request body changed from required to optional",
                    severity=Severity.LOW,
                    category=ChangeCategory.NON_BREAKING,
                    path=path,
                    method=method,
                    location="requestBody",
                )
            )

        # Removed properties (both required and optional)
        for prop_name in old_props:
            if prop_name not in new_props:
                if prop_name in old_required:
                    severity = Severity.CRITICAL
                    msg = f"Removed required request body property '{prop_name}'"
                else:
                    severity = Severity.MEDIUM
                    msg = f"Removed request body property '{prop_name}'"
                changes.append(
                    Change(
                        rule_id="BODY-005",
                        message=msg,
                        severity=severity,
                        category=ChangeCategory.BREAKING,
                        path=path,
                        method=method,
                        location=f"requestBody.{prop_name}",
                        old_value=prop_name,
                    )
                )

        # Changed property types in body
        for prop_name in set(old_props.keys()) & set(new_props.keys()):
            if isinstance(old_props[prop_name], dict) and isinstance(new_props[prop_name], dict):
                old_ptype = old_props[prop_name].get("type")
                new_ptype = new_props[prop_name].get("type")
                if old_ptype and new_ptype and old_ptype != new_ptype:
                    changes.append(
                        Change(
                            rule_id="BODY-006",
                            message=f"Changed request body property '{prop_name}' type from '{old_ptype}' to '{new_ptype}'",
                            severity=Severity.HIGH,
                            category=ChangeCategory.BREAKING,
                            path=path,
                            method=method,
                            location=f"requestBody.{prop_name}",
                            old_value=old_ptype,
                            new_value=new_ptype,
                        )
                    )

        return changes

    # ============================================================
    # NEW ENDPOINT DETAILS
    # ============================================================

    def _detect_new_endpoint_details(
        self,
        new_op: Dict[str, Any],
        path: str,
        method: str,
    ) -> List[Change]:
        """Report details about a new endpoint (all INFO level)."""
        changes: List[Change] = []

        # Report parameters
        params = get_parameters(new_op)
        for param in params:
            if isinstance(param, dict) and param.get("name"):
                changes.append(
                    Change(
                        rule_id="PATH-003",
                        message=f"New endpoint includes parameter '{param['name']}'",
                        severity=Severity.INFO,
                        category=ChangeCategory.NON_BREAKING,
                        path=path,
                        method=method,
                        location="parameter",
                        new_value=param["name"],
                    )
                )

        return changes
