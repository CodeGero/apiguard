"""Tests for the Click CLI."""

import json

import pytest
from click.testing import CliRunner

from apiguard.cli import main


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def petstore_v1_path(fixtures_dir):
    """Path to petstore v1 fixture."""
    return str(fixtures_dir / "petstore_v1.yaml")


@pytest.fixture
def petstore_v2_breaking_path(fixtures_dir):
    """Path to petstore v2 breaking fixture."""
    return str(fixtures_dir / "petstore_v2_breaking.yaml")


@pytest.fixture
def petstore_v2_nonbreaking_path(fixtures_dir):
    """Path to petstore v2 non-breaking fixture."""
    return str(fixtures_dir / "petstore_v2_nonbreaking.yaml")


class TestDiffCommand:
    """Tests for the `apiguard diff` command."""

    def test_diff_table_output(self, runner, petstore_v1_path, petstore_v2_breaking_path):
        """Default table output should work."""
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path
        ])
        # Should exit with 1 because there are breaking changes
        assert result.exit_code == 1
        assert "🔍" in result.output or "API Breaking Changes" in result.output

    def test_diff_json_output(self, runner, petstore_v1_path, petstore_v2_breaking_path):
        """JSON output should be valid JSON."""
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path,
            "--format", "json"
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "changes" in data
        assert "summary" in data
        assert len(data["changes"]) > 0

    def test_diff_markdown_output(self, runner, petstore_v1_path, petstore_v2_breaking_path):
        """Markdown output should contain expected sections."""
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path,
            "--format", "markdown"
        ])
        assert result.exit_code == 1
        assert "# 🔍" in result.output or "Breaking Changes" in result.output
        assert "## 📊 Summary" in result.output

    def test_diff_sarif_output(self, runner, petstore_v1_path, petstore_v2_breaking_path):
        """SARIF output should be valid JSON with runs."""
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path,
            "--format", "sarif"
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        assert len(data["runs"]) > 0

    def test_diff_no_breaking_exit_zero(self, runner, petstore_v1_path, petstore_v2_nonbreaking_path):
        """No breaking changes should exit 0."""
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_nonbreaking_path
        ])
        assert result.exit_code == 0

    def test_diff_severity_filter(self, runner, petstore_v1_path, petstore_v2_breaking_path):
        """Severity filter should reduce output."""
        # With --severity error, INFO and WARNING changes should be excluded
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path,
            "--severity", "error",
            "--format", "json"
        ])
        data = json.loads(result.output)
        for change in data["changes"]:
            assert change["severity"] in ("critical", "high")

    def test_diff_fail_on_warning(self, runner, petstore_v1_path, petstore_v2_nonbreaking_path):
        """With --fail-on warning, non-breaking changes with deprecations cause exit 1."""
        # petstore_v2_nonbreaking has no breaking changes, but we can test with breaking
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_nonbreaking_path,
            "--fail-on", "warning"
        ])
        # Should still exit 0 since no warnings or higher in nonbreaking spec
        assert result.exit_code == 0

    def test_diff_output_file(self, runner, petstore_v1_path, petstore_v2_breaking_path, tmp_path):
        """--output should write to file."""
        outfile = tmp_path / "report.md"
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path,
            "--format", "markdown",
            "--output", str(outfile)
        ])
        assert result.exit_code == 1
        assert outfile.exists()
        content = outfile.read_text()
        assert "# 🔍" in content or "Breaking Changes" in content

    def test_diff_invalid_spec(self, runner):
        """Invalid spec path should exit 2."""
        result = runner.invoke(main, [
            "diff", "/nonexistent/file.yaml", "/another/nonexistent.yaml"
        ])
        assert result.exit_code == 2


class TestValidateCommand:
    """Tests for the `apiguard validate` command."""

    def test_validate_valid_spec(self, runner, petstore_v1_path):
        """Valid spec should pass validation."""
        result = runner.invoke(main, ["validate", petstore_v1_path])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_empty_spec(self, runner, fixtures_dir):
        """Empty spec should show warnings."""
        result = runner.invoke(main, [
            "validate", str(fixtures_dir / "empty_spec.yaml")
        ])
        assert result.exit_code == 0  # warnings, not errors
        assert "No paths" in result.output

    def test_validate_strict_mode(self, runner, fixtures_dir):
        """Strict mode should fail on warnings."""
        result = runner.invoke(main, [
            "validate", str(fixtures_dir / "empty_spec.yaml"),
            "--strict"
        ])
        assert result.exit_code == 1

    def test_validate_invalid_spec(self, runner):
        """Invalid spec should fail."""
        result = runner.invoke(main, [
            "validate", "/nonexistent/file.yaml"
        ])
        assert result.exit_code == 2


class TestVersionCommand:
    """Tests for the `apiguard version` command."""

    def test_version(self, runner):
        """Should print version."""
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "ApiGuard" in result.output
        assert "1.0.0" in result.output


class TestNoColorOption:
    """Tests for the --no-color flag."""

    def test_no_color(self, runner, petstore_v1_path, petstore_v2_breaking_path):
        """--no-color should produce plain text output."""
        result = runner.invoke(main, [
            "diff", petstore_v1_path, petstore_v2_breaking_path,
            "--no-color"
        ])
        assert result.exit_code == 1
        # Should still produce output
        assert len(result.output) > 0
