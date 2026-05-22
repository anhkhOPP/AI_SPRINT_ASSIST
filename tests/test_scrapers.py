"""
Tests cho Scrapers - dùng mock data, không cần trang web thực.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("INTERNAL_USERNAME", "testuser")
os.environ.setdefault("INTERNAL_PASSWORD", "testpass")
os.environ.setdefault("INTERNAL_WORKLOG_URL", "https://10.0.0.1:8618/op_pm/Worklog?fav=test")

import pytest
from datetime import date
from src.scrapers.logwork_scraper import LogworkScraper
from src.scrapers.daily_scraper import DailyScraper


@pytest.fixture
def team_data():
    return [
        {"name": "Nguyen Van A", "position": "Developer", "uid": "uid-111"},
        {"name": "Tran Thi B",   "position": "QA",        "uid": "uid-222"},
        {"name": "Le Van C",     "position": "Tech Lead",  "uid": "uid-333"},
    ]


@pytest.fixture
def logwork(tmp_path, monkeypatch, team_data):
    team_file = tmp_path / "team.json"
    team_file.write_text(json.dumps(team_data, ensure_ascii=False))
    monkeypatch.chdir(tmp_path)
    return LogworkScraper()


@pytest.fixture
def daily(tmp_path, monkeypatch, team_data):
    team_file = tmp_path / "team.json"
    team_file.write_text(json.dumps(team_data, ensure_ascii=False))
    monkeypatch.chdir(tmp_path)
    return DailyScraper()


class TestLogworkScraper:

    def test_mock_data_has_correct_keys(self, logwork):
        data = logwork._mock_data()
        assert "logged" in data
        assert "missing" in data
        assert "summary" in data

    def test_mock_data_covers_all_team_members(self, logwork):
        data = logwork._mock_data()
        total = data["summary"]["logged_count"] + data["summary"]["missing_count"]
        assert total == len(logwork.team)

    def test_parse_api_response_logged(self, logwork):
        """Test parse API response - ai có đủ giờ."""
        api_data = {
            "data": [
                {"logByUserId": "uid-111", "spentTime": 8.0, "logByUser": {"item1": "User A"}},
                {"logByUserId": "uid-222", "spentTime": 7.5, "logByUser": {"item1": "User B"}},
                {"logByUserId": "uid-111", "spentTime": 1.0, "logByUser": {"item1": "User A"}},  # cộng dồn
            ]
        }
        result = logwork._parse_api_response(api_data, date.today())
        logged_names = [m["name"] for m in result["logged"]]
        missing_names = [m["name"] for m in result["missing"]]

        # uid-111 = 8+1 = 9h → đủ
        assert "Nguyen Van A" in logged_names
        # uid-222 = 7.5h → đủ
        assert "Tran Thi B" in logged_names
        # uid-333 = 0h → thiếu
        assert "Le Van C" in missing_names

    def test_parse_api_response_hours_accumulated(self, logwork):
        """Test cộng dồn nhiều log cùng user."""
        api_data = {
            "data": [
                {"logByUserId": "uid-111", "spentTime": 4.0, "logByUser": {"item1": "User A"}},
                {"logByUserId": "uid-111", "spentTime": 4.0, "logByUser": {"item1": "User A"}},
            ]
        }
        result = logwork._parse_api_response(api_data, date.today())
        logged = {m["name"]: m["hours"] for m in result["logged"]}
        assert logged.get("Nguyen Van A") == 8.0

    def test_parse_api_response_missing_when_no_log(self, logwork):
        """Test người không có log → missing."""
        api_data = {"data": []}  # Không ai log
        result = logwork._parse_api_response(api_data, date.today())
        assert len(result["missing"]) == len(logwork.team)
        assert len(result["logged"]) == 0

    def test_get_missing_users_returns_list(self, logwork):
        missing = logwork.get_missing_users()
        assert isinstance(missing, list)

    def test_last_workday_not_weekend(self, logwork):
        d = logwork._get_last_workday()
        assert d.weekday() < 5

    def test_build_post_data_contains_uids(self, logwork):
        params = logwork._build_post_data("21/May/2026 - 21/May/2026", ["uid-1", "uid-2"])
        param_names = [p[0] for p in params]
        param_values = [p[1] for p in params if p[0] == "uIds[]"]
        assert "uIds[]" in param_names
        assert "uid-1" in param_values
        assert "uid-2" in param_values

    def test_build_post_data_contains_date_range(self, logwork):
        date_range = "21/May/2026 - 21/May/2026"
        params = logwork._build_post_data(date_range, [])
        date_values = [p[1] for p in params if p[0] == "dateRange"]
        assert date_range in date_values


class TestDailyScraper:

    def test_mock_data_structure(self, daily):
        data = daily._mock_data(date.today())
        assert "date" in data
        assert "submitted" in data
        assert "missing" in data
        assert "entries" in data

    def test_mock_data_entries_have_fields(self, daily):
        data = daily._mock_data(date.today())
        for entry in data["entries"]:
            assert "name" in entry
            assert "yesterday" in entry
            assert "today" in entry
            assert "submitted" in entry

    def test_not_found_result_marks_all_missing(self, daily):
        result = daily._not_found_result(date.today())
        assert len(result["missing"]) == len(daily.team)
        assert result["submitted"] == []

    def test_get_missing_users_returns_list(self, daily):
        missing = daily.get_missing_users()
        assert isinstance(missing, list)

    def test_get_member_info_exact_match(self, daily):
        info = daily._get_member_info("Nguyen Van A")
        assert info["name"] == "Nguyen Van A"
        assert info["position"] == "Developer"

    def test_get_member_info_not_found(self, daily):
        info = daily._get_member_info("Nguyen Unknown")
        assert info["name"] == "Nguyen Unknown"
        assert info["position"] == ""

    def test_date_format_pattern(self, daily):
        today = date(2026, 5, 22)
        target_str = today.strftime(daily.DATE_FORMAT)
        assert target_str == "22-May-2026"

        title = "Daily Meeting 7 - 21-May-2026"
        match = daily.DAILY_TITLE_PATTERN.search(title)
        assert match is not None
        assert match.group(1) == "21-May-2026"
