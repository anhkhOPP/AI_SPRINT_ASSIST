"""
Cấu hình trung tâm cho AI Sprint Assistant.
Đọc từ biến môi trường (.env file).
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv

load_dotenv()


def _get_required(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Biến môi trường bắt buộc '{key}' chưa được cấu hình. "
            f"Vui lòng kiểm tra file .env"
        )
    return val


def _get_optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass
class GoogleChatConfig:
    webhook_url: str = field(default_factory=lambda: _get_required("GOOGLE_CHAT_WEBHOOK_URL"))
    alert_webhook_url: str = field(default_factory=lambda: _get_optional("GOOGLE_CHAT_ALERT_WEBHOOK_URL"))
    space_id: str = field(default_factory=lambda: _get_optional("GOOGLE_CHAT_SPACE_ID"))
    credentials_path: str = field(default_factory=lambda: _get_optional("GOOGLE_APPLICATION_CREDENTIALS", "./credentials/service_account.json"))


@dataclass
class InternalSiteConfig:
    logwork_url: str = field(default_factory=lambda: _get_optional("INTERNAL_LOGWORK_URL"))
    daily_url: str = field(default_factory=lambda: _get_optional("INTERNAL_DAILY_URL"))
    auth_type: str = field(default_factory=lambda: _get_optional("INTERNAL_AUTH_TYPE", "session_cookie"))
    username: str = field(default_factory=lambda: _get_optional("INTERNAL_USERNAME"))
    password: str = field(default_factory=lambda: _get_optional("INTERNAL_PASSWORD"))
    session_cookie: str = field(default_factory=lambda: _get_optional("INTERNAL_SESSION_COOKIE"))
    cookie_name: str = field(default_factory=lambda: _get_optional("INTERNAL_COOKIE_NAME", "JSESSIONID"))
    oauth_token: str = field(default_factory=lambda: _get_optional("INTERNAL_OAUTH_TOKEN"))


@dataclass
class ScheduleConfig:
    timezone: str = field(default_factory=lambda: _get_optional("TIMEZONE", "Asia/Ho_Chi_Minh"))
    daily_meeting_time: str = field(default_factory=lambda: _get_optional("DAILY_MEETING_TIME", "09:10"))
    logwork_reminder_time: str = field(default_factory=lambda: _get_optional("LOGWORK_REMINDER_TIME", "17:30"))
    logwork_check_time: str = field(default_factory=lambda: _get_optional("LOGWORK_CHECK_TIME", "09:30"))
    daily_check_time: str = field(default_factory=lambda: _get_optional("DAILY_CHECK_TIME", "10:00"))
    sprint_review_ask_time: str = field(default_factory=lambda: _get_optional("SPRINT_REVIEW_ASK_TIME", "09:00"))
    sprint_planning_ask_time: str = field(default_factory=lambda: _get_optional("SPRINT_PLANNING_ASK_TIME", "09:00"))
    enable_weekend_reminders: bool = field(
        default_factory=lambda: _get_optional("ENABLE_WEEKEND_REMINDERS", "false").lower() == "true"
    )

    def get_tz(self) -> pytz.tzinfo.BaseTzInfo:
        return pytz.timezone(self.timezone)

    def parse_time(self, time_str: str):
        """Parse chuỗi HH:MM thành (hour, minute)."""
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])


@dataclass
class SprintConfig:
    current_sprint_start: str = field(
        default_factory=lambda: _get_optional("CURRENT_SPRINT_START", datetime.now().strftime("%Y-%m-%d"))
    )
    sprint_duration_weeks: int = field(
        default_factory=lambda: int(_get_optional("SPRINT_DURATION_WEEKS", "2"))
    )
    current_sprint_name: str = field(
        default_factory=lambda: _get_optional("CURRENT_SPRINT_NAME", "Sprint 1")
    )

    def get_sprint_end(self) -> datetime:
        start = datetime.strptime(self.current_sprint_start, "%Y-%m-%d")
        return start + timedelta(weeks=self.sprint_duration_weeks)

    def days_remaining(self) -> int:
        end = self.get_sprint_end()
        remaining = (end - datetime.now()).days
        return max(0, remaining)


@dataclass
class TeamConfig:
    members_raw: str = field(default_factory=lambda: _get_optional("TEAM_MEMBERS", ""))
    alert_threshold: int = field(
        default_factory=lambda: int(_get_optional("ALERT_THRESHOLD", "3"))
    )

    def get_members(self) -> List[dict]:
        """Parse danh sách thành viên từ env string."""
        if not self.members_raw:
            return []
        members = []
        for item in self.members_raw.split(";"):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                name, email = item.split(":", 1)
                members.append({"name": name.strip(), "email": email.strip()})
            else:
                members.append({"name": item, "email": ""})
        return members


@dataclass
class BotServerConfig:
    host: str = field(default_factory=lambda: _get_optional("BOT_SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_get_optional("BOT_SERVER_PORT", "5000")))
    secret_token: str = field(default_factory=lambda: _get_optional("BOT_SECRET_TOKEN", ""))


@dataclass
class DatabaseConfig:
    database_url: str = field(
        default_factory=lambda: _get_optional("DATABASE_URL", "sqlite:///./data/sprint_assistant.db")
    )


@dataclass
class AppConfig:
    google_chat: GoogleChatConfig = field(default_factory=GoogleChatConfig)
    internal_site: InternalSiteConfig = field(default_factory=InternalSiteConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    sprint: SprintConfig = field(default_factory=SprintConfig)
    team: TeamConfig = field(default_factory=TeamConfig)
    bot_server: BotServerConfig = field(default_factory=BotServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


_config_instance: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Singleton config - chỉ load một lần."""
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
    return _config_instance
