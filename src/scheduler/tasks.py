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
             "Nhắc chuẩn bị Sprint Review"),

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

        logger.info(f"[Scheduler] Đã đăng ký {len(jobs)} jobs")

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def task_daily_meeting_reminder(self):
        """09:10 T2-T6 - Nhắc họp daily vào group."""
        try:
            msg = MessageTemplates.daily_meeting_reminder()
            self.bot.notify_daily_meeting(msg)
            logger.info("[Task] ✅ Nhắc họp daily")
        except Exception as e:
            logger.error(f"[Task:daily_meeting] {e}")

    def task_logwork_reminder(self):
        """17:30 T2-T6 - Nhắc log work cuối ngày vào group."""
        try:
            min_hours = self.cfg.internal.logwork_min_hours
            msg = MessageTemplates.logwork_reminder(min_hours)
            self.bot.notify_logwork_reminder(msg)
            logger.info("[Task] ✅ Nhắc log work")
        except Exception as e:
            logger.error(f"[Task:logwork_reminder] {e}")

    def task_check_logwork(self):
        """09:30 T2-T6 - Check ai chưa log đủ giờ hôm qua."""
        try:
            logger.info("[Task] Check log work hôm qua...")
            result = self.logwork.fetch_logwork_data()
            missing = result.get("missing", [])
            min_hours = self.cfg.internal.logwork_min_hours

            # Xác định ngày hôm qua (bỏ cuối tuần)
            yesterday = date.today() - timedelta(days=1)
            if yesterday.weekday() >= 5:
                yesterday -= timedelta(days=yesterday.weekday() - 4)

            msg = MessageTemplates.missing_logwork_report(missing, min_hours, yesterday)
            self.bot.notify_missing_logwork(msg)

            # Cảnh báo thêm nếu quá nhiều người thiếu
            if len(missing) >= self.cfg.alert_threshold:
                self.bot.send_group(
                    f"🚨 Có *{len(missing)} người* chưa log work đủ giờ!\n"
                    "PM/Lead cần follow up ngay!"
                )
            logger.info(f"[Task] ✅ Check logwork: {len(missing)} thiếu")
        except Exception as e:
            logger.error(f"[Task:check_logwork] {e}\n{traceback.format_exc()}")

    def task_check_daily(self):
        """10:00 T2-T6 - Check ai chưa điền daily + tóm tắt AI."""
        try:
            logger.info("[Task] Check daily standup...")
            result = self.daily.fetch_daily_data()
            missing = result.get("missing", [])
            entries = result.get("entries", [])

            # Báo ai chưa điền
            msg = MessageTemplates.missing_daily_report(missing)
            self.bot.notify_missing_daily(msg)

            # Tóm tắt AI (chỉ khi có đủ người điền)
            submitted_entries = [e for e in entries if e.get("submitted")]
            if submitted_entries:
                self._task_ai_daily_summary(submitted_entries)

            logger.info(f"[Task] ✅ Check daily: {len(missing)} chưa điền")
        except Exception as e:
            logger.error(f"[Task:check_daily] {e}\n{traceback.format_exc()}")

    def _task_ai_daily_summary(self, entries: list):
        """Tóm tắt nội dung daily bằng AI và gửi vào group."""
        try:
            from src.ai.gemini import GeminiAI
            ai = GeminiAI()

            if not ai.enabled:
                return

            sprint = self.sprint_manager.get_current_sprint()
            summary = ai.summarize_daily(
                entries=entries,
                sprint_name=sprint.name,
                days_remaining=sprint.days_remaining(),
            )

            if summary and summary.strip() != "✅ Daily bình thường, không có blockers.":
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
                logger.info(f"[Task] Sprint Review đã có lịch: {existing.scheduled_date}, bỏ qua")
                return

            public_url = self.cfg.bot_server.public_url
            msg = MessageTemplates.ask_pm_sprint_review(sprint.name, public_url)
            self.bot.ask_pm_sprint_review(msg)
            logger.info("[Task] ✅ Đã hỏi PM lịch Sprint Review qua DM")
        except Exception as e:
            logger.error(f"[Task:ask_review] {e}")

    def task_ask_sprint_planning(self):
        """Thứ 2 09:00 - Hỏi PM lịch Sprint Planning qua DM."""
        try:
            sprint = self.sprint_manager.get_current_sprint()

            # Chỉ hỏi khi đang trong tuần cuối sprint
            if not self.sprint_manager.is_sprint_week_ending():
                logger.info(f"[Task] Sprint chưa gần kết thúc (còn {sprint.days_remaining()} ngày), bỏ qua")
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
            logger.info("[Task] ✅ Đã hỏi PM lịch Sprint Planning qua DM")
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
            logger.info(f"[Task] ✅ Nhắc chuẩn bị Sprint Review (còn {days_until} ngày)")
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
            logger.error(f"Task không tồn tại: {task_id}. Có: {list(tasks.keys())}")
            return False
        logger.info(f"[Scheduler] Chạy ngay: {task_id}")
        fn()
        return True

    def _on_error(self, event):
        logger.error(f"[Scheduler] ❌ Job '{event.job_id}' lỗi: {event.exception}")
