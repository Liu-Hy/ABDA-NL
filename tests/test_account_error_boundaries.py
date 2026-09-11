"""Account HTTP routes disclose typed user errors, never arbitrary ValueError text."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/api/auth/dev/login", json={
            "email": "account-error-boundary@example.edu",
        }).status_code == 200
        yield client


@pytest.mark.parametrize("module, function, path, payload", [
    ("app.api.account_routes", "create_project", "/api/projects",
     {"name": "Private project", "source_scenario_id": "fire_prevention"}),
    ("app.api.account_routes", "parse_scenario_file", "/api/projects/import/preview",
     {"text": "title: A valid-looking scenario"}),
    ("app.scenario.source_upload", "preview_source", "/api/projects/materials/source-preview",
     {"filename": "source.txt", "data_base64": "dGV4dA=="}),
])
def test_account_value_errors_use_generic_server_error(
    client, monkeypatch, caplog, module, function, path, payload,
):
    def unexpected(*_args, **_kwargs):
        raise ValueError("private-provider-key-and-user-content")

    monkeypatch.setattr(importlib.import_module(module), function, unexpected)
    response = client.post(path, json=payload)
    assert response.status_code == 500
    assert "internal_error" in response.text
    assert "private-provider-key" not in response.text
    assert "private-provider-key" not in caplog.text


def test_typed_project_and_material_input_errors_remain_useful(client):
    project = client.post("/api/projects", json={
        "name": "   ", "source_scenario_id": "fire_prevention",
    })
    assert project.status_code == 400
    assert project.json()["detail"]["message"] == "scenario name cannot be empty"
    material = client.post("/api/projects/materials/source-preview", json={
        "filename": "source.txt", "data_base64": "%%invalid%%",
    })
    assert material.status_code == 400
    assert "could not be decoded" in material.json()["detail"]["message"]
