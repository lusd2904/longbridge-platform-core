from __future__ import annotations

from typing import Dict, List

import pytest
from fastapi import HTTPException

from apps.runtime_shared import auth
from core.platform.PlatformAccessService import PlatformAccessService


@pytest.fixture(autouse=True)
def clear_bootstrap_cache() -> None:
    PlatformAccessService.invalidate_bootstrap_cache()
    yield
    PlatformAccessService.invalidate_bootstrap_cache()


def _payload(user_id: int, username: str = "demo", status: str = "active") -> Dict[str, object]:
    return {
        "user": {
            "id": user_id,
            "username": username,
            "nickname": username,
            "email": f"{username}@example.com",
            "phone": "",
            "avatar": None,
            "role": "user",
            "roleCode": "user",
            "preferredSubsystemCode": "workspace",
            "status": status,
        },
        "access": {"roleCode": "user"},
        "menus": [{"code": "dashboard", "path": "/dashboard"}],
        "subsystems": [{"code": "workspace", "path": "/dashboard"}],
        "navigation": {"homePath": "/dashboard", "preferredSubsystemCode": "workspace"},
    }


def _record(user_id: int, username: str = "demo", status: str = "active") -> Dict[str, object]:
    return {
        "id": user_id,
        "username": username,
        "nickname": username,
        "email": f"{username}@example.com",
        "phone": "",
        "avatar": None,
        "role": "user",
        "status": status,
        "last_login_time": None,
        "created_at": None,
    }


def test_build_user_bootstrap_bundle_hits_cache_without_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[int] = []

    monkeypatch.setattr(PlatformAccessService, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(PlatformAccessService, "_bootstrap_cache_now", classmethod(lambda cls: 100.0))

    def fake_uncached(cls, user_id: int):
        calls.append(user_id)
        return _payload(user_id, username=f"user-{len(calls)}"), _record(user_id, username=f"user-{len(calls)}")

    monkeypatch.setattr(
        PlatformAccessService,
        "_build_user_bootstrap_bundle_uncached",
        classmethod(fake_uncached),
    )

    first_payload, first_record = PlatformAccessService.build_user_bootstrap_bundle(7)
    second_payload, second_record = PlatformAccessService.build_user_bootstrap_bundle(7)

    assert calls == [7]
    assert first_payload == second_payload
    assert first_record == second_record
    assert second_payload["user"]["username"] == "user-1"


def test_invalidate_bootstrap_cache_forces_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[int] = []

    monkeypatch.setattr(PlatformAccessService, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(PlatformAccessService, "_bootstrap_cache_now", classmethod(lambda cls: 100.0))

    def fake_uncached(cls, user_id: int):
        calls.append(user_id)
        return _payload(user_id, username=f"user-{len(calls)}"), _record(user_id, username=f"user-{len(calls)}")

    monkeypatch.setattr(
        PlatformAccessService,
        "_build_user_bootstrap_bundle_uncached",
        classmethod(fake_uncached),
    )

    first_payload, _ = PlatformAccessService.build_user_bootstrap_bundle(8)
    PlatformAccessService.invalidate_bootstrap_cache(8)
    second_payload, _ = PlatformAccessService.build_user_bootstrap_bundle(8)

    assert calls == [8, 8]
    assert first_payload["user"]["username"] == "user-1"
    assert second_payload["user"]["username"] == "user-2"


def test_bootstrap_cache_ttl_expiry_forces_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[int] = []
    now_values = iter([100.0, 100.0, 116.0, 116.0])

    monkeypatch.setattr(PlatformAccessService, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(PlatformAccessService, "_bootstrap_cache_now", classmethod(lambda cls: next(now_values)))

    def fake_uncached(cls, user_id: int):
        calls.append(user_id)
        return _payload(user_id, status="active" if len(calls) == 1 else "disabled"), _record(
            user_id,
            status="active" if len(calls) == 1 else "disabled",
        )

    monkeypatch.setattr(
        PlatformAccessService,
        "_build_user_bootstrap_bundle_uncached",
        classmethod(fake_uncached),
    )

    first_payload, _ = PlatformAccessService.build_user_bootstrap_bundle(9)
    second_payload, _ = PlatformAccessService.build_user_bootstrap_bundle(9)

    assert calls == [9, 9]
    assert first_payload["user"]["status"] == "active"
    assert second_payload["user"]["status"] == "disabled"


def test_build_user_bootstrap_bundle_returns_deep_copies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PlatformAccessService, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(PlatformAccessService, "_bootstrap_cache_now", classmethod(lambda cls: 100.0))
    monkeypatch.setattr(
        PlatformAccessService,
        "_build_user_bootstrap_bundle_uncached",
        classmethod(lambda cls, user_id: (_payload(user_id), _record(user_id))),
    )

    first_payload, first_record = PlatformAccessService.build_user_bootstrap_bundle(10)
    first_payload["user"]["username"] = "mutated"
    first_payload["menus"].append({"code": "other", "path": "/other"})
    first_record["username"] = "mutated"

    second_payload, second_record = PlatformAccessService.build_user_bootstrap_bundle(10)

    assert second_payload["user"]["username"] == "demo"
    assert second_record["username"] == "demo"
    assert [item["code"] for item in second_payload["menus"]] == ["dashboard"]


def test_build_bootstrap_payload_reuses_bundle_record_without_extra_user_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.PlatformAccessService, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(
        auth.PlatformAccessService,
        "build_user_bootstrap_bundle",
        classmethod(lambda cls, user_id, use_cache=True: (_payload(user_id, username="bundle-user"), _record(user_id, username="bundle-user"))),
    )
    monkeypatch.setattr(
        auth.DbUtil,
        "fetch_one",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected extra user query")),
    )

    payload = auth.build_bootstrap_payload(12)

    assert payload["user"]["username"] == "bundle-user"
    assert payload["homePath"] == "/dashboard"


def test_build_bootstrap_payload_raises_for_missing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.PlatformAccessService, "ensure_schema", classmethod(lambda cls: None))
    monkeypatch.setattr(
        auth.PlatformAccessService,
        "build_user_bootstrap_bundle",
        classmethod(lambda cls, user_id, use_cache=True: ({}, {})),
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.build_bootstrap_payload(404)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "用户不存在"
