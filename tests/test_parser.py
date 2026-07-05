"""Tests for the OpenAPI spec parser."""

import pytest

from apiguard.parser import (
    parse_spec,
    validate_spec,
    extract_endpoints,
    get_parameters,
    get_request_body,
    get_responses,
    get_schema_type,
    get_schema_properties,
    get_required_properties,
    is_deprecated,
    resolve_ref,
    SpecParseError,
    RefResolutionError,
)


class TestParseSpec:
    """Tests for parse_spec function."""

    def test_parse_valid_yaml(self, petstore_v1):
        """Should parse a valid OpenAPI 3.0 YAML spec."""
        assert petstore_v1["openapi"] == "3.0.3"
        assert petstore_v1["info"]["title"] == "Petstore API"
        assert "paths" in petstore_v1

    def test_parse_rejects_swagger_2(self, fixtures_dir):
        """Should reject Swagger 2.0 specs."""
        swagger_spec = '{"swagger": "2.0", "info": {"title": "Test", "version": "1.0"}, "paths": {}}'
        with pytest.raises(SpecParseError, match="Swagger 2.0"):
            parse_spec(swagger_spec)

    def test_parse_rejects_empty(self):
        """Should reject empty/null specs."""
        with pytest.raises(SpecParseError, match="object"):
            parse_spec("null")

    def test_parse_rejects_non_object(self):
        """Should reject specs that aren't objects."""
        with pytest.raises(SpecParseError, match="object"):
            parse_spec('["not", "an", "object"]')

    def test_parse_rejects_missing_version(self):
        """Should reject specs without openapi/swagger field."""
        bad = '{"info": {"title": "Test"}, "paths": {}}'
        with pytest.raises(SpecParseError, match="Missing"):
            parse_spec(bad)

    def test_parse_rejects_unsupported_version(self):
        """Should reject OpenAPI 2 or 4.x."""
        bad = '{"openapi": "4.0.0", "info": {"title": "Test"}, "paths": {}}'
        with pytest.raises(SpecParseError, match="Unsupported"):
            parse_spec(bad)

    def test_parse_handles_json(self):
        """Should parse JSON specs."""
        spec = parse_spec(
            '{"openapi": "3.0.3", "info": {"title": "Test", "version": "1.0"}, "paths": {}}'
        )
        assert spec["openapi"] == "3.0.3"


class TestRefResolution:
    """Tests for $ref resolution."""

    def test_resolve_simple_ref(self):
        """Should resolve a simple #/components/schemas/X ref."""
        spec = {
            "openapi": "3.0.3",
            "components": {
                "schemas": {
                    "Pet": {"type": "object", "properties": {"name": {"type": "string"}}}
                }
            }
        }
        result = resolve_ref(spec, "#/components/schemas/Pet")
        assert result == {"type": "object", "properties": {"name": {"type": "string"}}}

    def test_resolve_nested_ref(self):
        """Should resolve refs within resolved values."""
        spec = {
            "openapi": "3.0.3",
            "paths": {
                "/pets": {
                    "get": {
                        "responses": {
                            "200": {
                                "$ref": "#/components/responses/PetResponse"
                            }
                        }
                    }
                }
            },
            "components": {
                "responses": {
                    "PetResponse": {
                        "description": "A pet",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Pet"}
                            }
                        }
                    }
                },
                "schemas": {
                    "Pet": {"type": "object"}
                }
            }
        }
        parsed = parse_spec(spec)
        # After resolution, the $ref should be resolved
        resp = parsed["paths"]["/pets"]["get"]["responses"]["200"]
        assert resp["content"]["application/json"]["schema"]["type"] == "object"

    def test_resolve_invalid_ref(self):
        """Should raise on invalid $ref."""
        spec = {"openapi": "3.0.3"}
        with pytest.raises(RefResolutionError):
            resolve_ref(spec, "#/nonexistent/path")

    def test_resolve_remote_ref_raises(self):
        """Should raise on remote $ref references."""
        with pytest.raises(RefResolutionError, match="Remote"):
            resolve_ref({}, "external.yaml#/components/schemas/X")


class TestExtractEndpoints:
    """Tests for extract_endpoints function."""

    def test_extract_basic_endpoints(self):
        """Should extract GET and POST endpoints."""
        spec = {
            "openapi": "3.0.3",
            "paths": {
                "/pets": {
                    "get": {"summary": "List pets"},
                    "post": {"summary": "Create pet"},
                },
                "/pets/{id}": {
                    "get": {"summary": "Get pet"},
                }
            }
        }
        endpoints = extract_endpoints(spec)
        assert len(endpoints) == 3
        assert "GET:/pets" in endpoints
        assert "POST:/pets" in endpoints
        assert "GET:/pets/{id}" in endpoints

    def test_extract_ignores_non_http(self):
        """Should ignore non-HTTP-method keys in path items."""
        spec = {
            "openapi": "3.0.3",
            "paths": {
                "/pets": {
                    "get": {"summary": "List"},
                    "parameters": [],
                    "summary": "Pet operations",
                }
            }
        }
        endpoints = extract_endpoints(spec)
        assert len(endpoints) == 1
        assert "GET:/pets" in endpoints


class TestParameters:
    """Tests for parameter extraction."""

    def test_get_parameters(self):
        """Should extract parameters from an operation."""
        op = {
            "parameters": [
                {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                {"name": "status", "in": "query", "schema": {"type": "string"}},
            ]
        }
        params = get_parameters(op)
        assert len(params) == 2
        assert params[0]["name"] == "limit"


class TestRequestBody:
    """Tests for request body extraction."""

    def test_get_request_body(self):
        """Should extract the request body schema."""
        op = {
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}}
                        }
                    }
                }
            }
        }
        body = get_request_body(op)
        assert body is not None
        assert body["schema"]["type"] == "object"
        assert body["required"] is True
        assert "name" in body["properties"]

    def test_get_request_body_none(self):
        """Should return None when there's no request body."""
        op = {"parameters": []}
        body = get_request_body(op)
        assert body is None


class TestResponses:
    """Tests for response extraction."""

    def test_get_responses(self):
        """Should extract response schemas."""
        op = {
            "responses": {
                "200": {
                    "description": "OK",
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"}
                        }
                    }
                }
            }
        }
        responses = get_responses(op)
        assert "200" in responses
        assert responses["200"]["type"] == "object"


class TestSchemaHelpers:
    """Tests for schema utility functions."""

    def test_get_schema_type_simple(self):
        assert get_schema_type({"type": "string"}) == "string"
        assert get_schema_type({"type": "integer"}) == "integer"
        assert get_schema_type({"type": "object"}) == "object"

    def test_get_schema_type_array(self):
        schema = {"type": "array", "items": {"type": "string"}}
        assert get_schema_type(schema) == "array<string>"

    def test_get_schema_type_array_no_items_type(self):
        schema = {"type": "array", "items": {}}
        assert get_schema_type(schema) == "array"

    def test_get_schema_type_none(self):
        assert get_schema_type(None) is None
        assert get_schema_type({}) is None
        assert get_schema_type("not a dict") is None

    def test_get_schema_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            }
        }
        props = get_schema_properties(schema)
        assert len(props) == 2
        assert "name" in props
        assert "age" in props

    def test_get_schema_properties_array(self):
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"}
                }
            }
        }
        props = get_schema_properties(schema)
        assert len(props) == 1
        assert "id" in props

    def test_get_required_properties(self):
        schema = {"type": "object", "required": ["name", "email"]}
        required = get_required_properties(schema)
        assert required == {"name", "email"}

    def test_get_required_properties_empty(self):
        assert get_required_properties({}) == set()
        assert get_required_properties(None) == set()

    def test_is_deprecated(self):
        assert is_deprecated({"deprecated": True}) is True
        assert is_deprecated({"deprecated": False}) is False
        assert is_deprecated({"deprecated": "true"}) is False
        assert is_deprecated({}) is False


class TestValidateSpec:
    """Tests for spec validation."""

    def test_valid_spec_no_warnings(self, petstore_v1):
        """Valid spec should have no warnings."""
        warnings = validate_spec(petstore_v1)
        assert warnings == []

    def test_missing_fields_warns(self):
        """Missing required fields should generate warnings."""
        spec = {"openapi": "3.0.3"}
        warnings = validate_spec(spec)
        assert len(warnings) > 0
        assert any("info" in w.lower() for w in warnings)
        assert any("paths" in w.lower() for w in warnings)

    def test_empty_paths_warns(self):
        """Empty paths should generate a warning."""
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {}
        }
        warnings = validate_spec(spec)
        assert len(warnings) > 0
        assert any("no paths" in w.lower() for w in warnings)

    def test_missing_info_fields(self):
        """Missing info fields should warn."""
        spec = {
            "openapi": "3.0.3",
            "info": {},
            "paths": {"/test": {"get": {"responses": {"200": {"description": "OK"}}}}}
        }
        warnings = validate_spec(spec)
        assert any("title" in w.lower() for w in warnings)
        assert any("version" in w.lower() for w in warnings)

    def test_non_dict_path_item(self):
        """Non-dict path items should warn."""
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {"/bad": "not an object"}
        }
        warnings = validate_spec(spec)
        assert any("not an object" in w.lower() for w in warnings)
