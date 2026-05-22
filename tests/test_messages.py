"""
Unit tests cho MessageTemplates.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set mock env vars trước khi import config
os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("TIMEZONE", "Asia/Ho_Chi_Minh")
os.environ.setdefault("CURRENT_SPRINT_NAME", "Sprint 1")
os.environ.setdefault("CURRENT_SPRINT_START", "2024-01-01")

import pytest
from src.reminders.messages import MessageTemplates


class TestMessageTemplates:

    def test_daily_meeting_reminder_contains_time(self):
        msg = MessageTemplates.daily_meeting_reminder()
        assert "DAILY" in msg.upper() or "Daily" in msg
        assert "9:10" in msg or "09:10" in msg or "daily" in msg.lower()

    def test_logwork_reminder_contains_deadline(self):
        msg = MessageTemplates.logwork_reminder()
        assert "log work" in msg.lower() or "LOG WORK" in msg
        assert "17:30" in msg or "18:00" in msg

    def test_missing_logwork_empty_list(self):
        msg = MessageTemplates.missing_logwork_report([])
        assert "tất cả" in msg.lower() or "✅" in msg

    def test_missing_logwork_with_users(self):
        users = ["Nguyen Van A", "Tran Thi B"]
        msg = MessageTemplates.missing_logwork_report(users)
        assert "Nguyen Van A" in msg
        assert "Tran Thi B" in msg
        assert "2" in msg  # số lượng người

    def test_missing_daily_empty_list(self):
        msg = MessageTemplates.missing_daily_report([])
        assert "✅" in msg or "đầy đủ" in msg.lower()

    def test_missing_daily_with_users(self):
        users = ["Le Van C"]
        msg = MessageTemplates.missing_daily_report(users)
        assert "Le Van C" in msg

    def test_sprint_review_ask_contains_question(self):
        msg = MessageTemplates.sprint_review_ask("Sprint 5")
        assert "Sprint 5" in msg or "sprint review" in msg.lower()
        assert "?" in msg

    def test_sprint_planning_ask_monday(self):
        msg = MessageTemplates.sprint_planning_ask("Sprint 6")
        assert "planning" in msg.lower()

    def test_sprint_review_prep_today(self):
        msg = MessageTemplates.sprint_review_prep("Sprint 5", "26/01/2024 14:00", 0)
        assert "HÔM NAY" in msg or "hôm nay" in msg.lower()
        assert "Sprint 5" in msg

    def test_sprint_review_prep_tomorrow(self):
        msg = MessageTemplates.sprint_review_prep("Sprint 5", "27/01/2024 14:00", 1)
        assert "NGÀY MAI" in msg or "ngày mai" in msg.lower()

    def test_sprint_review_prep_3days(self):
        msg = MessageTemplates.sprint_review_prep("Sprint 5", "29/01/2024 14:00", 3)
        assert "3 ngày" in msg

    def test_weekly_summary(self):
        msg = MessageTemplates.weekly_summary("Sprint 5", 3, ["Nguyen Van A"])
        assert "Sprint 5" in msg
        assert "3 ngày" in msg

    def test_morning_digest(self):
        msg = MessageTemplates.morning_digest("Sprint 5", 5, 3, 10, [])
        assert "Sprint 5" in msg
        assert "5 ngày" in msg

    def test_overtime_warning(self):
        msg = MessageTemplates.overtime_warning("Sprint 5", ["Task A chưa done"])
        assert "Task A" in msg
        assert "Sprint 5" in msg
