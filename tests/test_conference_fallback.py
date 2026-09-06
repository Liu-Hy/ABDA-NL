"""Keep the offline presentation capture separate from identity and models."""

import json

import pytest

from deploy.capture_conference_fallback import FRAMES, ORIGIN, SCENARIO, TOGGLE, allowed_request, render_gallery


@pytest.mark.parametrize("path", ["/", "/app.js", "/api/auth/session", "/config"])
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
