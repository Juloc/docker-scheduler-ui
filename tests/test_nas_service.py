import pytest

from app import nas_service


def test_normalize_mac_accepts_common_formats():
    assert nas_service._normalize_mac("AA:BB:CC:DD:EE:FF") == "AABBCCDDEEFF"
    assert nas_service._normalize_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"


def test_normalize_mac_rejects_invalid_value():
    with pytest.raises(ValueError):
        nas_service._normalize_mac("not-a-mac")


def test_wake_sends_standard_magic_packet(monkeypatch):
    sent = {}

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def setsockopt(self, *args):
            pass

        def settimeout(self, value):
            pass

        def sendto(self, payload, address):
            sent["payload"] = payload
            sent["address"] = address

    monkeypatch.setattr(
        nas_service,
        "current_status",
        lambda profile_id=None: {
            "name": "Storage",
            "host": "nas.local",
            "wol_enabled": True,
            "mac_address": "AA:BB:CC:DD:EE:FF",
        },
    )
    monkeypatch.setattr(nas_service.socket, "socket", lambda *args, **kwargs: FakeSocket())

    message = nas_service.wake(1)

    assert len(sent["payload"]) == 102
    assert sent["payload"].startswith(bytes.fromhex("FF" * 6))
    assert sent["address"] == ("255.255.255.255", 9)
    assert "Storage" in message
