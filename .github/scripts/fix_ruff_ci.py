from pathlib import Path


def replace(path: str, old: str, new: str, count: int = -1) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    if old not in content:
        raise RuntimeError(f"Expected text was not found in {path}: {old!r}")
    file_path.write_text(content.replace(old, new, count), encoding="utf-8")


replace(
    "app/notification_service.py",
    "        except Exception as exc:\n            errors.append(f\"{webhook['name']}: {exc}\")",
    "        except RuntimeError as exc:\n            errors.append(f\"{webhook['name']}: {exc}\")",
)
replace(
    "app/routes/nas_logs_settings.py",
    "    except Exception as exc:\n        return redirect_to(\"/settings\", error=str(exc))",
    "    except (RuntimeError, ValueError) as exc:\n        return redirect_to(\"/settings\", error=str(exc))",
)
replace(
    "app/scheduler_service.py",
    "from datetime import datetime, timedelta",
    "from datetime import datetime, timedelta, timezone",
)
replace(
    "app/scheduler_service.py",
    "next_run_time=datetime.now(),",
    "next_run_time=datetime.now(timezone.utc),",
)
replace(
    "app/scheduler_service.py",
    "            except Exception:\n                if attempt >= NAS_ACTION_MAX_ATTEMPTS:",
    "            except Exception:  # noqa: BLE001 - retry boundary must survive unexpected action failures\n                if attempt >= NAS_ACTION_MAX_ATTEMPTS:",
)
replace(
    "app/scheduler_service.py",
    "    except Exception as exc:\n        database.mark_schedule_run(schedule_id, str(exc))",
    "    except Exception as exc:  # noqa: BLE001 - scheduler jobs must persist errors instead of terminating\n        database.mark_schedule_run(schedule_id, str(exc))",
)
