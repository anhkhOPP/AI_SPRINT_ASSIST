"""
Unit tests cho Scrapers (với mock data - không cần trang web thực).
"""
import os
import sys
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("TEAM_MEMBERS", "Nguyen Van A:a@test.com;Tran Thi B:b@test.com;Le Van C:c@test.com")

import pytest
from src.scrapers.logwork_scraper import LogworkScraper
from src.scrapers.daily_scraper import DailyScraper


class TestLogworkScraper:

    def test_mock_data_returns_structure(self):
        """Test mock data khi URL chưa cấu hình."""
        scraper = LogworkScraper()
        data = scraper._mock_data(date.today())

        assert "date" in data
        assert "logged" in data
        assert "missing" in data
        assert "logged_count" in data
        assert "missing_count" in data
        assert isinstance(data["logged"], list)
        assert isinstance(data["missing"], list)

    def test_mock_data_logged_plus_missing_equals_total(self):
        scraper = LogworkScraper()
        data = scraper._mock_data(date.today())
        total = data["logged_count"] + data["missing_count"]
        team_count = len(scraper.team_members) if scraper.team_members else 4
        assert total == team_count

    def test_get_missing_users_no_url_returns_list(self):
        """Khi không có URL, dùng mock data và trả về list."""
        scraper = LogworkScraper()
        missing = scraper.get_missing_users()
        assert isinstance(missing, list)

    def test_fetch_data_uses_yesterday_by_default(self):
        scraper = LogworkScraper()
        data = scraper.fetch_data()

        yesterday = date.today() - timedelta(days=1)
        # Bỏ qua cuối tuần
        if yesterday.weekday() >= 5:
            yesterday = yesterday - timedelta(days=yesterday.weekday() - 4)

        assert data["date"] == yesterday.strftime("%Y-%m-%d")

    def test_fetch_data_with_specific_date(self):
        scraper = LogworkScraper()
        target = date(2024, 1, 15)
        data = scraper.fetch_data(target)
        assert data["date"] == "2024-01-15"

    def test_build_result_structure(self):
        result = LogworkScraper._build_result(
            date(2024, 1, 15),
            ["User A", "User B"],
            ["User C"],
        )
        assert result["date"] == "2024-01-15"
        assert "User A" in result["logged"]
        assert "User C" in result["missing"]
        assert result["logged_count"] == 2
        assert result["missing_count"] == 1


class TestDailyScraper:

    def test_mock_data_returns_structure(self):
        scraper = DailyScraper()
        data = scraper._mock_data(date.today())

        assert "date" in data
        assert "submitted" in data
        assert "missing" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_get_missing_users_no_url_returns_list(self):
        scraper = DailyScraper()
        missing = scraper.get_missing_users()
        assert isinstance(missing, list)

    def test_get_daily_entries_returns_list(self):
        scraper = DailyScraper()
        entries = scraper.get_daily_entries()
        assert isinstance(entries, list)

    def test_entries_have_required_fields(self):
        scraper = DailyScraper()
        data = scraper._mock_data(date.today())
        for entry in data["entries"]:
            assert "user" in entry
            assert "yesterday" in entry
            assert "today" in entry
            assert "blockers" in entry
            assert "submitted" in entry

    def test_fetch_data_for_today(self):
        scraper = DailyScraper()
        data = scraper.fetch_data(date.today())
        assert data["date"] == date.today().strftime("%Y-%m-%d")

    def test_build_result_structure(self):
        entries = [{"user": "A", "yesterday": "x", "today": "y", "blockers": "", "submitted": True}]
        result = DailyScraper._build_result(
            date(2024, 1, 15),
            ["A"],
            ["B", "C"],
            entries,
        )
        assert result["submitted_count"] == 1
        assert result["missing_count"] == 2
        assert len(result["entries"]) == 1
