"""Explicit, validated Azure boundaries shared by revision preparation tools."""
from __future__ import annotations

from dataclasses import dataclass, fields
import json
from pathlib import Path
import re
from uuid import UUID


class TargetError(RuntimeError):
    """Fixed diagnostic that contains no credentials or raw cloud response."""


@dataclass(frozen=True)
class RolloutTarget:
    subscription: str
    tenant: str
    operator: str
    resource_group: str
    app: str
    job: str
    postgres: str
    database: str
    app_login: str

    @property
    def arm_root(self) -> str:
        return (f"https://management.azure.com/subscriptions/{self.subscription}"
                f"/resourceGroups/{self.resource_group}")

    def require_identity(self, identity: dict) -> None:
        observed = (identity.get("id"), identity.get("tenantId"),
                    identity.get("user", {}).get("name", "").lower(), identity.get("state"))
        if observed != (self.subscription, self.tenant, self.operator.lower(), "Enabled"):
            raise TargetError("the Azure identity differs from the explicit target configuration")

    def require_resource(self, resource: dict, kind: str, name: str) -> None:
        expected = f"{self.arm_root.removeprefix('https://management.azure.com')}/providers/{kind}/{name}"
        if resource.get("name") != name or str(resource.get("id", "")).lower() != expected.lower():
            raise TargetError("an Azure resource differs from the exact target configuration")


def load_target(path: Path) -> RolloutTarget:
    try:
        raw = json.loads(path.read_text())
        names = {item.name for item in fields(RolloutTarget)}
        if not isinstance(raw, dict) or set(raw) != names or not all(
            isinstance(value, str) and value and value == value.strip() for value in raw.values()
        ):
            raise ValueError
        for key in ("subscription", "tenant"):
            if str(UUID(raw[key])) != raw[key].lower():
                raise ValueError
        if not re.fullmatch(r"[^\s@]+@[^\s@]+", raw["operator"]):
            raise ValueError
        for key in ("resource_group", "app", "job", "postgres"):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,89}", raw[key]):
                raise ValueError
        for key in ("database", "app_login"):
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", raw[key]):
                raise ValueError
        if raw["app_login"] in {"postgres", "azure_pg_admin", "azuresu", "public"}:
            raise ValueError
        return RolloutTarget(**raw)
    except Exception as exc:
        raise TargetError("provide a complete, valid rollout target JSON file") from exc
