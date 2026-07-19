from datetime import datetime

from app import scheduler_service


def test_upcoming_occurrences_expands_daily_schedule(monkeypatch):
    monkeypatch.setattr(
        scheduler_service.database,
        "list_enabled_schedules",
        lambda: [
            {
                "id": 1,
                "name": "Night stop",
                "target_type": "group",
                "target_id": "2",
                "action": "stop",
                "hour": 23,
                "minute": 30,
                "weekdays": "",
            }
        ],
    )

    now = datetime(2026, 7, 19, 20, 0).astimezone()
    occurrences = scheduler_service.get_upcoming_occurrences(days=7, now=now)

    assert len(occurrences) == 7
    assert all(item["name"] == "Night stop" for item in occurrences)
    assert all(item["time_label"] == "23:30" for item in occurrences)
    assert occurrences == sorted(occurrences, key=lambda item: item["run_at"])


def test_upcoming_occurrences_respects_selected_weekdays(monkeypatch):
    monkeypatch.setattr(
        scheduler_service.database,
        "list_enabled_schedules",
        lambda: [
            {
                "id": 2,
                "name": "Weekday start",
                "target_type": "group",
                "target_id": "3",
                "action": "start",
                "hour": 8,
                "minute": 0,
                "weekdays": "mon,tue,wed,thu,fri",
            }
        ],
    )

    now = datetime(2026, 7, 19, 20, 0).astimezone()  # Sunday
    occurrences = scheduler_service.get_upcoming_occurrences(days=7, now=now)

    assert len(occurrences) == 5
    assert [item["run_at"].weekday() for item in occurrences] == [0, 1, 2, 3, 4]
