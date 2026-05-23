"""
Tests cho webhook server - xử lý lệnh từ PM.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("INTERNAL_USERNAME", "testuser")
os.environ.setdefault("INTERNAL_PASSWORD", "testpass")

import pytest
from src.bot.webhook_server import _parse_event_command, _help_text, handle_pm_message
from unittest.mock import patch, MagicMock


class TestParseEventCommand:

    def test_parse_full_command_with_link(self):
        result = _parse_event_command("/set_review 26/05 14:00 https://meet.google.com/abc")
        assert result is not None
        date_str, time_str, link, room = result
        assert "05-26" in date_str or date_str.endswith("-05-26")
        assert time_str == "14:00"
        assert link == "https://meet.google.com/abc"

    def test_parse_command_without_link(self):
        result = _parse_event_command("/set_review 26/05 14:00")
        assert result is not None
        date_str, time_str, link, room = result
        assert time_str == "14:00"
        assert link == ""

    def test_parse_command_with_dash_separator(self):
        result = _parse_event_command("/set_planning 27-05 09:00")
        assert result is not None

    def test_parse_command_single_digit_day(self):
        result = _parse_event_command("/set_review 5/06 14:00")
        assert result is not None

    def test_parse_command_missing_time(self):
        result = _parse_event_command("/set_review 26/05")
        assert result is None

    def test_parse_command_missing_date(self):
        result = _parse_event_command("/set_review 14:00")
        assert result is None

    def test_parse_command_no_args(self):
        result = _parse_event_command("/set_review")
        assert result is None


class TestHandlePmMessage:

    def test_help_command(self):
        reply = handle_pm_message("/help", "PM")
        assert "/set_review" in reply
        assert "/set_planning" in reply
        assert "/sprint" in reply

    def test_unknown_message_returns_hint(self):
        reply = handle_pm_message("xin chào", "PM")
        assert "/set_review" in reply or "lệnh" in reply.lower()

    @patch("src.bot.webhook_server.get_sprint_manager")
    def test_sprint_command(self, mock_mgr):
        mock_sprint = MagicMock()
        mock_sprint.name = "Sprint 19"
        mock_sprint.start_date = "2026-05-13"
        mock_sprint.end_date = "2026-05-26"

        mock_mgr.return_value.get_current_sprint.return_value = mock_sprint
        mock_mgr.return_value.get_sprint_stats.return_value = {
            "days_remaining": 4,
            "velocity_percent": 85.0,
            "upcoming_events": [],
        }

        reply = handle_pm_message("/sprint", "PM")
        assert "Sprint 19" in reply
        assert "4" in reply
