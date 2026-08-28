"""Static browser-shell invariants that do not require a JavaScript runtime."""
from __future__ import annotations

from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path


STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"


class _HTMLInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.label_targets: list[str] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.attributes_by_id: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.append(element_id)
            self.attributes_by_id[element_id] = values
        if tag == "label" and values.get("for"):
            self.label_targets.append(values["for"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.stylesheets.append(values["href"])


def _inventory() -> _HTMLInventory:
    parser = _HTMLInventory()
    parser.feed((STATIC_ROOT / "index.html").read_text(encoding="utf-8"))
    return parser


def test_frontend_ids_labels_and_assets_are_self_contained():
    inventory = _inventory()
    duplicates = [value for value, count in Counter(inventory.ids).items() if count > 1]
    assert duplicates == []
    assert set(inventory.label_targets) <= set(inventory.ids)
    assert inventory.scripts[-2:] == ["app.js", "workspace.js"]
    assert all("://" not in source for source in inventory.scripts)
    assert all("://" not in source for source in inventory.stylesheets)


def test_workspace_exposes_accessible_core_controls():
    inventory = _inventory()
    required = {
        "workspace-btn",
        "save-btn",
        "modal-workspace",
        "dev-login-email",
        "trial-activate-btn",
        "project-create-form",
        "funded-profile-select",
        "byok-api-key",
        "mcp-token-form",
        "mcp-secret-value",
    }
    assert required <= set(inventory.ids)
    facts = inventory.attributes_by_id["facts-list"]
    assert facts["tabindex"] == "0"
    assert facts["aria-label"]


def test_byok_key_has_no_browser_persistence_code():
    source = (STATIC_ROOT / "workspace.js").read_text(encoding="utf-8")
    for persistence_api in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
        assert persistence_api not in source
    assert "api_key: state.llmAccess.apiKey" in source
    assert "state.llmAccess.apiKey = ''" in source


def test_oidc_login_does_not_copy_share_fragments_into_server_urls():
    source = (STATIC_ROOT / "workspace.js").read_text(encoding="utf-8")
    assert "const next = window.location.pathname;" in source
    assert "window.location.pathname}${window.location.hash" not in source
    assert "oidcLink.target = '_blank'" in source
    assert "refreshExternalOIDCLogin" in source


def test_logout_uses_same_origin_post_before_oidc_session_logout():
    inventory = _inventory()
    logout_form = inventory.attributes_by_id["logout-form"]
    assert logout_form["method"] == "post"
    assert logout_form["action"] == "/auth/logout"
    source = (STATIC_ROOT / "workspace.js").read_text(encoding="utf-8")
    assert "byId('logout-form')?.addEventListener('submit', handleLogout)" in source
    assert "state.authSession.auth_mode === 'oidc'" in source


def test_public_policy_pages_are_linked_and_script_free():
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    for name, heading in (
        ("privacy.html", "Privacy notice"),
        ("terms.html", "Terms of use"),
    ):
        assert f'href="/{name}"' in index
        source = (STATIC_ROOT / name).read_text(encoding="utf-8")
        assert f"<h1>{heading}</h1>" in source
        assert "<script" not in source
        assert 'href="/"' in source

    privacy = (STATIC_ROOT / "privacy.html").read_text(encoding="utf-8")
    terms = (STATIC_ROOT / "terms.html").read_text(encoding="utf-8")
    assert "retained for up to 30 days" in privacy
    assert "retained for 7 days" in privacy
    assert "complete it within 30 days" in privacy
    assert "not analyzed as research data" in privacy
    assert 'href="mailto:privacy@abda-nl.org"' in privacy
    assert 'href="mailto:support@abda-nl.org"' in terms


def test_vendored_browser_assets_match_recorded_provenance():
    vendor_root = STATIC_ROOT / "vendor"
    manifest = json.loads((vendor_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assets = manifest["assets"]
    assert set(assets) == {"dagre.min.js", "marked.min.js", "purify.min.js"}
    assert assets["dagre.min.js"]["version"] == "0.8.5"
    assert assets["marked.min.js"]["version"] == "18.0.7"
    assert assets["purify.min.js"]["version"] == "3.4.13"

    for filename, metadata in assets.items():
        payload = (vendor_root / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == metadata["sha256"]
        assert metadata["version"].encode() in payload
        assert metadata["source"].startswith("https://")
        assert metadata["source_integrity"].startswith(("sha256:", "sha512-"))
        for license_file in metadata["license_files"]:
            assert (vendor_root / license_file).stat().st_size > 500


def test_assistant_markdown_uses_a_restricted_fragment_sink():
    source = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert "RETURN_DOM_FRAGMENT: true" in source
    assert "bubble.append(fragment)" in source
    assert "container.innerHTML = parts.join" not in source
    assert "function escapeAttr(s) {\n  return escapeHtml(s);\n}" in source
    allowed_tags = source.split("const CHAT_MARKDOWN_ALLOWED_TAGS", 1)[1].split(
        "]);", 1
    )[0]
    for active_tag in ("script", "style", "svg", "math", "iframe", "img", "form"):
        assert f"'{active_tag}'" not in allowed_tags
