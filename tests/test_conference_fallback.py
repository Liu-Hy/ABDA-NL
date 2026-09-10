"""Keep the offline presentation capture separate from identity and models."""

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from deploy.capture_conference_fallback import (
    FRAMES, GET_PATHS, ORIGIN, SCENARIO, TOGGLE, allowed_request, capture,
    capture_tool_source, render_gallery, validate_base_url,
)


def test_allowlist_covers_current_bootstrap_without_allowing_arbitrary_assets():
    class Assets(HTMLParser):
        paths: set[str]

        def __init__(self):
            super().__init__()
            self.paths = set()

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            path = attrs.get("src") if tag == "script" else (
                attrs.get("href") if tag == "link" and attrs.get("rel") == "stylesheet" else None
            )
            if path:
                self.paths.add("/" + path.lstrip("/"))

    assets = Assets()
    assets.feed((Path(__file__).resolve().parents[1] / "app/static/index.html").read_text())
    assert assets.paths
    assert GET_PATHS == assets.paths | {"/", "/config", "/scenarios", "/api/auth/session", "/favicon.ico"}
    for base_url in (ORIGIN, "http://127.0.0.1:8765", "http://[::1]:9000"):
        assert all(allowed_request("GET", base_url + path, base_url=base_url) for path in assets.paths)
        assert not allowed_request("GET", base_url + "/unexpected.js", base_url=base_url)


@pytest.mark.parametrize("base_url", [ORIGIN, "http://127.0.0.1:8765", "http://[::1]:9000"])
def test_capture_base_url_is_canonical_and_same_origin(base_url):
    assert validate_base_url(base_url) == base_url
    assert validate_base_url(base_url + "/") == base_url
    assert allowed_request("GET", base_url + "/", base_url=base_url)
    body = json.dumps({"scenario_id": SCENARIO, "diff_ops": [TOGGLE]})
    assert allowed_request("POST", base_url + "/state", body, base_url=base_url)
    assert not allowed_request("GET", "http://127.0.0.1:1234/", base_url=base_url)
    assert not allowed_request("GET", "https://other.example/", base_url=base_url)
    if base_url != ORIGIN:
        assert not allowed_request("GET", ORIGIN + "/", base_url=base_url)


@pytest.mark.parametrize("base_url", [
    "https://other.example", "http://demo.abda-nl.org", ORIGIN + ":443",
    "http://localhost:8765", "http://127.1:8765", "http://2130706433:8765",
    "http://127.0.0.2:8765", "http://192.168.1.1:8765", "https://127.0.0.1:8765",
    "http://127.0.0.1", "http://127.0.0.1:0", "http://127.0.0.1:65536",
    "http://127.0.0.1:08765", "http://user@127.0.0.1:8765",
    "http://127.0.0.1:8765/path", "http://127.0.0.1:8765/?",
    "http://127.0.0.1:8765/#", "http://127.0.0.1:8765/?share=private",
    "http://127.0.0.1:8765/#share=private", " http://127.0.0.1:8765",
    "http://127.0.0.1:8765\n", "http://[::1%25lo]:8765", "file:///tmp/index.html",
])
def test_capture_rejects_noncanonical_or_remote_targets_without_creating_output(tmp_path, base_url):
    output = tmp_path / "capture"
    with pytest.raises(ValueError):
        capture(output, base_url=base_url)
    assert not output.exists()
    assert not allowed_request("GET", base_url + "/", base_url=base_url)


@pytest.mark.parametrize("existing", ["capture", "capture.zip"])
def test_capture_refuses_to_overwrite_output_or_archive(tmp_path, existing):
    occupied = tmp_path / existing
    occupied.write_bytes(b"previous capture")
    with pytest.raises(ValueError, match="nothing is overwritten"):
        capture(tmp_path / "capture")
    assert occupied.read_bytes() == b"previous capture"


@pytest.mark.parametrize("path", ["/", "/app.js", "/scenarios.js", "/api/auth/session", "/config"])
def test_capture_allows_required_anonymous_reads(path):
    assert allowed_request("GET", ORIGIN + path)


@pytest.mark.parametrize("url,method,body", [
    (ORIGIN + "/chat", "POST", "{}"),
    (ORIGIN + "/propose", "POST", "{}"),
    (ORIGIN + "/api/projects", "POST", "{}"),
    (ORIGIN + "/api/mcp/tokens", "GET", None),
    (ORIGIN + "/auth/login", "GET", None),
    (ORIGIN + "/?share=placeholder", "GET", None),
    (ORIGIN + "/#share=placeholder", "GET", None),
    ("https://other.example/", "GET", None),
    (ORIGIN + ":443/", "GET", None),
    (ORIGIN + "/state", "POST", '{"scenario_id":"private","diff_ops":[]}'),
    (ORIGIN + "/state", "POST", "not-json"),
    (ORIGIN + "/scenarios", "POST", "{}"),
])
def test_capture_rejects_unrelated_network_operations(url, method, body):
    assert not allowed_request(method, url, body)


@pytest.mark.parametrize("path,method,body", [
    ("/chat", "POST", "{}"), ("/propose", "POST", "{}"),
    ("/api/projects", "GET", None), ("/api/projects", "POST", "{}"),
    ("/api/mcp/tokens", "POST", "{}"), ("/api/auth/dev-login", "POST", "{}"),
    ("/api/scenarios/export", "POST", "{}"), ("/.env", "GET", None),
    ("/state", "GET", None), ("/state", "POST", '{"scenario_id":"private","diff_ops":[]}'),
    ("/state", "POST", '{"scenario_id":"popov_v_hayashi","diff_ops":[],"project_id":"private"}'),
    ("/?", "GET", None), ("/#", "GET", None),
])
def test_loopback_capture_preserves_identity_model_and_private_data_guards(path, method, body):
    base_url = "http://127.0.0.1:8765"
    assert not allowed_request(method, base_url + path, body, base_url=base_url)


def test_capture_only_computes_the_rehearsed_public_what_if():
    for operations in ([], [TOGGLE]):
        body = json.dumps({"scenario_id": SCENARIO, "diff_ops": operations})
        assert allowed_request("POST", ORIGIN + "/state", body)
    assert not allowed_request("POST", ORIGIN + "/state", json.dumps({
        "scenario_id": SCENARIO, "diff_ops": [TOGGLE], "llm": {"profile": "balanced"},
    }))


def test_gallery_is_local_script_free_and_clearly_labeled():
    rendered = render_gallery("2026-09-06 <capture>")
    assert "2026-09-06 &lt;capture&gt;" in rendered
    assert "Offline screenshot backup, not a live interactive session." in rendered
    assert "<script" not in rendered
    assert "default-src 'none'" in rendered
    assert rendered.count("<section ") == len(FRAMES) == 6
    for slug, _, _ in FRAMES:
        assert f'src="{slug}.png"' in rendered
        assert f'id="{slug}"' in rendered


def test_local_gallery_does_not_claim_a_hosted_release():
    rendered = render_gallery("2026-09-10", "http://127.0.0.1:8765")
    assert "http://127.0.0.1:8765" in rendered
    assert "Captured from a local candidate." in rendered
    assert "does not show that the public service was updated" in rendered
    assert "Captured from the public service." not in rendered
    assert "Conclusion graph" in rendered and "ASPIC- text" in rendered


def test_tool_provenance_does_not_infer_a_served_revision(monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("deploy.capture_conference_fallback.subprocess.run", no_git)
    receipt = capture_tool_source()
    assert receipt["capture_tool_revision"] is None
    assert receipt["capture_tool_worktree_dirty"] is None
    assert len(receipt["capture_tool_sha256"]) == 64
    assert "served_revision" not in receipt
