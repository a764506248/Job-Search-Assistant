import asyncio

from fastapi.testclient import TestClient

from job_search_assistant.automation.browser_protocol import (
    BrowserConnectionHub,
    BrowserProtocolError,
)
from job_search_assistant.main import create_app


def test_pairing_code_is_one_time_and_token_authenticates() -> None:
    hub = BrowserConnectionHub()
    pairing = hub.create_pairing()

    token = hub.exchange_pairing_code(pairing["code"])

    assert hub.authenticate(token) is True
    assert hub.authenticate("wrong-token") is False


def test_pairing_token_survives_service_restart(tmp_path) -> None:
    token_path = tmp_path / "browser-token.sha256"
    first_hub = BrowserConnectionHub(token_path)
    pairing = first_hub.create_pairing()
    token = first_hub.exchange_pairing_code(pairing["code"])

    restarted_hub = BrowserConnectionHub(token_path)

    assert restarted_hub.authenticate(token) is True
    assert token_path.stat().st_mode & 0o777 == 0o600


def test_previous_single_user_token_format_is_migrated(tmp_path) -> None:
    token_path = tmp_path / "browser-token.sha256"
    first_hub = BrowserConnectionHub(token_path)
    pairing = first_hub.create_pairing(7)
    token = first_hub.exchange_pairing_code(pairing["code"])
    token_hash = first_hub._hash(token)
    token_path.write_text(
        f'{{"tokenHash":"{token_hash}","userId":7}}', encoding="utf-8"
    )

    migrated_hub = BrowserConnectionHub(token_path)

    assert migrated_hub.authenticate(token) is True
    assert migrated_hub.resolve_user(token) == 7


def test_extension_websocket_pairs_and_becomes_ready(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    pairing = client.post("/v1/browser/pairing").json()

    with client.websocket_connect("/v1/browser/ws") as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "pairingCode": pairing["code"],
                "protocolVersion": "1.0",
                "extensionVersion": "test",
            }
        )
        paired = websocket.receive_json()
        assert paired["type"] == "paired"
        assert websocket.receive_json()["type"] == "ready"
        assert client.get("/v1/browser/status").json()["connected"] is True


def test_hub_dispatches_allowlisted_action_and_correlates_response() -> None:
    hub = BrowserConnectionHub()

    class FakeSocket:
        async def send_json(self, envelope) -> None:
            hub.resolve(
                {
                    "requestId": envelope["requestId"],
                    "status": "success",
                    "evidence": {"extensionAlive": True},
                }
            )

    async def exercise() -> None:
        socket = FakeSocket()
        hub.attach(socket, "test", 1)  # type: ignore[arg-type]
        result = await hub.dispatch(run_id=1, user_id=1, action="ping", payload={})
        assert result["status"] == "success"
        assert result["evidence"]["extensionAlive"] is True

    asyncio.run(exercise())


def test_hub_rejects_dispatch_for_another_user() -> None:
    hub = BrowserConnectionHub()

    class FakeSocket:
        async def send_json(self, envelope) -> None:
            raise AssertionError("cross-user action must not reach the extension")

    async def exercise() -> None:
        hub.attach(FakeSocket(), "test", 1)  # type: ignore[arg-type]
        try:
            await hub.dispatch(run_id=2, user_id=2, action="send_greeting", payload={})
        except BrowserProtocolError as error:
            assert "not connected for this user" in str(error)
        else:  # pragma: no cover - explicit failure message is clearer than pytest helpers here
            raise AssertionError("cross-user dispatch was accepted")

    asyncio.run(exercise())


def test_browser_status_is_visible_only_to_connection_owner() -> None:
    hub = BrowserConnectionHub()

    class FakeSocket:
        pass

    hub.attach(FakeSocket(), "test", 1)  # type: ignore[arg-type]

    assert hub.status(1)["connected"] is True
    assert hub.status(2)["connected"] is False
    assert hub.status(2)["extensionVersion"] is None


def test_stale_socket_disconnect_does_not_detach_new_owner() -> None:
    hub = BrowserConnectionHub()

    class FakeSocket:
        pass

    first = FakeSocket()
    second = FakeSocket()
    hub.attach(first, "first", 1)  # type: ignore[arg-type]
    hub.attach(second, "second", 2)  # type: ignore[arg-type]

    hub.detach(first)  # type: ignore[arg-type]

    assert hub.connected_user_ids() == (2,)
    assert hub.status(1)["connected"] is False
    assert hub.status(2)["connected"] is True
    assert hub.status(2)["extensionVersion"] == "second"


def test_pairing_tokens_and_connections_are_isolated_for_two_users(tmp_path) -> None:
    hub = BrowserConnectionHub(tmp_path / "browser-tokens.json")
    first_pairing = hub.create_pairing(1)
    second_pairing = hub.create_pairing(2)
    first_token = hub.exchange_pairing_code(first_pairing["code"])
    second_token = hub.exchange_pairing_code(second_pairing["code"])

    class FakeSocket:
        def __init__(self, owner_id: int) -> None:
            self.owner_id = owner_id
            self.actions: list[str] = []

        async def send_json(self, envelope) -> None:
            self.actions.append(envelope["action"])
            hub.resolve(
                {"requestId": envelope["requestId"], "status": "success"},
                self.owner_id,
            )

    async def exercise() -> None:
        first = FakeSocket(1)
        second = FakeSocket(2)
        hub.attach(first, "first", 1)  # type: ignore[arg-type]
        hub.attach(second, "second", 2)  # type: ignore[arg-type]

        await asyncio.gather(
            hub.dispatch(run_id=1, user_id=1, action="ping", payload={}),
            hub.dispatch(run_id=2, user_id=2, action="session_status", payload={}),
        )
        assert first.actions == ["ping"]
        assert second.actions == ["session_status"]
        hub.detach(first)  # type: ignore[arg-type]
        assert hub.status(1)["connected"] is False
        assert hub.status(2)["connected"] is True

    assert hub.resolve_user(first_token) == 1
    assert hub.resolve_user(second_token) == 2
    asyncio.run(exercise())

    restarted = BrowserConnectionHub(tmp_path / "browser-tokens.json")
    assert restarted.resolve_user(first_token) == 1
    assert restarted.resolve_user(second_token) == 2
