"""Private restoration and consented snapshot metadata at the HTTP boundary."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.db.models import Project, ScenarioSubmission, ShareLink, User, utc_now
from app.db.session import get_session_factory
from app.services import projects as project_service
from app.services.privacy_requests import export_privacy_account
from test_scenario_submissions import ADMIN, AUTHOR, PICNIC, client as curation_client, decide, login, project, submit

client = curation_client


def archive(client, saved):
    response = client.delete(f"/api/projects/{saved['id']}?expected_version={saved['version']}")
    assert response.status_code == 204, response.text
    return client.get("/api/projects?archived=true").json()["projects"][0]


def restore(client, saved, **options):
    return client.post(f"/api/projects/{saved['id']}/restore", json={
        "expected_version": saved["version"], **options,
    })


def test_restore_is_owner_scoped_versioned_and_permanently_revokes_old_links(client):
    login(client)
    saved = project(client)
    links = [client.post(f"/api/projects/{saved['id']}/shares", json={}).json() for _ in range(2)]
    archived = archive(client, saved)
    assert archived["version"] == 2 and archived["archived_at"]
    assert archived["active_share_count"] == 0
    assert client.get("/api/projects").json()["projects"] == []
    assert client.get(f"/api/projects/{saved['id']}").status_code == 404
    assert restore(client, archived, expected_version=1).status_code == 409
    login(client, "other@example.org")
    assert client.get("/api/projects?archived=true").json()["projects"] == []
    assert restore(client, archived).status_code == 404
    login(client)
    restored = restore(client, archived)
    assert restored.status_code == 200, restored.text
    assert restored.headers["etag"] == '"3"'
    assert restored.json()["archived_at"] is None
    assert restored.json()["scenario"] == saved["scenario"]
    assert restored.json()["description"] == saved["description"]
    assert restore(client, archived).status_code == 409
    assert client.get("/api/projects?archived=true").json()["projects"] == []
    for link in links:
        token = link["url"].split("#share=", 1)[1]
        assert client.post("/api/shares/resolve", json={"token": token}).status_code == 404
    assert all(item["revoked_at"] for item in client.get(f"/api/projects/{saved['id']}/shares").json()["share_links"])
    new_link = client.post(f"/api/projects/{saved['id']}/shares", json={}).json()
    assert client.post("/api/shares/resolve", json={"token": new_link["url"].split("#share=", 1)[1]}).status_code == 200


def test_restore_checks_active_capacity_before_changing_project_or_shares(client, monkeypatch):
    login(client)
    saved = project(client)
    client.post(f"/api/projects/{saved['id']}/shares", json={})
    archived = archive(client, saved)
    project(client)
    monkeypatch.setattr(project_service, "MAX_ACTIVE_PROJECTS", 1)
    response = restore(client, archived)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "project_limit"
    with get_session_factory()() as session:
        stored = session.get(Project, saved["id"])
        assert stored.archived_at and stored.version == 2
        assert session.scalar(select(ShareLink).where(ShareLink.project_id == saved["id"])).revoked_at is None


def test_restore_does_not_commit_a_historical_project_that_cannot_be_opened(client, monkeypatch):
    login(client)
    saved = project(client)
    client.post(f"/api/projects/{saved['id']}/shares", json={})
    archived = archive(client, saved)

    def unavailable(_scenario, _source):
        raise project_service.ProjectValidationError("Reference content is unavailable.")

    monkeypatch.setattr(project_service, "normalize_project_scenario", unavailable)
    response = restore(client, archived)
    assert response.status_code == 400
    with get_session_factory()() as session:
        stored = session.get(Project, saved["id"])
        assert stored.archived_at and stored.version == 2
        assert session.scalar(select(ShareLink).where(ShareLink.project_id == saved["id"])).revoked_at is None


@pytest.mark.parametrize("change", [{"status": "suspended"}, {"email_verified": False}])
def test_restore_refreshes_active_verified_owner_even_for_stale_service_user(client, change):
    user_id = login(client)["user"]["id"]
    saved = project(client)
    archived = archive(client, saved)
    with get_session_factory()() as stale, get_session_factory()() as writer:
        user = stale.get(User, user_id)
        current = writer.get(User, user_id)
        for key, value in change.items():
            setattr(current, key, value)
        writer.commit()
        with pytest.raises(project_service.ProjectNotFoundError):
            project_service.restore_project(stale, user, saved["id"], expected_version=archived["version"])
    with get_session_factory()() as session:
        assert session.get(Project, saved["id"]).version == 2


def test_simultaneous_restores_cannot_exceed_active_cap(client, monkeypatch):
    user_id = login(client)["user"]["id"]
    first = project(client)
    second = project(client)
    archive(client, first)
    archive(client, second)
    project(client)
    monkeypatch.setattr(project_service, "MAX_ACTIVE_PROJECTS", 2)
    barrier = Barrier(2)

    def restore_one(saved):
        with get_session_factory()() as session:
            user = session.get(User, user_id)
            barrier.wait(timeout=5)
            try:
                project_service.restore_project(session, user, saved["id"], expected_version=2)
                return "restored"
            except project_service.ProjectLimitError:
                return "limited"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(restore_one, [first, second])) == ["limited", "restored"]
    with get_session_factory()() as session:
        assert session.scalar(select(func.count(Project.id)).where(Project.owner_user_id == user_id, Project.archived_at.is_(None))) == 2


def test_restore_requires_same_origin_authentication_and_positive_version(client):
    login(client)
    saved = archive(client, project(client))
    path = f"/api/projects/{saved['id']}/restore"
    assert client.post(path, json={"expected_version": saved["version"]}, headers={"origin": "https://evil.example"}).status_code == 403
    assert restore(client, saved, expected_version=0).status_code == 422
    client.post("/api/auth/logout")
    assert restore(client, saved).status_code == 401


def test_public_metadata_is_consented_immutable_and_separate_from_private_notes(client):
    response = client.post("/api/auth/dev/login", json={"email": AUTHOR, "display_name": "Scenario Author"})
    user_id = response.json()["user"]["id"]
    saved = project(client)
    options = {"public_title": "Public teaching title", "public_summary": "Brief public summary.",
               "author_note": "Private review context", "attribute_author": True}
    response = submit(client, saved, **options)
    assert response.status_code == 201, response.text
    item = response.json()
    assert submit(client, saved, **options).json()["id"] == item["id"]
    assert submit(client, saved, **{**options, "public_summary": "Changed"}).status_code == 409
    assert submit(client, saved, **{**options, "attribute_author": False}).status_code == 409
    detail = client.get(f"/api/scenario-submissions/{item['id']}").json()
    assert detail["scenario"]["title"] == "Public teaching title"
    assert detail["scenario"]["description"] == PICNIC["description"]
    assert detail["author_note"] == "Private review context"
    assert detail["portable_scenario"]["sources"][0]["text"] == PICNIC["sources"][0]["text"]
    with get_session_factory()() as session:
        exported = export_privacy_account(session, AUTHOR)
        record = exported["scenario_submissions"][0]
        assert record["public_summary"] == options["public_summary"]
        assert record["author_note"] == options["author_note"]
        assert record["attribution_name"] == "Scenario Author"
    login(client, ADMIN)
    published = decide(client, item, "approve").json()
    with get_session_factory()() as session:
        session.get(User, user_id).display_name = "Later profile name"
        session.commit()
    login(client)
    updated = client.put(f"/api/projects/{saved['id']}", json={"expected_version": 1, "name": "New private title"}).json()
    row = client.get("/api/projects").json()["projects"][0]
    assert row["version"] == 2 and row["submissions"][0]["project_version"] == 1
    assert row["submissions"][0]["status"] == "published"
    archive(client, updated)
    client.post("/api/auth/logout")
    catalog = client.get("/scenarios").json()["scenarios"]
    public = next(entry for entry in catalog if entry["id"] == published["public_scenario_id"])
    assert public["public_summary"] == "Brief public summary."
    assert public["title"] == "Public teaching title"
    assert public["description"] == PICNIC["description"]
    assert public["attribution_name"] == "Scenario Author" and public["published_at"]
    assert public["published_at"].endswith("+00:00")
    assert "Private review context" not in str(catalog) and AUTHOR not in str(catalog)


@pytest.mark.parametrize("name", [None, "person@example.org", "Author <person@example.org>"])
def test_public_attribution_never_falls_back_to_or_contains_email(client, name):
    client.post("/api/auth/dev/login", json={"email": AUTHOR, "display_name": name})
    saved = project(client)
    assert submit(client, saved, attribute_author=True).status_code == 400
    response = submit(client, saved)
    assert response.status_code == 201 and response.json()["attribution_name"] is None
    assert submit(client, saved, attribute_author="true").status_code == 422


def test_queue_counts_cover_more_than_one_page_and_names_are_admin_only(client):
    owner_id = login(client)["user"]["id"]
    with get_session_factory()() as session:
        session.get(User, owner_id).display_name = "Example contributor"
        for index in range(52):
            session.add(ScenarioSubmission(submitter_id=owner_id, project_version=1,
                title=f"Snapshot {index}", description="", scenario_json=PICNIC,
                status="pending" if index < 51 else "published"))
        session.commit()
    mine = client.get("/api/scenario-submissions").json()
    assert mine["own_count"] == 52 and mine["has_more"] and len(mine["submissions"]) == 50
    assert "counts" not in mine and "submitter_display_name" not in str(mine)
    login(client, "other@example.org")
    assert client.get("/api/scenario-submissions").json()["own_count"] == 0
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    login(client, ADMIN)
    queue = client.get("/api/scenario-submissions?queue=true&status=pending").json()
    assert queue["counts"] == {"pending": 51, "published": 1, "rejected": 0, "withdrawn": 0, "mine": 0}
    assert queue["has_more"] and len(queue["submissions"]) == 50
    assert all(item["submitter_display_name"] == "Example contributor" for item in queue["submissions"])
    client.post("/api/auth/view-mode", json={"normal_user_view": True})
    assert client.get("/api/scenario-submissions?queue=true").status_code == 403
    assert "counts" not in client.get("/api/scenario-submissions").json()


def test_own_unpublish_needs_no_note_but_records_removal_and_other_authors_need_reason(client):
    login(client, ADMIN)
    own = submit(client, project(client), publish=True).json()
    removed = decide(client, own, "unpublish")
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "withdrawn" and removed.json()["version"] == own["version"] + 1
    assert removed.json()["reviewed_at"]
    login(client)
    other = submit(client, project(client)).json()
    login(client, ADMIN)
    published = decide(client, other, "approve").json()
    assert decide(client, published, "unpublish").status_code == 400


def test_project_status_counts_only_usable_links(client):
    login(client)
    saved = project(client)
    one = client.post(f"/api/projects/{saved['id']}/shares", json={}).json()
    client.post(f"/api/projects/{saved['id']}/shares", json={"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    client.delete(f"/api/projects/{saved['id']}/shares/{one['id']}")
    assert client.get("/api/projects").json()["projects"][0]["active_share_count"] == 1
    with get_session_factory()() as session:
        link = session.scalar(select(ShareLink).where(ShareLink.project_id == saved["id"], ShareLink.revoked_at.is_(None)))
        link.expires_at = utc_now() - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/projects").json()["projects"][0]["active_share_count"] == 0
