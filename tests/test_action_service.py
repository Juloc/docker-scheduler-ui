from app import action_service


def test_group_start_uses_configured_order():
    group = {
        "containers": [
            {"container_name": "database"},
            {"container_name": "backend"},
            {"container_name": "frontend"},
        ]
    }

    ordered = action_service._ordered_group_items(group, "start")

    assert [item["container_name"] for item in ordered] == ["database", "backend", "frontend"]


def test_group_stop_reverses_configured_order():
    group = {
        "containers": [
            {"container_name": "database"},
            {"container_name": "backend"},
            {"container_name": "frontend"},
        ]
    }

    ordered = action_service._ordered_group_items(group, "stop")

    assert [item["container_name"] for item in ordered] == ["frontend", "backend", "database"]


def test_target_aliases_treat_id_short_id_and_name_as_same_container(monkeypatch):
    monkeypatch.setattr(
        action_service,
        "get_container_info",
        lambda ref: {
            "id": "abcdef1234567890",
            "short_id": "abcdef123456",
            "name": "media-server",
        },
    )

    aliases = action_service._target_aliases(["abcdef1234567890"])

    assert "abcdef1234567890" in aliases
    assert "abcdef123456" in aliases
    assert "media-server" in aliases


def test_conflicting_group_run_is_detected_before_first_step(monkeypatch):
    monkeypatch.setattr(
        action_service.database,
        "list_action_runs",
        lambda limit=1000: [
            {
                "id": 7,
                "status": "running",
                "source_type": "group",
                "source_id": "12",
            }
        ],
    )
    monkeypatch.setattr(
        action_service.database,
        "get_group",
        lambda group_id: {"containers": [{"container_name": "media-server"}]},
    )
    monkeypatch.setattr(
        action_service,
        "get_container_info",
        lambda ref: {
            "id": "abcdef1234567890",
            "short_id": "abcdef123456",
            "name": "media-server",
        },
    )

    conflicts = action_service._find_conflicting_runs(["abcdef1234567890"])

    assert [run["id"] for run in conflicts] == [7]
