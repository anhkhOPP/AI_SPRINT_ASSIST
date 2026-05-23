"""
Tiện ích tính toán ngày làm việc theo quy tắc công ty.

Quy tắc:
- T2-T6: ngày làm việc bình thường, log 7.5h
- T7 tuần 1, 4, 5 trong tháng: ngày làm việc, log 4h
- T7 tuần 2, 3 trong tháng: nghỉ
- CN: nghỉ
"""
from datetime import date, timedelta
from typing import Tuple
import os


class WorkdayCalendar:

    # Tuần trong tháng T7 được nghỉ (configurable qua env)
    # week_of_month = ceil(day / 7), đếm từ 1
    SATURDAY_OFF_WEEKS = [
        int(w.strip())
        for w in os.getenv("SATURDAY_OFF_WEEKS", "2,3").split(",")
        if w.strip().isdigit()
    ]

    WEEKDAY_MIN_HOURS = float(os.getenv("LOGWORK_MIN_HOURS", "7.5"))
    SATURDAY_MIN_HOURS = float(os.getenv("SATURDAY_MIN_HOURS", "4.0"))

    @classmethod
    def week_of_month(cls, d: date) -> int:
        """Tuần thứ mấy trong tháng (1-indexed)."""
        return (d.day - 1) // 7 + 1

    @classmethod
    def is_saturday_workday(cls, d: date) -> bool:
        """T7 có phải ngày làm việc không (tuần 1, 4, 5)."""
        if d.weekday() != 5:
            return False
        week = cls.week_of_month(d)
        return week not in cls.SATURDAY_OFF_WEEKS

    @classmethod
    def is_workday(cls, d: date) -> bool:
        """Ngày d có phải ngày làm việc không."""
        if d.weekday() == 6:  # Chủ nhật
            return False
        if d.weekday() == 5:  # Thứ 7
            return cls.is_saturday_workday(d)
        return True  # T2-T6 luôn làm việc

    @classmethod
    def get_min_hours(cls, d: date) -> float:
        """Số giờ log work tối thiểu cho ngày d."""
        if d.weekday() == 5:
            return cls.SATURDAY_MIN_HOURS
        return cls.WEEKDAY_MIN_HOURS

    @classmethod
    def get_last_workday(cls, from_date: date = None) -> date:
        """
        Ngày làm việc gần nhất trước from_date.
        Dùng cho check logwork buổi sáng (kiểm tra hôm qua).
        """
        if from_date is None:
            from_date = date.today()

        check = from_date - timedelta(days=1)
        # Tìm ngày làm việc gần nhất (tối đa 7 ngày về trước)
        for _ in range(7):
            if cls.is_workday(check):
                return check
            check -= timedelta(days=1)

        return from_date - timedelta(days=1)  # fallback

    @classmethod
    def should_check_logwork_today(cls, today: date = None) -> Tuple[bool, date, float]:
        """
        Hôm nay có cần check logwork không?

        Returns:
            (should_check: bool, check_date: date, min_hours: float)

        Logic:
        - T2-T6: check logwork ngày hôm qua
        - T2: check T7 (nếu T7 làm) hoặc T6 (nếu T7 nghỉ)
        - T7 làm: KHÔNG check (check vào T2)
        - T7 nghỉ: không làm việc
        - CN: không làm việc
        """
        if today is None:
            today = date.today()

        weekday = today.weekday()

        # CN: không check
        if weekday == 6:
            return False, today, 0

        # T7: không check logwork (check vào T2)
        if weekday == 5:
            return False, today, 0

        # T2-T6: check ngày làm việc gần nhất
        last_wd = cls.get_last_workday(today)
        min_hours = cls.get_min_hours(last_wd)
        return True, last_wd, min_hours

    @classmethod
    def should_check_daily_today(cls, today: date = None) -> bool:
        """
        Hôm nay có cần check daily standup không?
        T2-T6: có. T7, CN: không.
        """
        if today is None:
            today = date.today()
        return today.weekday() < 5  # T2=0 ... T6=4

    @classmethod
    def should_send_daily_reminder_today(cls, today: date = None) -> bool:
        """
        Hôm nay có nhắc họp daily không?
        T2-T6: có. T7 làm: KHÔNG (không có daily T7).
        """
        if today is None:
            today = date.today()
        return today.weekday() < 5

    @classmethod
    def should_send_logwork_reminder_today(cls, today: date = None) -> bool:
        """
        Hôm nay có nhắc log work cuối ngày không?
        T2-T6: có. T7 làm: có (nhắc log 4h).
        """
        if today is None:
            today = date.today()
        return cls.is_workday(today)

    @classmethod
    def describe_day(cls, d: date) -> str:
        """Mô tả ngày: 'Monday', 'Saturday (week 1 - workday)', etc."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        name = days[d.weekday()]
        if d.weekday() == 5:
            week = cls.week_of_month(d)
            workday = cls.is_saturday_workday(d)
            return f"{name} (week {week} of month - {'workday 4h' if workday else 'day off'})"
        return name
