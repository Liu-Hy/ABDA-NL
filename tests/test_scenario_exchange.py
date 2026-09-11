"""Portable scenario files must remain data-only, bounded, and private."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from app.api.main import app
from app.scenario.exchange import ScenarioFileError, parse_scenario_file


def picnic():
    return {
        "title": "Our picnic",
        "facts": {"sunny": {"description": "The forecast is sunny"}},
        "conclusions": {"outside": {"description": "Hold the picnic outside"}},
        "rules": {"r1": {"type": "defeasible", "premises": ["sunny"], "conclusion": "outside"}},
    }


@pytest.fixture()
def client():
    with TestClient(app) as client:
        yield client


def login(client):
    response = client.post("/api/auth/dev/login", json={"email": f"{uuid4().hex}@example.org"})
    assert response.status_code == 200


@pytest.mark.parametrize("encode", [json.dumps, yaml.safe_dump])
def test_standalone_files_and_bom(encode):
    raw, source, warnings = parse_scenario_file("\ufeff" + encode(picnic()))
    assert raw == picnic()
    assert source is None
    assert not warnings


@pytest.mark.parametrize("text", [
    "", "null", "- a", "title: first\ntitle: second", '{"title":"first","title":"second"}',
    "x: &a [1]\ny: *a", "x: &a [*a]", "x: !!python/object/apply:os.system ['echo unsafe']",
    "1: value", "true: value", "? [a, b]\n: c", "x: " + "[" * 30 + "1" + "]" * 30,
    "[", "a: b\n---\nc: d", "x: " + "a" * 1_000_000,
    '{"format":"unknown","version":1}', '{"format":"abda-nl-scenario","version":true}',
    '{"format":"abda-nl-scenario","version":1,"scenario":[],"source_scenario_id":null}',
])
def test_invalid_or_resource_expanding_files_are_rejected(text):
    with pytest.raises(ScenarioFileError):
        parse_scenario_file(text)


def test_export_has_strict_metadata():
    document = {"format": "abda-nl-scenario", "version": 1, "scenario": picnic()}
    assert parse_scenario_file(json.dumps(document))[0] == picnic()
    for key, value in [("project_id", "private-id"), ("email", "private@example.org")]:
        with pytest.raises(ScenarioFileError, match="unexpected fields"):
            parse_scenario_file(json.dumps({**document, key: value}))
    with pytest.raises(ScenarioFileError, match="identifier"):
        parse_scenario_file(json.dumps({**document, "source_scenario_id": 5}))


def test_raw_corpus_is_explicitly_excluded():
    raw, source, warnings = parse_scenario_file(json.dumps({**picnic(), "corpus": ["../../.env"]}))
    assert raw["corpus"] == []
    assert source is None
    assert "not uploaded or read" in warnings[0]


def test_preview_requires_authentication_and_same_origin(client):
    payload = {"text": json.dumps(picnic())}
    assert client.post("/api/projects/import/preview", json=payload).status_code == 401
    login(client)
    response = client.post("/api/projects/import/preview", json=payload, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_preview_import_private_ownership_and_roundtrip(client):
    login(client)
    before = client.get("/api/projects").json()
    response = client.post("/api/projects/import/preview", json={"text": yaml.safe_dump(picnic())})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    preview = response.json()
    assert client.get("/api/projects").json() == before
    create = client.post("/api/projects/import", json={
        "name": "Picnic copy", "scenario": preview["scenario"], "source_scenario_id": preview["source_scenario_id"],
    })
    assert create.status_code == 201, create.text
    project = create.json()
    assert project["af"]["labels_by_proposition"]["outside"] == "accepted"
    assert project["source_scenario_id"] is None
    export = {"format": "abda-nl-scenario", "version": 1, "scenario": project["scenario"], "source_scenario_id": None}
    reopened = client.post("/api/projects/import/preview", json={"text": json.dumps(export)})
    assert reopened.json()["scenario"] == project["scenario"]
    login(client)
    assert client.get(f'/api/projects/{project["id"]}').status_code == 404
    assert all(item["title"] != "Our picnic" for item in client.get("/scenarios").json()["scenarios"])


@pytest.mark.parametrize("change", [
    lambda raw: raw["rules"]["r1"].update(premises=["missing"]),
    lambda raw: raw["rules"]["r1"].update(type="magic"),
    lambda raw: raw.update(secret="do not store"),
])
def test_invalid_preview_never_creates_a_project(client, change):
    login(client)
    raw = picnic()
    change(raw)
    before = client.get("/api/projects").json()
    response = client.post("/api/projects/import/preview", json={"text": json.dumps(raw)})
    assert response.status_code == 400, response.text
    assert client.get("/api/projects").json() == before


def test_exported_example_corpus_is_checked_not_trusted(client):
    login(client)
    scenario = client.post("/state", json={"scenario_id": "popov_v_hayashi", "diff_ops": []}).json()["scenario"]
    export = {"format": "abda-nl-scenario", "version": 1, "source_scenario_id": "popov_v_hayashi", "scenario": scenario}
    assert client.post("/api/projects/import/preview", json={"text": json.dumps(export)}).status_code == 200
    scenario["corpus"] = ["../../.env"]
    response = client.post("/api/projects/import/preview", json={"text": json.dumps(export)})
    assert response.status_code == 400
    assert "fixed built-in source scenario" in response.json()["detail"]["message"]
