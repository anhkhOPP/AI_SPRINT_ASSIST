"""
Unit tests cho SprintManager.
"""
import os
import sys
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages?key=test")
os.environ.setdefault("CURRENT_SPRINT_NAME", "Sprint Test")
os.environ.setdefault("CURRENT_SPRINT_START", "2024-01-01")
os.environ.setdefault("SPRINT_DURATION_WEEKS", "2")

import pytest
from src.sprint.manager import SprintManager, Sprint, SprintEvent, SprintState


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    """Dùng thư mục tạm cho data files."""
    monkeypatch.setattr(SprintManager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(SprintManager, "SPRINT_FILE", tmp_path / "sprints.json")
    monkeypatch.setattr(SprintManager, "CURRENT_SPRINT_FILE", tmp_path / "current_sprint.json")
    return tmp_path


class TestSprintEvent:

    def test_days_until_future(self):
        future_date = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        event = SprintEvent(
            event_type="review",
            scheduled_date=future_date,
            scheduled_time="14:00",
        )
        assert event.days_until() == 5

    def test_days_until_today(self):
        today = date.today().strftime("%Y-%m-%d")
        event = SprintEvent(
            event_type="review",
            scheduled_date=today,
            scheduled_time="14:00",
        )
        assert event.days_until() == 0

    def test_days_until_past(self):
        past_date = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
        event = SprintEvent(
            event_type="review",
            scheduled_date=past_date,
            scheduled_time="14:00",
        )
        assert event.days_until() == -2

    def test_to_dict_and_from_dict(self):
        event = SprintEvent(
            event_type="planning",
            scheduled_date="2024-01-29",
            scheduled_time="09:00",
            meeting_link="https://meet.google.com/test",
        )
        d = event.to_dict()
        restored = SprintEvent.from_dict(d)
        assert restored.event_type == event.event_type
        assert restored.scheduled_date == event.scheduled_date
        assert restored.meeting_link == event.meeting_link


class TestSprint:

    def test_days_remaining_future(self):
        future_end = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        sprint = Sprint(name="Sprint 1", start_date="2024-01-01", end_date=future_end)
        assert sprint.days_remaining() == 10

    def test_is_active_true(self):
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        sprint = Sprint(name="Sprint 1", start_date=yesterday, end_date=tomorrow)
        assert sprint.is_active() is True

    def test_is_active_future(self):
        future_start = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        future_end = (date.today() + timedelta(days=19)).strftime("%Y-%m-%d")
        sprint = Sprint(name="Sprint 1", start_date=future_start, end_date=future_end)
        assert sprint.is_active() is False

    def test_get_event_found(self):
        sprint = Sprint(name="Sprint 1", start_date="2024-01-01", end_date="2024-01-14")
        event = SprintEvent(event_type="review", scheduled_date="2024-01-12", scheduled_time="14:00")
        sprint.events.append(event.to_dict())

        found = sprint.get_event("review")
        assert found is not None
        assert found.event_type == "review"

    def test_get_event_not_found(self):
        sprint = Sprint(name="Sprint 1", start_date="2024-01-01", end_date="2024-01-14")
        assert sprint.get_event("review") is None


class TestSprintManager:

    def test_init_creates_sprint(self, temp_data_dir):
        manager = SprintManager()
        sprint = manager.get_current_sprint()
        assert sprint is not None
        assert sprint.name  # Sprint có tên hợp lệ

    def test_update_sprint_event(self, temp_data_dir):
        manager = SprintManager()
        future_date = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")

        event = manager.update_sprint_event(
            event_type="review",
            scheduled_date=future_date,
            scheduled_time="14:00",
            created_by="PM",
        )

        assert event.event_type == "review"
        assert event.scheduled_date == future_date

        # Kiểm tra được lưu
        sprint = manager.get_current_sprint()
        saved_event = sprint.get_event("review")
        assert saved_event is not None
        assert saved_event.scheduled_date == future_date

    def test_get_upcoming_events(self, temp_data_dir):
        manager = SprintManager()
        future_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
        manager.update_sprint_event("review", future_date, "14:00")

        events = manager.get_upcoming_events(days_ahead=7)
        assert len(events) >= 1

    def test_should_send_prep_reminder(self, temp_data_dir):
        manager = SprintManager()
        # Ngày mai
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        manager.update_sprint_event("review", tomorrow, "14:00")

        should_send, days = manager.should_send_prep_reminder("review")
        assert should_send is True
        assert days == 1

    def test_get_sprint_stats(self, temp_data_dir):
        manager = SprintManager()
        manager.update_metrics(planned_points=50, completed_points=40)
        stats = manager.get_sprint_stats()

        assert "sprint_name" in stats
        assert "days_remaining" in stats
        assert stats["velocity_percent"] == 80.0

    def test_persist_sprint_to_file(self, temp_data_dir):
        manager1 = SprintManager()
        future_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
        manager1.update_sprint_event("review", future_date, "14:00")

        # Load lại từ file
        manager2 = SprintManager()
        sprint = manager2.get_current_sprint()
        event = sprint.get_event("review")
        assert event is not None
        assert event.scheduled_date == future_date
