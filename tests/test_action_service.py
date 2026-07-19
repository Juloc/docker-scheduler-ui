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
