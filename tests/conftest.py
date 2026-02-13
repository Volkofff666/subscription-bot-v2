from pathlib import Path

import pytest

import database

TEST_SUITES = {
    "test_database.py": "Database lifecycle and subscription state",
    "test_subscription_tasks.py": "Background subscription jobs",
    "test_payments.py": "Tribute webhook and payment factory",
    "test_admin_and_messages.py": "Admin helpers and message templates",
}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_bot.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    data_dir = Path(database.DATABASE_PATH).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return db_path


def pytest_report_header(config):
    lines = ["Subscription Bot Test Plan:"]
    for filename, description in TEST_SUITES.items():
        lines.append(f"  - {filename}: {description}")
    return lines


def _module_from_nodeid(nodeid: str) -> str:
    normalized = nodeid.replace("\\", "/")
    return normalized.split("::", 1)[0].split("/")[-1]


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    outcomes = ("passed", "failed", "skipped", "xfailed", "xpassed", "error")
    counts = {}

    for outcome in outcomes:
        for report in terminalreporter.stats.get(outcome, []):
            module = _module_from_nodeid(report.nodeid)
            bucket = counts.setdefault(module, {name: 0 for name in outcomes})
            bucket[outcome] += 1

    terminalreporter.section("Coverage Summary", sep="=")
    for filename, description in TEST_SUITES.items():
        bucket = counts.get(filename, {name: 0 for name in outcomes})
        total = sum(bucket.values())
        ok = bucket["failed"] == 0 and bucket["error"] == 0 and total > 0
        status = "OK" if ok else "WARN"
        terminalreporter.write_line(
            f"[{status}] {filename}: {description} | "
            f"total={total}, passed={bucket['passed']}, failed={bucket['failed']}, "
            f"errors={bucket['error']}, skipped={bucket['skipped']}"
        )

    failed_reports = terminalreporter.stats.get("failed", []) + terminalreporter.stats.get("error", [])
    if failed_reports:
        terminalreporter.write_line("")
        terminalreporter.write_line("Failed tests:")
        for report in failed_reports:
            terminalreporter.write_line(f"  - {report.nodeid}")
