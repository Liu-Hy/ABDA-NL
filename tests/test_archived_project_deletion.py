"""Permanent private deletion preserves snapshots, ownership, and credit history."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models import (
    CreditEligibilityMarker, EmergencyUsageReservation, Identity, LLMUsageEvent,
    NamedCreditEntitlement, Project, ScenarioSubmission, ShareLink, TrialGrant,
    TrialProgram, UsageReservation, User, utc_now,
)
from app.db.session import get_session_factory
from app.services import projects as service
from app.services.trials import activate_trial, reserve_trial_credit, settle_trial_credit
from test_scenario_submissions import (
    ADMIN, PICNIC, client as curation_client, decide, login, project, submit,
)

client = curation_client
DELETE_PATH = "/api/projects/archived/delete"


def archive(client, saved):
    response = client.delete(f"/api/projects/{saved['id']}?expected_version={saved['version']}")
    assert response.status_code == 204, response.text
    return next(item for item in client.get("/api/projects?archived=true").json()["projects"]
                if item["id"] == saved["id"])


def delete(client, saved, *, single=False, **kwargs):
    if single:
        item = saved[0]
        return client.delete(
            f"/api/projects/{item['id']}/permanent?expected_version={item['version']}", **kwargs,
        )
    return client.post(DELETE_PATH, json={
        "projects": [{"id": item["id"], "expected_version": item["version"]} for item in saved],
    }, **kwargs)


def rows(session, model):
    return [dict(row) for row in session.execute(select(model.__table__)).mappings()]


@pytest.mark.parametrize("single", [False, True])
def test_deletion_removes_only_archived_private_copy_and_old_bearer_links(client, single):
    login(client)
    saved = project(client)
    share = client.post(f"/api/projects/{saved['id']}/shares", json={}).json()
    archived = archive(client, saved)
    active = project(client)
    active_before = client.get(f"/api/projects/{active['id']}").json()
    response = delete(client, [archived], single=single)
    assert response.status_code == (204 if single else 200), response.text
    if not single:
        assert response.json() == {"deleted_ids": [saved["id"]], "deleted_count": 1}
    assert client.get("/api/projects?archived=true").json()["projects"] == []
    assert client.get(f"/api/projects/{active['id']}").json() == active_before
    assert client.post(f"/api/projects/{saved['id']}/restore", json={"expected_version": 2}).status_code == 404
    assert delete(client, [archived], single=single).status_code == 404
    token = share["url"].split("#share=", 1)[1]
    assert client.post("/api/shares/resolve", json={"token": token}).status_code == 404
    with get_session_factory()() as session:
        assert session.get(Project, saved["id"]) is None
        assert session.get(ShareLink, share["id"]) is None


def test_delete_preserves_submitted_and_published_snapshots_and_account_ledgers(client):
    owner_id = login(client)["user"]["id"]
    pending_project, public_project = project(client), project(client)
    pending = submit(client, pending_project).json()
    public = submit(client, public_project).json()
    login(client, ADMIN)
    public = decide(client, public, "approve", note="Approved teaching example").json()
    public_before = client.get(f"/scenarios/{public['public_scenario_id']}").json()
    login(client)
    archived = [archive(client, saved) for saved in (pending_project, public_project)]
    tables = (User, Identity, TrialGrant, TrialProgram, CreditEligibilityMarker,
              NamedCreditEntitlement, UsageReservation, EmergencyUsageReservation, LLMUsageEvent)
    with get_session_factory()() as session:
        activate_trial(session, session.get(User, owner_id))
        reservation = reserve_trial_credit(session, owner_id, amount_microusd=200,
                      provider="test", model="test", request_kind="chat")
        reservation_id = reservation.id
        assert session.get(TrialGrant, owner_id).reserved_microusd == 200
        assert session.scalar(select(CreditEligibilityMarker).where(
            CreditEligibilityMarker.user_id == owner_id,
        )) is not None
        session.add(LLMUsageEvent(user_id=owner_id, request_id="synthetic-delete-test",
                    provider="test", route="test", model="test", billing_source="byok",
                    request_kind="chat", status="succeeded", cost_microusd=125))
        session.commit()
        account_before = {table.__tablename__: rows(session, table) for table in tables}
        snapshots_before = rows(session, ScenarioSubmission)
    response = delete(client, archived)
    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 2
    with get_session_factory()() as session:
        assert {table.__tablename__: rows(session, table) for table in tables} == account_before
        assert rows(session, ScenarioSubmission) == [
            {**row, "project_id": None} for row in snapshots_before
        ]
        balance = settle_trial_credit(session, reservation_id, actual_microusd=50)
        assert (balance.reserved_microusd, balance.spent_microusd) == (0, 50)
    assert client.get(f"/api/scenario-submissions/{pending['id']}").json()["status"] == "pending"
    assert client.get(f"/scenarios/{public['public_scenario_id']}").json() == public_before
    login(client, ADMIN)
    # Detaching a private project also leaves ordinary review and withdrawal usable.
    assert decide(client, pending, "approve").status_code == 200
    assert decide(client, public, "unpublish", note="Curator removal").status_code == 200


@pytest.mark.parametrize("failure", ["foreign", "missing", "active", "version"])
def test_invalid_target_rolls_back_the_entire_selection(client, failure):
    login(client, "other@example.org")
    foreign = archive(client, project(client))
    login(client)
    first = project(client)
    share = client.post(f"/api/projects/{first['id']}/shares", json={}).json()
    first = archive(client, first)
    second = archive(client, project(client))
    active = project(client)
    bad = {"foreign": foreign, "missing": {"id": str(uuid4()), "version": 2},
           "active": active, "version": {**second, "version": 1}}[failure]
    response = delete(client, [first, bad, second] if failure != "version" else [first, bad])
    assert response.status_code == (404 if failure in {"foreign", "missing"} else 409), response.text
    with get_session_factory()() as session:
        assert session.get(Project, first["id"]).version == 2
        assert session.get(Project, second["id"]).version == 2
        assert session.get(Project, active["id"]).archived_at is None
        assert session.get(Project, foreign["id"]).version == 2
        assert session.get(ShareLink, share["id"]).revoked_at is None


def test_delete_all_uses_confirmed_versions_and_does_not_include_a_later_archive(client):
    login(client)
    confirmed = [archive(client, project(client)) for _ in range(2)]
    later = archive(client, project(client))
    result = delete(client, confirmed)
    assert result.status_code == 200, result.text
    assert result.json()["deleted_ids"] == [item["id"] for item in confirmed]
    remaining = client.get("/api/projects?archived=true").json()["projects"]
    assert [item["id"] for item in remaining] == [later["id"]]


def test_restore_then_archive_cannot_reuse_a_previous_deletion_confirmation(client):
    login(client)
    old = archive(client, project(client))
    restored = client.post(f"/api/projects/{old['id']}/restore", json={"expected_version": 2}).json()
    assert delete(client, [old]).status_code == 409
    current = archive(client, restored)
    assert current["version"] == 4
    assert delete(client, [old]).status_code == 409
    assert delete(client, [current]).status_code == 200


@pytest.mark.parametrize("change", [{"status": "suspended"}, {"email_verified": False}])
def test_deletion_rechecks_a_stale_owner_under_the_account_lock(client, change):
    owner_id = login(client)["user"]["id"]
    saved = archive(client, project(client))
    with get_session_factory()() as stale, get_session_factory()() as writer:
        owner = stale.get(User, owner_id)
        current = writer.get(User, owner_id)
        for key, value in change.items():
            setattr(current, key, value)
        writer.commit()
        with pytest.raises(service.ProjectNotFoundError):
            service.delete_archived_projects(stale, owner, targets=[(saved["id"], 2)])
    with get_session_factory()() as session:
        assert session.get(Project, saved["id"]).version == 2


@pytest.mark.parametrize("single", [False, True])
def test_deletion_requires_authentication_same_origin_and_existing_mutation_limit(client, single):
    login(client)
    archived = archive(client, project(client))
    assert delete(client, [archived], single=single, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 200
    assert delete(client, [archived], single=single).status_code == 401
    login(client)
    from app.api import account_routes
    from fastapi import HTTPException

    def exhausted(_request, _session, _settings, _user):
        raise HTTPException(status_code=429, detail="rate limited")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(account_routes, "_limit_user_mutation", exhausted)
        assert delete(client, [archived], single=single).status_code == 429
    with get_session_factory()() as session:
        assert session.get(Project, archived["id"]).version == 2


def test_deletion_rejects_unbounded_or_ambiguous_targets_without_changes(client):
    login(client)
    saved = archive(client, project(client))
    target = {"id": saved["id"], "expected_version": 2}
    invalid = [{}, {"all": True}, {"projects": []}, {"projects": [target, target]}]
    invalid.extend({"projects": [{**target, "expected_version": value}]} for value in (0, -1, True, "2"))
    invalid.extend([
        {"projects": [{"id": saved["id"]}]},
        {"projects": [{**target, "id": "x" * 37}]},
        {"projects": [target], "all": True},
        {"projects": [{"id": str(uuid4()), "expected_version": 2} for _ in range(501)]},
    ])
    for payload in invalid:
        assert client.post(DELETE_PATH, json=payload).status_code == 422
    assert client.delete(f"/api/projects/{saved['id']}/permanent?expected_version=0").status_code == 422
    with get_session_factory()() as session:
        assert session.get(Project, saved["id"]).version == 2


def test_delete_all_accepts_the_full_account_limit_and_frees_storage_capacity(client):
    owner_id = login(client)["user"]["id"]
    count = service.MAX_TOTAL_PROJECTS
    assert count == 500
    with get_session_factory()() as session:
        session.add_all(Project(owner_user_id=owner_id, name=f"Archived {index}",
                        scenario_json=PICNIC, archived_at=utc_now(), version=2) for index in range(count))
        session.commit()
    archived = client.get("/api/projects?archived=true").json()["projects"]
    assert len(archived) == count
    response = client.post("/api/projects/import", json={"name": "Over capacity", "scenario": PICNIC})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "project_limit"
    deleted = delete(client, archived)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_count"] == count
    assert client.get("/api/projects?archived=true").json()["projects"] == []
    assert project(client)["name"]


def test_sqlite_delete_and_restore_cannot_both_succeed(client):
    owner_id = login(client)["user"]["id"]
    first, second = [archive(client, project(client)) for _ in range(2)]
    barrier = Barrier(2)

    def operate(action):
        with get_session_factory()() as session:
            owner = session.get(User, owner_id)
            barrier.wait(timeout=5)
            try:
                if action == "delete":
                    service.delete_archived_projects(session, owner, targets=[(first["id"], 2), (second["id"], 2)])
                else:
                    service.restore_project(session, owner, first["id"], expected_version=2)
                return action
            except (service.ProjectNotFoundError, service.ProjectVersionConflictError):
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(operate, ["delete", "restore"]))
    assert results in (["delete", "conflict"], ["conflict", "restore"])
    with get_session_factory()() as session:
        if "delete" in results:
            assert session.scalar(select(func.count(Project.id)).where(Project.owner_user_id == owner_id)) == 0
        else:
            assert session.get(Project, first["id"]).archived_at is None
            assert session.get(Project, second["id"]).version == 2
