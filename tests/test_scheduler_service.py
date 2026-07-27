from datetime import datetime

from app import scheduler_service


def test_nas_group_action_retries_failed_runs(monkeypatch):
    runs = iter([1, 2, 3])
    statuses = {
        1: {"status": "failed"},
        2: {"status": "failed"},
        3: {"status": "success"},
    }
    triggers: list[str] = []
    sleeps: list[int] = []

    def start_group_run(group_id, action, background, trigger_type, check_nas):
        assert group_id == 7
        assert action == "start"
        assert background is False
        assert check_nas is False
        triggers.append(trigger_type)
        return next(runs)

    monkeypatch.setattr(scheduler_service.action_service, "start_group_run", start_group_run)
    monkeypatch.setattr(scheduler_service.database, "get_action_run", lambda run_id: statuses[run_id])
    monkeypatch.setattr(scheduler_service.time, "sleep", sleeps.append)

    scheduler_service._run_nas_group_actions([{"id": 7}], "start", "nas-online")

    assert triggers == ["nas-online", "nas-online-retry-2", "nas-online-retry-3"]
    assert sleeps == [scheduler_service.NAS_ACTION_RETRY_SECONDS] * 2


def test_nas_group_action_stops_after_max_failed_attempts(monkeypatch):
    attempts: list[str] = []
    sleeps: list[int] = []

    def start_group_run(group_id, action, background, trigger_type, check_nas):
        attempts.append(trigger_type)
        return len(attempts)

    monkeypatch.setattr(scheduler_service.action_service, "start_group_run", start_group_run)
    monkeypatch.setattr(scheduler_service.database, "get_action_run", lambda run_id: {"status": "failed"})
    monkeypatch.setattr(scheduler_service.time, "sleep", sleeps.append)

    scheduler_service._run_nas_group_actions([{"id": 1}], "start", "nas-online")

    assert len(attempts) == scheduler_service.NAS_ACTION_MAX_ATTEMPTS
    assert len(sleeps) == scheduler_service.NAS_ACTION_MAX_ATTEMPTS - 1


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
