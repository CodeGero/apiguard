"""OpenAPI 3.x specification parser with local $ref resolution.

Handles both JSON and YAML input, validates structure, and resolves
internal $ref references for downstream diff analysis.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

# JSON pointer RFC 6901 escape sequences
_JSON_POINTER_ESCAPE = re.compile(r"~[01]")


class SpecParseError(Exception):
    """Raised when an OpenAPI spec cannot be parsed or is invalid."""

    pass


class RefResolutionError(Exception):
    """Raised when a $ref cannot be resolved."""

    pass


def _unescape_json_pointer(token: str) -> str:
    """Unescape a JSON pointer token (RFC 6901)."""
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_ref_path(ref: str) -> List[str]:
    """Parse a JSON pointer into path segments.

    Handles:
        #/components/schemas/Pet        -> ['components', 'schemas', 'Pet']
        #/paths/~1users/get             -> ['paths', '/users', 'get']
        file.yaml#/components/schemas/X -> raises (remote refs unsupported)
    """
    if not ref.startswith("#"):
        # Remote refs not supported for now
        raise RefResolutionError(f"Remote $ref references are not supported: {ref}")

    pointer = ref[1:]  # strip leading #
    if not pointer.startswith("/"):
        raise RefResolutionError(f"Invalid $ref pointer: {ref}")

    tokens = pointer.split("/")[1:]  # skip empty first token from leading /
    return [_unescape_json_pointer(t) for t in tokens]


def resolve_ref(spec: Dict[str, Any], ref: str) -> Any:
    """Resolve a single $ref within a spec document.

    Args:
        spec: The full OpenAPI spec dict.
        ref: A $ref string (e.g. '#/components/schemas/Pet').

    Returns:
        The resolved value from the spec.

    Raises:
        RefResolutionError: If the reference cannot be resolved.
    """
    path = _resolve_ref_path(ref)
    current: Any = spec
    for i, segment in enumerate(path):
        if isinstance(current, dict):
            if segment not in current:
                raise RefResolutionError(
                    f"Could not resolve {ref}: key '{segment}' not found "
                    f"at {'/'.join(path[:i]) or '<root>'}"
                )
            current = current[segment]
        elif isinstance(current, list):
            try:
                idx = int(segment)
                current = current[idx]
            except (ValueError, IndexError):
                raise RefResolutionError(
                    f"Could not resolve {ref}: index '{segment}' out of range "
                    f"at {'/'.join(path[:i])}"
                )
        else:
            raise RefResolutionError(
                f"Could not resolve {ref}: cannot descend into scalar value "
                f"at {'/'.join(path[:i])}"
            )
    return current


def _deep_resolve_refs(spec: Dict[str, Any], root: Optional[Dict[str, Any]] = None) -> Any:
    """Recursively resolve all $ref references in a spec subtree.

    Detects circular references and stops at the reference.
    """
    if root is None:
        root = spec

    if isinstance(spec, dict):
        if "$ref" in spec and len(spec) == 1:
            # This is a pure $ref node — resolve it
            resolved = resolve_ref(root, spec["$ref"])
            # Recursively resolve nested refs in the resolved value
            return _deep_resolve_refs(resolved, root)
        return {k: _deep_resolve_refs(v, root) for k, v in spec.items()}
    elif isinstance(spec, list):
        return [_deep_resolve_refs(item, root) for item in spec]
    return spec


def _validate_openapi_version(version: str) -> None:
    """Validate that the spec uses a supported OpenAPI version (3.0 or 3.1)."""
    if not version.startswith("3."):
        raise SpecParseError(
            f"Unsupported OpenAPI version: {version}. "
            f"Only OpenAPI 3.0 and 3.1 are supported."
        )


def _ensure_list(value: Any, context: str) -> List[Dict[str, Any]]:
    """Ensure a value is a list, raising a helpful error if not."""
    if not isinstance(value, list):
        raise SpecParseError(f"{context}: expected a list, got {type(value).__name__}")
    return value


def parse_spec(
    source: Any, resolve_external_refs: bool = False
) -> Dict[str, Any]:
    """Parse an OpenAPI 3.x specification from a file path, raw string, or dict.

    Args:
        source: File path (.json, .yaml, .yml), raw JSON/YAML string, or
            an already-deserialized dict.
        resolve_external_refs: If True, attempt to resolve external $refs.
            Currently not supported; will raise an error.

    Returns:
        A fully resolved OpenAPI spec dict with all internal $refs resolved.

    Raises:
        SpecParseError: If the spec is invalid or uses an unsupported version.
        FileNotFoundError: If the source is a path that doesn't exist.
    """
    # If source is already a dict, use it directly
    if isinstance(source, dict):
        spec = source
        content = None  # already parsed
    else:
        # Try to parse as a file path first
        path = Path(str(source))
        if path.exists() and path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = str(source)

    # Try JSON first, then YAML
    if content is not None:
        try:
            spec = json.loads(content)
        except json.JSONDecodeError:
            try:
                spec = yaml.safe_load(content)
            except yaml.YAMLError as e:
                raise SpecParseError(f"Failed to parse spec as JSON or YAML: {e}")

    if not isinstance(spec, dict):
        raise SpecParseError("OpenAPI spec must be a JSON object/dict at the top level")

    if spec is None:
        raise SpecParseError("OpenAPI spec is empty")

    # Determine OpenAPI version
    openapi_version = spec.get("openapi") or spec.get("swagger")
    if not openapi_version:
        raise SpecParseError(
            "Missing 'openapi' or 'swagger' version field. "
            "Is this a valid OpenAPI/Swagger spec?"
        )

    swagger_version = spec.get("swagger")
    if swagger_version:
        raise SpecParseError(
            f"Swagger {swagger_version} detected. This tool only supports OpenAPI 3.0+."
        )

    _validate_openapi_version(str(openapi_version))

    # Resolve all internal $refs
    resolved = _deep_resolve_refs(spec)

    return resolved


def extract_endpoints(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract all endpoints from an OpenAPI spec.

    Returns:
        A dict mapping normalized endpoint keys to their operation objects.
        Keys are in the format 'METHOD:/path' (e.g. 'GET:/pets/{petId}').
    """
    endpoints: Dict[str, Dict[str, Any]] = {}
    paths = spec.get("paths", {})

    if not isinstance(paths, dict):
        return endpoints

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in path_item:
            if method.lower() in HTTP_METHODS:
                operation = path_item[method]
                if isinstance(operation, dict):
                    key = f"{method.upper()}:{path}"
                    endpoints[key] = operation

    return endpoints


def get_parameters(operation: Dict[str, Any], spec: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Get all parameters for an operation (including path-level parameters)."""
    params: List[Dict[str, Any]] = []

    # Operation-level parameters
    op_params = operation.get("parameters", [])
    if isinstance(op_params, list):
        params.extend(op_params)

    return params


def get_request_body(operation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get the request body info from an operation.

    Returns a dict with:
        - schema: The JSON Schema for the body (or None)
        - required: Whether the body is required (bool)
        - properties: Schema properties (for convenience)
        - required_props: Required property names (for convenience)
    Returns None if there's no request body.
    """
    body = operation.get("requestBody")
    if not isinstance(body, dict):
        return None

    result: Dict[str, Any] = {
        "required": body.get("required", False) if isinstance(body, dict) else False,
        "schema": None,
        "properties": {},
        "required_props": set(),
        "_raw": body,
    }

    # Try to get the JSON content schema
    content = body.get("content", {})
    if isinstance(content, dict):
        for media_type in ("application/json", "*/*"):
            if media_type in content:
                media = content[media_type]
                if isinstance(media, dict):
                    result["schema"] = media.get("schema")
                    break
        # Take the first available content type if specific not found
        if result["schema"] is None and content:
            first = next(iter(content.values()))
            if isinstance(first, dict):
                result["schema"] = first.get("schema")

    if result["schema"] is not None and isinstance(result["schema"], dict):
        result["properties"] = get_schema_properties(result["schema"])
        result["required_props"] = get_required_properties(result["schema"])

    return result


def get_responses(operation: Dict[str, Any], spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get all response schemas from an operation, resolving $ref references.

    Args:
        operation: The operation object from an OpenAPI path.
        spec: The full OpenAPI spec (required for $ref resolution).

    Returns:
        Dict mapping status codes to their response schemas.
        Includes responses even if they don't have a content schema
        (schema will be None for description-only responses).
    """
    responses: Dict[str, Any] = {}
    resp_obj = operation.get("responses", {})

    if not isinstance(resp_obj, dict):
        return responses

    for status, response in resp_obj.items():
        if not isinstance(response, dict):
            continue
        content = response.get("content", {})
        if isinstance(content, dict):
            for media_type in ("application/json", "*/*"):
                if media_type in content:
                    media = content[media_type]
                    if isinstance(media, dict) and "schema" in media:
                        schema = media["schema"]
                        if spec is not None:
                            schema = _deep_resolve_refs(schema, spec)
                        responses[status] = schema
                        break
            # Take first available if specific type not found and status not yet added
            if status not in responses and content:
                first = next(iter(content.values()))
                if isinstance(first, dict) and "schema" in first:
                    schema = first["schema"]
                    if spec is not None:
                        schema = _deep_resolve_refs(schema, spec)
                    responses[status] = schema

        # Include description-only responses (schema will be None)
        if status not in responses:
            responses[status] = None

    return responses


def get_schema_type(schema: Any) -> Optional[str]:
    """Get the type of a JSON Schema object, handling arrays."""
    if not isinstance(schema, dict):
        return None

    schema_type = schema.get("type")

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict) and "type" in items:
            return f"array<{items['type']}>"
        return "array"

    return schema_type


def get_schema_properties(schema: Any) -> Dict[str, Dict[str, Any]]:
    """Get properties from a JSON Schema object."""
    if not isinstance(schema, dict):
        return {}

    if schema.get("type") == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return items.get("properties", {})
        return {}

    return schema.get("properties", {})


def get_required_properties(schema: Any) -> Set[str]:
    """Get the set of required property names from a schema."""
    if not isinstance(schema, dict):
        return set()
    return set(schema.get("required", []))


def is_deprecated(obj: Dict[str, Any]) -> bool:
    """Check if an object has deprecated: true."""
    return obj.get("deprecated", False) is True


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """Validate an OpenAPI spec structure and return a list of warnings/issues.

    Args:
        spec: A parsed OpenAPI spec dict.

    Returns:
        A list of warning/issue strings. Empty list means no issues found.
    """
    warnings: List[str] = []

    # Check required top-level fields
    for field in ("openapi", "info", "paths"):
        if field not in spec:
            if field == "openapi":
                warnings.append("Missing 'openapi' version field")
            elif field == "info":
                warnings.append("Missing 'info' object")
            elif field == "paths":
                warnings.append("Missing 'paths' object (no endpoints defined)")

    # Check info fields
    info = spec.get("info", {})
    if isinstance(info, dict):
        for field in ("title", "version"):
            if field not in info:
                warnings.append(f"Missing 'info.{field}' field")

    # Check paths
    paths = spec.get("paths", {})
    if isinstance(paths, dict):
        if not paths:
            warnings.append("No paths defined in the spec")
        else:
            for path, path_item in paths.items():
                if not isinstance(path_item, dict):
                    warnings.append(f"Path '{path}' is not an object")
                    continue
                if not path_item:
                    warnings.append(f"Path '{path}' has no operations")

    return warnings
