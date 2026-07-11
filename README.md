# ApiGuard — OpenAPI Breaking Change Detector

**Detect breaking changes in your API specs before they reach production.**

ApiGuard compares two OpenAPI 3.x specifications and identifies every breaking change, non-breaking change, and deprecation — with severity levels, rule IDs, and CI-ready output.

```bash
pip install kryptorious-apiguard
```

## Quick Start

```bash
# Compare two specs
apiguard diff openapi-v1.yaml openapi-v2.yaml

# JSON output for CI pipelines
apiguard diff old.yaml new.yaml --format json

# Fail CI on any breaking change
apiguard diff old.yaml new.yaml --fail-on warning
```

## What It Detects

| Severity | Category | Examples |
|----------|----------|----------|
| 🔴 CRITICAL | Removed endpoint, removed response status, removed required path param |
| 🟠 HIGH | Changed parameter type, added required param, removed required property |
| 🟡 MEDIUM | Removed enum value, changed response property type |
| ⚠️ WARNING | Deprecated endpoint, deprecated parameter |
| ℹ️ INFO | Added endpoint, added optional param, added response field |

**30+ detection rules** covering paths, parameters, responses, request bodies, and deprecations.

## Output Formats

```bash
apiguard diff v1.yaml v2.yaml                    # Rich terminal table (default)
apiguard diff v1.yaml v2.yaml --format json      # Machine-readable JSON
apiguard diff v1.yaml v2.yaml --format markdown  # Markdown report
apiguard diff v1.yaml v2.yaml --format sarif     # SARIF (Premium)
```

## CI/CD Integration

```yaml
# .github/workflows/api-check.yml
name: API Breaking Change Check
on: [pull_request]
jobs:
  api-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install kryptorious-apiguard
      - run: apiguard diff main-openapi.yaml pr-openapi.yaml --format json --fail-on error
```

## Comparison

| Feature | ApiGuard | openapi-diff | Spectral |
|---------|----------|-------------|----------|
| Native Python | ✅ | ❌ (Java) | ✅ (JS) |
| Breaking change detection | ✅ Full | ✅ | ❌ (linting only) |
| Severity levels | ✅ 6 levels | ✅ 3 levels | ❌ |
| SARIF output | ✅ Premium | ❌ | ❌ |
| $ref resolution | ✅ Local | ✅ Full | ✅ |
| CI exit codes | ✅ | ✅ | ✅ |
| Install size | ~2MB | ~50MB+ | ~10MB |

## Premium

Upgrade to Premium ($9 lifetime) for:

- **SARIF output** — GitHub Advanced Security integration
- **CI annotations** — Inline PR comments on breaking changes
- **Custom rules** — Define your own breaking change policies
- **Team dashboards** — Track API stability over time
- **Priority support**

[Get Premium — $9 Lifetime](https://kryptorious.gumroad.com/l/jbvet)

## Requirements

- Python 3.9+
- Handles OpenAPI 3.0 and 3.1 specs
- Supports JSON and YAML input

## License

MIT — free for personal and commercial use. Premium features require a license.

Built by [Kryptorious Quantum Biosciences](https://kryptorious.gumroad.com).


---

**Part of the Kryptorious developer-tools suite.** Get the full bundle with DevFlow Premium (multi-env CI, approval gates, infra-as-code): 👉 https://codegero.github.io/store/