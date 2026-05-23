"""
Cấu hình trung tâm - đọc từ file .env
"""
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

import pytz
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Biến môi trường bắt buộc '{key}' chưa được cấu hình. Kiểm tra file .env"
        )
    return val


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ------------------------------------------------------------------
# Google Chat
# ------------------------------------------------------------------

@dataclass
class GoogleChatConfig:
    # Webhook gửi vào group nhóm
    group_webhook_url: str = field(
        default_factory=lambda: _require("GOOGLE_CHAT_WEBHOOK_URL")
    )
    # Webhook gửi DM riêng cho PM
    pm_webhook_url: str = field(
        default_factory=lambda: _get("GOOGLE_CHAT_PM_WEBHOOK_URL")
    )


# ------------------------------------------------------------------
# Trang nội bộ op_pm
# ------------------------------------------------------------------

@dataclass
class InternalSiteConfig:
    base_url: str = field(
        default_factory=lambda: _get("INTERNAL_BASE_URL", "https://10.36.36.63:8618/op_pm")
    )
    login_url: str = field(
        default_factory=lambda: _get("INTERNAL_LOGIN_URL")
    )
    username: str = field(
        default_factory=lambda: _require("INTERNAL_USERNAME")
    )
    password: str = field(
        default_factory=lambda: _require("INTERNAL_PASSWORD")
    )
    login_field_username: str = field(
        default_factory=lambda: _get("INTERNAL_LOGIN_FIELD_USERNAME", "username")
    )
    login_field_password: str = field(
        default_factory=lambda: _get("INTERNAL_LOGIN_FIELD_PASSWORD", "password")
    )
    worklog_url: str = field(
        default_factory=lambda: _get("INTERNAL_WORKLOG_URL")
    )
    daily_parent_url: str = field(
        default_factory=lambda: _get("INTERNAL_DAILY_PARENT_URL")
    )
    logwork_min_hours: float = field(
        default_factory=lambda: float(_get("LOGWORK_MIN_HOURS", "7.5"))
    )

    def get_login_url(self) -> str:
        """Trả về login URL, tự suy ra nếu chưa cấu hình."""
        if self.login_url:
            return self.login_url
        return self.base_url.rstrip("/") + "/login"


# ------------------------------------------------------------------
# Lịch
# ------------------------------------------------------------------

@dataclass
class ScheduleConfig:
    timezone: str = field(
        default_factory=lambda: _get("TIMEZONE", "Asia/Ho_Chi_Minh")
    )
    daily_meeting_time: str = field(
        default_factory=lambda: _get("DAILY_MEETING_TIME", "09:10")
    )
    logwork_check_time: str = field(
        default_factory=lambda: _get("LOGWORK_CHECK_TIME", "09:30")
    )
    daily_check_time: str = field(
        default_factory=lambda: _get("DAILY_CHECK_TIME", "10:00")
    )
    logwork_reminder_time: str = field(
        default_factory=lambda: _get("LOGWORK_REMINDER_TIME", "17:30")
    )
    sprint_review_ask_time: str = field(
        default_factory=lambda: _get("SPRINT_REVIEW_ASK_TIME", "09:00")
    )
    sprint_planning_ask_time: str = field(
        default_factory=lambda: _get("SPRINT_PLANNING_ASK_TIME", "09:00")
    )

    def get_tz(self) -> pytz.BaseTzInfo:
        return pytz.timezone(self.timezone)

    def parse_time(self, time_str: str):
        h, m = time_str.split(":")
        return int(h), int(m)


# ------------------------------------------------------------------
# Sprint
# ------------------------------------------------------------------

@dataclass
class SprintConfig:
    name: str = field(
        default_factory=lambda: _get("CURRENT_SPRINT_NAME", "Sprint 1")
    )
    start_date: str = field(
        default_factory=lambda: _get("CURRENT_SPRINT_START", datetime.now().strftime("%Y-%m-%d"))
    )
    duration_weeks: int = field(
        default_factory=lambda: int(_get("SPRINT_DURATION_WEEKS", "2"))
    )

    def end_date(self) -> datetime:
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        return start + timedelta(weeks=self.duration_weeks)

    def days_remaining(self) -> int:
        remaining = (self.end_date() - datetime.now()).days
        return max(0, remaining)


# ------------------------------------------------------------------
# Bot Server
# ------------------------------------------------------------------

@dataclass
class BotServerConfig:
    host: str = field(default_factory=lambda: _get("BOT_SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_get("BOT_SERVER_PORT", "5000")))
    secret_token: str = field(default_factory=lambda: _get("BOT_SECRET_TOKEN", ""))
    public_url: str = field(default_factory=lambda: _get("BOT_PUBLIC_URL", ""))


# ------------------------------------------------------------------
# App Config (tổng hợp)
# ------------------------------------------------------------------

@dataclass
class GeminiConfig:
    api_key: str = field(default_factory=lambda: _get("GEMINI_API_KEY", ""))
    model: str = field(default_factory=lambda: _get("GEMINI_MODEL", "gemini-2.0-flash"))

    def is_enabled(self) -> bool:
        return bool(self.api_key)


@dataclass
class AppConfig:
    google_chat: GoogleChatConfig = field(default_factory=GoogleChatConfig)
    internal: InternalSiteConfig = field(default_factory=InternalSiteConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    sprint: SprintConfig = field(default_factory=SprintConfig)
    bot_server: BotServerConfig = field(default_factory=BotServerConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    alert_threshold: int = field(
        default_factory=lambda: int(_get("ALERT_THRESHOLD", "3"))
    )


_instance: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _instance
    if _instance is None:
        _instance = AppConfig()
    return _instance
