"""
Sprint Manager - Quản lý vòng đời sprint.

Lưu trữ và quản lý:
- Thông tin sprint hiện tại (tên, ngày, trạng thái)
- Lịch Sprint Review và Sprint Planning
- Lịch sử các sprints đã qua
- Thống kê sprint (velocity, completion rate)

Dữ liệu được lưu vào SQLite (không cần server DB riêng).
"""
import os
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

import pytz
from loguru import logger

from config import get_config


class SprintState(str, Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    REVIEW = "review"
    RETROSPECTIVE = "retrospective"
    CLOSED = "closed"


@dataclass
class SprintEvent:
    """Một sự kiện trong sprint (review/planning/retro)."""
    event_type: str           # "review" | "planning" | "retro" | "demo"
    scheduled_date: str       # YYYY-MM-DD
    scheduled_time: str       # HH:MM
    meeting_link: str = ""
    notes: str = ""
    notified_1day: bool = False
    notified_3days: bool = False
    created_by: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "SprintEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def get_datetime(self, tz: pytz.tzinfo.BaseTzInfo) -> Optional[datetime]:
        """Chuyển đổi sang datetime có timezone."""
        try:
            dt_str = f"{self.scheduled_date} {self.scheduled_time}"
            naive = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            return tz.localize(naive)
        except Exception:
            return None

    def days_until(self) -> int:
        """Số ngày đến event."""
        try:
            event_date = datetime.strptime(self.scheduled_date, "%Y-%m-%d").date()
            return (event_date - date.today()).days
        except Exception:
            return -1


@dataclass
class Sprint:
    """Thông tin một sprint."""
    name: str
    start_date: str           # YYYY-MM-DD
    end_date: str             # YYYY-MM-DD
    state: str = SprintState.ACTIVE
    goal: str = ""
    team_members: List[str] = None
    events: List[Dict] = None
    metrics: Dict[str, Any] = None

    def __post_init__(self):
        if self.team_members is None:
            self.team_members = []
        if self.events is None:
            self.events = []
        if self.metrics is None:
            self.metrics = {
                "planned_points": 0,
                "completed_points": 0,
                "planned_tasks": 0,
                "completed_tasks": 0,
            }

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Sprint":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def days_remaining(self) -> int:
        try:
            end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
            return max(0, (end - date.today()).days)
        except Exception:
            return 0

    def is_active(self) -> bool:
        try:
            start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
            end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
            return start <= date.today() <= end
        except Exception:
            return False

    def get_event(self, event_type: str) -> Optional[SprintEvent]:
        for e in self.events:
            ev = SprintEvent.from_dict(e)
            if ev.event_type == event_type:
                return ev
        return None


class SprintManager:
    """
    Quản lý sprint và các sự kiện liên quan.
    Dữ liệu lưu vào JSON file (đơn giản, không cần DB server).
    """

    DATA_DIR = Path("./data")
    SPRINT_FILE = DATA_DIR / "sprints.json"
    CURRENT_SPRINT_FILE = DATA_DIR / "current_sprint.json"

    def __init__(self):
        cfg = get_config()
        self.cfg = cfg
        self.tz = cfg.schedule.get_tz()
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._current_sprint: Optional[Sprint] = None
        self._load_or_init()

    # ------------------------------------------------------------------
    # Current Sprint Management
    # ------------------------------------------------------------------

    def get_current_sprint(self) -> Sprint:
        """Lấy sprint hiện tại."""
        if self._current_sprint is None:
            self._load_or_init()
        return self._current_sprint

    def update_sprint_event(
        self,
        event_type: str,
        scheduled_date: str,
        scheduled_time: str,
        meeting_link: str = "",
        created_by: str = "bot",
    ) -> SprintEvent:
        """
        Cập nhật hoặc tạo mới sự kiện sprint.

        Args:
            event_type: "review" | "planning" | "retro"
            scheduled_date: YYYY-MM-DD
            scheduled_time: HH:MM
        """
        sprint = self.get_current_sprint()

        # Xóa event cũ cùng loại nếu có
        sprint.events = [e for e in sprint.events if e.get("event_type") != event_type]

        event = SprintEvent(
            event_type=event_type,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            meeting_link=meeting_link,
            created_by=created_by,
            created_at=datetime.now(self.tz).strftime("%Y-%m-%d %H:%M"),
        )
        sprint.events.append(event.to_dict())
        self._save_current_sprint()

        logger.info(f"[SprintManager] Đã cập nhật {event_type}: {scheduled_date} {scheduled_time}")
        return event

    def advance_sprint(self) -> Sprint:
        """
        Kết thúc sprint hiện tại và tạo sprint mới.
        """
        old_sprint = self.get_current_sprint()
        old_sprint.state = SprintState.CLOSED
        self._archive_sprint(old_sprint)

        # Tính tên sprint mới
        try:
            num = int(old_sprint.name.split()[-1]) + 1
        except (ValueError, IndexError):
            num = 1
        new_name = f"Sprint {num}"

        # Tính ngày sprint mới
        old_end = datetime.strptime(old_sprint.end_date, "%Y-%m-%d").date()
        new_start = old_end + timedelta(days=1)
        new_end = new_start + timedelta(weeks=self.cfg.sprint.duration_weeks) - timedelta(days=1)

        new_sprint = Sprint(
            name=new_name,
            start_date=new_start.strftime("%Y-%m-%d"),
            end_date=new_end.strftime("%Y-%m-%d"),
            state=SprintState.ACTIVE,
            team_members=old_sprint.team_members,
        )
        self._current_sprint = new_sprint
        self._save_current_sprint()

        logger.info(f"[SprintManager] Sprint mới: {new_name} ({new_start} - {new_end})")
        return new_sprint

    def update_metrics(
        self,
        planned_points: int = None,
        completed_points: int = None,
        planned_tasks: int = None,
        completed_tasks: int = None,
    ) -> None:
        """Cập nhật metrics sprint."""
        sprint = self.get_current_sprint()
        if planned_points is not None:
            sprint.metrics["planned_points"] = planned_points
        if completed_points is not None:
            sprint.metrics["completed_points"] = completed_points
        if planned_tasks is not None:
            sprint.metrics["planned_tasks"] = planned_tasks
        if completed_tasks is not None:
            sprint.metrics["completed_tasks"] = completed_tasks
        self._save_current_sprint()

    # ------------------------------------------------------------------
    # Notification Helpers
    # ------------------------------------------------------------------

    def get_upcoming_events(self, days_ahead: int = 7) -> List[SprintEvent]:
        """Lấy các sự kiện sắp diễn ra trong N ngày tới."""
        sprint = self.get_current_sprint()
        upcoming = []
        for e in sprint.events:
            ev = SprintEvent.from_dict(e)
            days = ev.days_until()
            if 0 <= days <= days_ahead:
                upcoming.append(ev)
        return sorted(upcoming, key=lambda x: x.days_until())

    def should_send_prep_reminder(self, event_type: str = "review") -> tuple:
        """
        Kiểm tra có nên gửi nhắc nhở chuẩn bị không.

        Returns: (should_send: bool, days_until: int)
        """
        sprint = self.get_current_sprint()
        event = sprint.get_event(event_type)

        if not event:
            return False, -1

        days = event.days_until()

        # Nhắc tại: 7 ngày, 3 ngày, 1 ngày, ngày họp
        reminder_days = {7, 3, 1, 0}
        should_send = days in reminder_days

        return should_send, days

    def is_sprint_week_ending(self) -> bool:
        """Kiểm tra sprint có kết thúc trong tuần này không."""
        sprint = self.get_current_sprint()
        remaining = sprint.days_remaining()
        return 0 <= remaining <= 7

    def get_sprint_stats(self) -> Dict[str, Any]:
        """Lấy thống kê sprint hiện tại."""
        sprint = self.get_current_sprint()
        metrics = sprint.metrics

        planned = metrics.get("planned_points", 0)
        completed = metrics.get("completed_points", 0)
        velocity_pct = (completed / planned * 100) if planned > 0 else 0

        planned_tasks = metrics.get("planned_tasks", 0)
        completed_tasks = metrics.get("completed_tasks", 0)
        task_pct = (completed_tasks / planned_tasks * 100) if planned_tasks > 0 else 0

        return {
            "sprint_name": sprint.name,
            "days_remaining": sprint.days_remaining(),
            "is_active": sprint.is_active(),
            "state": sprint.state,
            "velocity_percent": round(velocity_pct, 1),
            "task_completion_percent": round(task_pct, 1),
            "planned_points": planned,
            "completed_points": completed,
            "planned_tasks": planned_tasks,
            "completed_tasks": completed_tasks,
            "upcoming_events": [e.to_dict() for e in self.get_upcoming_events()],
        }

    # ------------------------------------------------------------------
    # Persistence (JSON files)
    # ------------------------------------------------------------------

    def _load_or_init(self):
        """Load sprint hiện tại từ file hoặc khởi tạo từ config."""
        if self.CURRENT_SPRINT_FILE.exists():
            try:
                with open(self.CURRENT_SPRINT_FILE) as f:
                    data = json.load(f)
                    self._current_sprint = Sprint.from_dict(data)
                    logger.info(f"[SprintManager] Loaded sprint: {self._current_sprint.name}")
                    return
            except Exception as e:
                logger.warning(f"[SprintManager] Lỗi load sprint file: {e}, khởi tạo từ config")

        # Khởi tạo từ config
        cfg = self.cfg.sprint
        end_date = cfg.end_date().strftime("%Y-%m-%d")
        self._current_sprint = Sprint(
            name=cfg.name,
            start_date=cfg.start_date,
            end_date=end_date,
            state=SprintState.ACTIVE,
            team_members=[],
        )
        self._save_current_sprint()
        logger.info(f"[SprintManager] Khởi tạo sprint mới: {self._current_sprint.name}")

    def _save_current_sprint(self):
        """Lưu sprint hiện tại vào file."""
        try:
            with open(self.CURRENT_SPRINT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._current_sprint.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[SprintManager] Lỗi lưu sprint: {e}")

    def _archive_sprint(self, sprint: Sprint):
        """Lưu sprint đã kết thúc vào lịch sử."""
        try:
            history = []
            if self.SPRINT_FILE.exists():
                with open(self.SPRINT_FILE) as f:
                    history = json.load(f)
            history.append(sprint.to_dict())
            with open(self.SPRINT_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logger.info(f"[SprintManager] Đã archive sprint: {sprint.name}")
        except Exception as e:
            logger.error(f"[SprintManager] Lỗi archive sprint: {e}")

    def get_sprint_history(self) -> List[Sprint]:
        """Lấy lịch sử tất cả sprints."""
        if not self.SPRINT_FILE.exists():
            return []
        try:
            with open(self.SPRINT_FILE) as f:
                data = json.load(f)
            return [Sprint.from_dict(d) for d in data]
        except Exception:
            return []
