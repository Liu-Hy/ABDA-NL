from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "codeql.yml"
CODEQL_SHA = "cdf488f595d80d6e07e03d4674febd5ab45fa938"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


def test_codeql_workflow_is_python_only_pinned_and_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert f"actions/checkout@{CHECKOUT_SHA}" in text
    assert text.count("github/codeql-action/") == 2
    assert text.count(f"@{CODEQL_SHA}") == 2
    assert "languages: python" in text
    assert "queries: security-extended" in text
    assert "id: analyze" in text
    assert "Require a clean security scan" in text
    assert 'root.rglob("*.sarif")' in text
    assert "CodeQL reported {findings} security finding(s)" in text
    assert "security-events: write" in text
    assert "contents: write" not in text
    assert "packages: write" not in text
    assert "id-token: write" not in text
    assert "pull-requests: write" not in text
    assert "branches:\n      - development" in text
    assert "schedule:" not in text
