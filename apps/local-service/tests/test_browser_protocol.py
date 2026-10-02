import asyncio

from fastapi.testclient import TestClient

from job_search_assistant.automation.browser_protocol import BrowserConnectionHub
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
        hub.attach(socket, "test")  # type: ignore[arg-type]
        result = await hub.dispatch(run_id=1, action="ping", payload={})
        assert result["status"] == "success"
        assert result["evidence"]["extensionAlive"] is True

    asyncio.run(exercise())
