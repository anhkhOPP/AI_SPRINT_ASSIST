"""
Tests cho MessageTemplates.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("INTERNAL_USERNAME", "testuser")
os.environ.setdefault("INTERNAL_PASSWORD", "testpass")

import pytest
from datetime import date
from src.reminders.messages import MessageTemplates


class TestMessageTemplates:

    def test_daily_meeting_reminder(self):
        msg = MessageTemplates.daily_meeting_reminder()
        assert "DAILY" in msg or "daily" in msg.lower()
        assert "09:10" in msg or "standup" in msg.lower()

    def test_logwork_reminder_contains_hours(self):
        msg = MessageTemplates.logwork_reminder(7.5)
        assert "7.5" in msg
        assert "log" in msg.lower()

    def test_missing_logwork_empty(self):
        msg = MessageTemplates.missing_logwork_report([], 7.5)
        assert "✅" in msg or "đủ" in msg.lower()

    def test_missing_logwork_with_members(self):
        members = [
            {"name": "Nguyen Van A", "position": "Developer", "hours": 3.0},
            {"name": "Tran Thi B", "position": "QA", "hours": 0.0},
        ]
        msg = MessageTemplates.missing_logwork_report(members, 7.5)
        assert "Nguyen Van A" in msg
        assert "Tran Thi B" in msg
        assert "Developer" in msg
        assert "2" in msg

    def test_missing_logwork_shows_hours(self):
        members = [{"name": "A", "position": "Dev", "hours": 3.5}]
        msg = MessageTemplates.missing_logwork_report(members, 7.5)
        assert "3.5" in msg

    def test_missing_daily_empty(self):
        msg = MessageTemplates.missing_daily_report([])
        assert "✅" in msg or "đầy đủ" in msg.lower()

    def test_missing_daily_with_members(self):
        members = [
            {"name": "Le Van C", "position": "Tech Lead"},
        ]
        msg = MessageTemplates.missing_daily_report(members)
        assert "Le Van C" in msg
        assert "Tech Lead" in msg

    def test_ask_pm_sprint_review(self):
        msg = MessageTemplates.ask_pm_sprint_review("Sprint 19")
        assert "Sprint 19" in msg
        assert "/set_review" in msg
        assert "Thứ 5" in msg

    def test_ask_pm_sprint_planning(self):
        msg = MessageTemplates.ask_pm_sprint_planning("Sprint 19", "Sprint 20")
        assert "Sprint 20" in msg
        assert "/set_planning" in msg

    def test_sprint_review_prep_today(self):
        msg = MessageTemplates.sprint_review_prep("Sprint 19", "26/05/2026 14:00", 0)
        assert "HÔM NAY" in msg
        assert "Sprint 19" in msg

    def test_sprint_review_prep_tomorrow(self):
        msg = MessageTemplates.sprint_review_prep("Sprint 19", "26/05/2026 14:00", 1)
        assert "NGÀY MAI" in msg

    def test_sprint_review_prep_3days(self):
        msg = MessageTemplates.sprint_review_prep("Sprint 19", "28/05/2026 14:00", 3)
        assert "3 ngày" in msg

    def test_sprint_review_prep_with_link(self):
        msg = MessageTemplates.sprint_review_prep(
            "Sprint 19", "26/05/2026 14:00", 1, "https://meet.google.com/xxx"
        )
        assert "https://meet.google.com/xxx" in msg

    def test_confirm_sprint_event_review(self):
        msg = MessageTemplates.confirm_sprint_event("review", "26/05/2026", "14:00")
        assert "Sprint Review" in msg
        assert "26/05/2026" in msg

    def test_confirm_sprint_event_planning(self):
        msg = MessageTemplates.confirm_sprint_event("planning", "27/05/2026", "09:00")
        assert "Sprint Planning" in msg

    def test_announce_sprint_event(self):
        msg = MessageTemplates.announce_sprint_event(
            "Sprint 19", "review", "26/05/2026", "14:00"
        )
        assert "Sprint 19" in msg
        assert "REVIEW" in msg.upper()
