"""
Tests cho Scrapers - dùng mock data, không cần trang web thực.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("INTERNAL_USERNAME", "testuser")
os.environ.setdefault("INTERNAL_PASSWORD", "testpass")

import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from src.scrapers.logwork_scraper import LogworkScraper
from src.scrapers.daily_scraper import DailyScraper


@pytest.fixture
def logwork(tmp_path, monkeypatch):
    """LogworkScraper với team.json tạm."""
    import json
    team = [
        {"name": "Nguyen Van A", "position": "Developer"},
        {"name": "Tran Thi B", "position": "QA"},
        {"name": "Le Van C", "position": "Tech Lead"},
    ]
    team_file = tmp_path / "team.json"
    team_file.write_text(json.dumps(team, ensure_ascii=False))
    monkeypatch.chdir(tmp_path)
    return LogworkScraper()


@pytest.fixture
def daily(tmp_path, monkeypatch):
    """DailyScraper với team.json tạm."""
    import json
    team = [
        {"name": "Nguyen Van A", "position": "Developer"},
        {"name": "Tran Thi B", "position": "QA"},
        {"name": "Le Van C", "position": "Tech Lead"},
    ]
    team_file = tmp_path / "team.json"
    team_file.write_text(json.dumps(team, ensure_ascii=False))
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

    def test_build_result_logged(self, logwork):
        user_hours = {"Nguyen Van A": 8.0, "Tran Thi B": 7.5, "Le Van C": 3.0}
        result = logwork._build_result(user_hours)
        logged_names = [m["name"] for m in result["logged"]]
        missing_names = [m["name"] for m in result["missing"]]
        assert "Nguyen Van A" in logged_names
        assert "Tran Thi B" in logged_names
        assert "Le Van C" in missing_names  # 3h < 7.5h

    def test_build_result_missing_not_in_worklog(self, logwork):
        # Le Van C không xuất hiện trong worklog → missing
        user_hours = {"Nguyen Van A": 8.0}
        result = logwork._build_result(user_hours)
        missing_names = [m["name"] for m in result["missing"]]
        assert "Le Van C" in missing_names
        assert "Tran Thi B" in missing_names

    def test_extract_hours_formats(self, logwork):
        from bs4 import BeautifulSoup

        def make_cells(text):
            soup = BeautifulSoup(f"<tr><td>user</td><td>{text}</td></tr>", "lxml")
            return soup.find_all("td")

        assert logwork._extract_hours(make_cells("7.5h"), 1) == 7.5
        assert logwork._extract_hours(make_cells("7,5h"), 1) == 7.5
        assert logwork._extract_hours(make_cells("8h"), 1) == 8.0
        assert logwork._extract_hours(make_cells("7h30m"), 1) == 7.5
        assert logwork._extract_hours(make_cells("450m"), 1) == 7.5
        assert logwork._extract_hours(make_cells("0"), 1) == 0.0
        assert logwork._extract_hours(make_cells("-"), 1) == 0.0

    def test_get_missing_users_returns_list(self, logwork):
        missing = logwork.get_missing_users()
        assert isinstance(missing, list)

    def test_summary_total_hours(self, logwork):
        user_hours = {"Nguyen Van A": 8.0, "Tran Thi B": 7.5}
        result = logwork._build_result(user_hours)
        assert result["summary"]["total_hours"] == 15.5


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
        """Kiểm tra format ngày trong tên document."""
        import re
        today = date(2026, 5, 22)
        target_str = today.strftime(daily.DATE_FORMAT)
        assert target_str == "22-May-2026"

        # Kiểm tra regex pattern khớp với tên document thực tế
        title = "Daily Meeting 7 - 21-May-2026"
        match = daily.DAILY_TITLE_PATTERN.search(title)
        assert match is not None
        assert match.group(1) == "21-May-2026"
