"""Tests cho WorkdayCalendar - logic ngày làm việc T7."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SATURDAY_OFF_WEEKS", "2,3")
os.environ.setdefault("SATURDAY_MIN_HOURS", "4.0")
os.environ.setdefault("LOGWORK_MIN_HOURS", "7.5")

import pytest
from datetime import date
from src.utils.schedule_utils import WorkdayCalendar


class TestWeekOfMonth:
    def test_week1(self):
        assert WorkdayCalendar.week_of_month(date(2026, 5, 1)) == 1
        assert WorkdayCalendar.week_of_month(date(2026, 5, 7)) == 1

    def test_week2(self):
        assert WorkdayCalendar.week_of_month(date(2026, 5, 8)) == 2
        assert WorkdayCalendar.week_of_month(date(2026, 5, 14)) == 2

    def test_week3(self):
        assert WorkdayCalendar.week_of_month(date(2026, 5, 15)) == 3
        assert WorkdayCalendar.week_of_month(date(2026, 5, 21)) == 3

    def test_week4(self):
        assert WorkdayCalendar.week_of_month(date(2026, 5, 22)) == 4
        assert WorkdayCalendar.week_of_month(date(2026, 5, 28)) == 4

    def test_week5(self):
        assert WorkdayCalendar.week_of_month(date(2026, 5, 29)) == 5


class TestSaturdayWorkday:
    def test_saturday_week1_is_workday(self):
        # May 2, 2026 = Saturday week 1
        sat_w1 = date(2026, 5, 2)
        assert sat_w1.weekday() == 5
        assert WorkdayCalendar.week_of_month(sat_w1) == 1
        assert WorkdayCalendar.is_saturday_workday(sat_w1) is True

    def test_saturday_week2_is_off(self):
        # May 9, 2026 = Saturday week 2
        sat_w2 = date(2026, 5, 9)
        assert sat_w2.weekday() == 5
        assert WorkdayCalendar.is_saturday_workday(sat_w2) is False

    def test_saturday_week3_is_off(self):
        # May 16, 2026 = Saturday week 3
        sat_w3 = date(2026, 5, 16)
        assert WorkdayCalendar.is_saturday_workday(sat_w3) is False

    def test_saturday_week4_is_workday(self):
        # May 23, 2026 = Saturday week 4
        sat_w4 = date(2026, 5, 23)
        assert WorkdayCalendar.is_saturday_workday(sat_w4) is True

    def test_saturday_week5_is_workday(self):
        # May 30, 2026 = Saturday week 5
        sat_w5 = date(2026, 5, 30)
        assert WorkdayCalendar.is_saturday_workday(sat_w5) is True

    def test_non_saturday_returns_false(self):
        monday = date(2026, 5, 4)
        assert WorkdayCalendar.is_saturday_workday(monday) is False


class TestMinHours:
    def test_weekday_75h(self):
        monday = date(2026, 5, 4)
        assert WorkdayCalendar.get_min_hours(monday) == 7.5

    def test_saturday_workday_4h(self):
        sat_w1 = date(2026, 5, 2)
        assert WorkdayCalendar.get_min_hours(sat_w1) == 4.0


class TestGetLastWorkday:
    def test_monday_returns_friday_if_sat_off(self):
        # May 11 (Mon) - May 10 (Sun) - May 9 (Sat week 2 = OFF) → May 8 (Fri)
        monday = date(2026, 5, 11)
        last = WorkdayCalendar.get_last_workday(monday)
        assert last == date(2026, 5, 8)  # Friday

    def test_monday_returns_saturday_if_sat_on(self):
        # May 25 (Mon) - May 24 (Sun) - May 23 (Sat week 4 = ON) → May 23 (Sat)
        monday = date(2026, 5, 25)
        last = WorkdayCalendar.get_last_workday(monday)
        assert last == date(2026, 5, 23)  # Saturday

    def test_tuesday_returns_monday(self):
        tuesday = date(2026, 5, 5)
        last = WorkdayCalendar.get_last_workday(tuesday)
        assert last == date(2026, 5, 4)  # Monday


class TestShouldCheckLogwork:
    def test_monday_after_sat_off_checks_friday(self):
        # Monday May 11, Sat May 9 = week 2 = off → check Friday May 8
        should, check_date, min_hours = WorkdayCalendar.should_check_logwork_today(date(2026, 5, 11))
        assert should is True
        assert check_date == date(2026, 5, 8)
        assert min_hours == 7.5

    def test_monday_after_sat_on_checks_saturday(self):
        # Monday May 25, Sat May 23 = week 4 = on → check Saturday May 23
        should, check_date, min_hours = WorkdayCalendar.should_check_logwork_today(date(2026, 5, 25))
        assert should is True
        assert check_date == date(2026, 5, 23)
        assert min_hours == 4.0

    def test_saturday_no_check(self):
        should, _, _ = WorkdayCalendar.should_check_logwork_today(date(2026, 5, 23))
        assert should is False

    def test_sunday_no_check(self):
        should, _, _ = WorkdayCalendar.should_check_logwork_today(date(2026, 5, 24))
        assert should is False


class TestShouldCheckDaily:
    def test_weekdays_yes(self):
        for day in range(4, 9):  # Mon-Fri May 4-8
            assert WorkdayCalendar.should_check_daily_today(date(2026, 5, day)) is True

    def test_saturday_no(self):
        assert WorkdayCalendar.should_check_daily_today(date(2026, 5, 23)) is False

    def test_sunday_no(self):
        assert WorkdayCalendar.should_check_daily_today(date(2026, 5, 24)) is False
