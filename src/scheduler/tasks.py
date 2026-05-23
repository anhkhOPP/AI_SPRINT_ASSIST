"""
Scheduler - Tất cả tác vụ định kỳ chạy theo lịch VN.

Lịch:
  09:00 Thứ 2  → Hỏi PM lịch Sprint Planning (DM)
  09:00 Thứ 5  → Hỏi PM lịch Sprint Review (DM)
  09:10 T2-T6  → Nhắc họp Daily (group)
  09:30 T2-T6  → Check log work hôm qua (group)
  10:00 T2-T6  → Check daily standup (group)
  16:00 T2-T6  → Kiểm tra nhắc chuẩn bị Sprint Review (group)
  17:30 T2-T6  → Nhắc log work cuối ngày (group)
"""
import traceback
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from loguru import logger

from config import get_config
from src.bot.google_chat import GoogleChatBot
from src.scrapers.logwork_scraper import LogworkScraper
from src.scrapers.daily_scraper import DailyScraper
from src.sprint.manager import SprintManager
from src.reminders.messages import MessageTemplates


class TaskScheduler:

    def __init__(self):
        self.cfg = get_config()
        self.tz = self.cfg.schedule.get_tz()
        self.bot = GoogleChatBot()
        self.logwork = LogworkScraper()
        self.daily = DailyScraper()
        self.sprint_manager = SprintManager()
        self.scheduler = BackgroundScheduler(timezone=self.tz)
        self.scheduler.add_listener(self._on_error, EVENT_JOB_ERROR)
        self._register_jobs()

    def start(self):
        self.scheduler.start()
        logger.info("[Scheduler] ✅ Đã khởi động")
        for job in self.scheduler.get_jobs():
            logger.info(f"  • {job.name} → next: {job.next_run_time}")

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Đã dừng")

    # ------------------------------------------------------------------
    # Đăng ký jobs
    # ------------------------------------------------------------------

    def _register_jobs(self):
        s = self.cfg.schedule
        tz = self.tz
        wd = "mon-fri"

        plan_h, plan_m = s.parse_time(s.sprint_planning_ask_time)
        rev_h, rev_m = s.parse_time(s.sprint_review_ask_time)
        daily_h, daily_m = s.parse_time(s.daily_meeting_time)
        check_lw_h, check_lw_m = s.parse_time(s.logwork_check_time)
        check_d_h, check_d_m = s.parse_time(s.daily_check_time)
        lw_h, lw_m = s.parse_time(s.logwork_reminder_time)

        jobs = [
            # Thứ 2: hỏi PM lịch Sprint Planning
            (self.task_ask_sprint_planning,
             CronTrigger(day_of_week="mon", hour=plan_h, minute=plan_m, timezone=tz),
             "Hỏi PM lịch Sprint Planning"),

            # Thứ 5: hỏi PM lịch Sprint Review
            (self.task_ask_sprint_review,
             CronTrigger(day_of_week="thu", hour=rev_h, minute=rev_m, timezone=tz),
             "Hỏi PM lịch Sprint Review"),

            # 09:10 T2-T6: nhắc họp daily
            (self.task_daily_meeting_reminder,
             CronTrigger(day_of_week=wd, hour=daily_h, minute=daily_m, timezone=tz),
             "Nhắc họp Daily"),

            # 09:30 T2-T6: check log work hôm qua
            (self.task_check_logwork,
             CronTrigger(day_of_week=wd, hour=check_lw_h, minute=check_lw_m, timezone=tz),
             "Check Log Work hôm qua"),

            # 10:00 T2-T6: check daily standup
            (self.task_check_daily,
             CronTrigger(day_of_week=wd, hour=check_d_h, minute=check_d_m, timezone=tz),
             "Check Daily Standup"),

            # 16:00 T2-T6: nhắc chuẩn bị sprint review
            (self.task_sprint_review_prep,
             CronTrigger(day_of_week=wd, hour=16, minute=0, timezone=tz),
             "Sprint Review prep reminder"),

            # 17:30 T2-T6: nhắc log work cuối ngày
            (self.task_logwork_reminder,
             CronTrigger(day_of_week=wd, hour=lw_h, minute=lw_m, timezone=tz),
             "Nhắc Log Work cuối ngày"),
        ]

        for fn, trigger, name in jobs:
            self.scheduler.add_job(
                fn, trigger,
                id=fn.__name__,
                name=name,
                replace_existing=True,
                misfire_grace_time=120,
            )

        logger.info(f"[Scheduler] Registered {len(jobs)} jobs")

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def task_daily_meeting_reminder(self):
        """09:10 T2-T6 - Nhắc họp daily (skip T7, CN)."""
        try:
            from src.utils.schedule_utils import WorkdayCalendar
            if not WorkdayCalendar.should_send_daily_reminder_today():
                logger.info("[Task] Daily reminder skipped (not a weekday)")
                return
            msg = MessageTemplates.daily_meeting_reminder()
            self.bot.notify_daily_meeting(msg)
            logger.info("[Task] ✅ Daily meeting reminder sent")
        except Exception as e:
            logger.error(f"[Task:daily_meeting] {e}")

    def task_logwork_reminder(self):
        """17:30 T2-T7 - Nhắc log work (T7 làm: nhắc 4h)."""
        try:
            from src.utils.schedule_utils import WorkdayCalendar
            if not WorkdayCalendar.should_send_logwork_reminder_today():
                logger.info("[Task] Logwork reminder skipped (day off)")
                return
            min_hours = WorkdayCalendar.get_min_hours(date.today())
            msg = MessageTemplates.logwork_reminder(min_hours)
            self.bot.notify_logwork_reminder(msg)
            logger.info(f"[Task] ✅ Logwork reminder sent (threshold: {min_hours}h)")
        except Exception as e:
            logger.error(f"[Task:logwork_reminder] {e}")

    def task_check_logwork(self):
        """09:30 T2-T6 - Check logwork ngày làm việc gần nhất.
        T2: check T7 (nếu T7 làm, threshold 4h) hoặc T6 (nếu T7 nghỉ, threshold 7.5h).
        """
        try:
            from src.utils.schedule_utils import WorkdayCalendar
            should_check, check_date, min_hours = WorkdayCalendar.should_check_logwork_today()

            if not should_check:
                logger.info("[Task] Logwork check skipped")
                return

            logger.info(f"[Task] Checking logwork for {WorkdayCalendar.describe_day(check_date)} ({check_date}), threshold: {min_hours}h")
            result = self.logwork.fetch_logwork_data(check_date)

            # Re-classify logged/missing với threshold đúng theo ngày
            all_members = result.get("logged", []) + result.get("missing", [])
            logged = [m for m in all_members if m.get("hours", 0) >= min_hours]
            missing = [m for m in all_members if m.get("hours", 0) < min_hours]

            msg = MessageTemplates.missing_logwork_report(missing, min_hours, check_date)
            self.bot.notify_missing_logwork(msg)

            if len(missing) >= self.cfg.alert_threshold:
                self.bot.send_group(
                    f"🚨 Có *{len(missing)} người* chưa log work đủ {min_hours}h!\n"
                    "PM/Lead cần follow up ngay!"
                )
            logger.info(f"[Task] ✅ Logwork check ({check_date}): {len(logged)} ok, {len(missing)} missing")
        except Exception as e:
            logger.error(f"[Task:check_logwork] {e}\n{traceback.format_exc()}")

    def task_check_daily(self):
        """10:00 T2-T6 - Check daily standup + AI summary (skip T7, CN)."""
        try:
            from src.utils.schedule_utils import WorkdayCalendar
            if not WorkdayCalendar.should_check_daily_today():
                logger.info("[Task] Daily check skipped (Saturday/Sunday)")
                return

            logger.info("[Task] Checking daily standup...")
            result = self.daily.fetch_daily_data()
            missing = result.get("missing", [])
            entries = result.get("entries", [])

            msg = MessageTemplates.missing_daily_report(missing)
            self.bot.notify_missing_daily(msg)

            submitted_entries = [e for e in entries if e.get("submitted")]
            if submitted_entries:
                self._task_ai_daily_summary(submitted_entries)

            logger.info(f"[Task] ✅ Daily check: {len(missing)} missing")
        except Exception as e:
            logger.error(f"[Task:check_daily] {e}\n{traceback.format_exc()}")

    def _task_ai_daily_summary(self, entries: list):
        """Tóm tắt nội dung daily bằng AI và gửi vào group."""
        try:
            from src.ai import get_ai
            ai = get_ai()

            if not ai.enabled:
                return

            sprint = self.sprint_manager.get_current_sprint()
            summary = ai.summarize_daily(
                entries=entries,
                sprint_name=sprint.name,
                days_remaining=sprint.days_remaining(),
            )

            if summary and summary.strip() != "✅ Daily bình thường, none blockers.":
                msg = f"🤖 *AI DAILY INSIGHT*\n\n{summary}"
                self.bot.send_group(msg)
                logger.info("[Task] ✅ Gửi AI daily summary")

        except Exception as e:
            logger.error(f"[Task:ai_summary] {e}")

    def task_ask_sprint_review(self):
        """Thứ 5 09:00 - Hỏi PM lịch Sprint Review qua DM."""
        try:
            sprint = self.sprint_manager.get_current_sprint()

            # Nếu đã có lịch và chưa đến ngày thì không hỏi lại
            existing = sprint.get_event("review")
            if existing and existing.days_until() > 0:
                logger.info(f"[Task] Sprint Review already scheduled: {existing.scheduled_date}, bỏ qua")
                return

            public_url = self.cfg.bot_server.public_url
            msg = MessageTemplates.ask_pm_sprint_review(sprint.name, public_url)
            self.bot.ask_pm_sprint_review(msg)
            logger.info("[Task] ✅ Asked PM for Sprint Review schedule via DM")
        except Exception as e:
            logger.error(f"[Task:ask_review] {e}")

    def task_ask_sprint_planning(self):
        """Thứ 2 09:00 - Hỏi PM lịch Sprint Planning qua DM."""
        try:
            sprint = self.sprint_manager.get_current_sprint()

            # Chỉ hỏi khi đang trong tuần cuối sprint
            if not self.sprint_manager.is_sprint_week_ending():
                logger.info(f"[Task] Sprint not ending soon (remaining {sprint.days_remaining()} ngày), bỏ qua")
                return

            # Tính tên sprint tiếp theo
            try:
                num = int(sprint.name.split()[-1]) + 1
                next_name = f"Sprint {num}"
            except (ValueError, IndexError):
                next_name = "tiếp theo"

            public_url = self.cfg.bot_server.public_url
            msg = MessageTemplates.ask_pm_sprint_planning(sprint.name, next_name, public_url)
            self.bot.ask_pm_sprint_planning(msg)
            logger.info("[Task] ✅ Asked PM for Sprint Planning schedule via DM")
        except Exception as e:
            logger.error(f"[Task:ask_planning] {e}")

    def task_sprint_review_prep(self):
        """16:00 T2-T6 - Nhắc nhóm chuẩn bị Sprint Review."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            should_send, days_until = self.sprint_manager.should_send_prep_reminder("review")

            if not should_send:
                return

            event = sprint.get_event("review")
            if not event:
                return

            from datetime import datetime
            review_date = datetime.strptime(event.scheduled_date, "%Y-%m-%d")
            date_display = review_date.strftime("%d/%m/%Y") + f" {event.scheduled_time}"

            meeting_room = getattr(event, "meeting_room", "")
            msg = MessageTemplates.sprint_review_prep(
                sprint.name, date_display, days_until, event.meeting_link, meeting_room
            )
            self.bot.notify_sprint_review_prep(msg)
            logger.info(f"[Task] ✅ Sprint Review prep reminder (remaining {days_until} ngày)")
        except Exception as e:
            logger.error(f"[Task:review_prep] {e}")

    # ------------------------------------------------------------------
    # Manual trigger (test)
    # ------------------------------------------------------------------

    def run_now(self, task_id: str) -> bool:
        """Chạy ngay một task để test."""
        tasks = {
            "daily_meeting": self.task_daily_meeting_reminder,
            "logwork_reminder": self.task_logwork_reminder,
            "check_logwork": self.task_check_logwork,
            "check_daily": self.task_check_daily,
            "ask_review": self.task_ask_sprint_review,
            "ask_planning": self.task_ask_sprint_planning,
            "review_prep": self.task_sprint_review_prep,
            "ai_summary": lambda: self._task_ai_daily_summary(
                self.daily.fetch_daily_data().get("entries", [])
            ),
        }
        fn = tasks.get(task_id)
        if not fn:
            logger.error(f"Task not found: {task_id}. Có: {list(tasks.keys())}")
            return False
        logger.info(f"[Scheduler] Chạy ngay: {task_id}")
        fn()
        return True

    def _on_error(self, event):
        logger.error(f"[Scheduler] ❌ Job '{event.job_id}' lỗi: {event.exception}")
