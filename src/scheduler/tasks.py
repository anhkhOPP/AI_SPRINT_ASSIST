"""
Scheduler - Quản lý tất cả tác vụ định kỳ.

Sử dụng APScheduler với CronTrigger để chạy đúng giờ theo múi giờ Việt Nam.

Lịch mặc định:
- 09:10 T2-T6: Nhắc họp daily
- 09:30 T2-T6: Kiểm tra log work hôm qua
- 10:00 T2-T6: Kiểm tra daily standup
- 17:30 T2-T6: Nhắc log work
- 09:00 Thứ 5: Hỏi lịch sprint review
- 09:00 Thứ 2: Hỏi lịch sprint planning
- 16:00 hàng ngày: Kiểm tra nhắc nhở sprint review
- 08:30 T6: Tổng kết tuần
- 08:00 hàng ngày: Morning digest
"""
import traceback
from datetime import date, datetime, timedelta
from typing import Optional

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
    """
    Quản lý và chạy tất cả scheduled tasks.

    Mỗi task được đăng ký với CronTrigger theo timezone VN.
    Task chạy fail sẽ được log lại nhưng không crash app.
    """

    def __init__(self):
        cfg = get_config()
        self.cfg = cfg
        self.tz = cfg.schedule.get_tz()

        # Khởi tạo các components
        self.bot = GoogleChatBot()
        self.logwork_scraper = LogworkScraper()
        self.daily_scraper = DailyScraper()
        self.sprint_manager = SprintManager()
        self.templates = MessageTemplates()

        # APScheduler
        self.scheduler = BackgroundScheduler(timezone=self.tz)
        self.scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)

        self._register_all_tasks()

    def start(self):
        """Khởi động scheduler."""
        self.scheduler.start()
        logger.info("[Scheduler] ✅ Đã khởi động tất cả scheduled tasks")
        self._log_jobs()

    def stop(self):
        """Dừng scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Đã dừng scheduler")

    # ------------------------------------------------------------------
    # Register All Tasks
    # ------------------------------------------------------------------

    def _register_all_tasks(self):
        """Đăng ký tất cả scheduled tasks."""
        sched = self.cfg.schedule

        # Parse giờ từ config
        daily_h, daily_m = sched.parse_time(sched.daily_meeting_time)
        logwork_h, logwork_m = sched.parse_time(sched.logwork_reminder_time)
        check_logwork_h, check_logwork_m = sched.parse_time(sched.logwork_check_time)
        check_daily_h, check_daily_m = sched.parse_time(sched.daily_check_time)
        review_ask_h, review_ask_m = sched.parse_time(sched.sprint_review_ask_time)
        planning_ask_h, planning_ask_m = sched.parse_time(sched.sprint_planning_ask_time)

        weekdays = "mon-fri"

        # 1. Nhắc họp daily (9:10 T2-T6)
        self.scheduler.add_job(
            self.task_daily_meeting_reminder,
            CronTrigger(day_of_week=weekdays, hour=daily_h, minute=daily_m, timezone=self.tz),
            id="daily_meeting_reminder",
            name="Nhắc họp Daily",
            replace_existing=True,
            misfire_grace_time=60,
        )

        # 2. Kiểm tra log work hôm qua (9:30 T2-T6)
        self.scheduler.add_job(
            self.task_check_logwork,
            CronTrigger(day_of_week=weekdays, hour=check_logwork_h, minute=check_logwork_m, timezone=self.tz),
            id="check_logwork",
            name="Kiểm tra Log Work",
            replace_existing=True,
            misfire_grace_time=120,
        )

        # 3. Kiểm tra daily standup (10:00 T2-T6)
        self.scheduler.add_job(
            self.task_check_daily_standup,
            CronTrigger(day_of_week=weekdays, hour=check_daily_h, minute=check_daily_m, timezone=self.tz),
            id="check_daily_standup",
            name="Kiểm tra Daily Standup",
            replace_existing=True,
            misfire_grace_time=120,
        )

        # 4. Nhắc log work cuối ngày (17:30 T2-T6)
        self.scheduler.add_job(
            self.task_logwork_reminder,
            CronTrigger(day_of_week=weekdays, hour=logwork_h, minute=logwork_m, timezone=self.tz),
            id="logwork_reminder",
            name="Nhắc Log Work Cuối Ngày",
            replace_existing=True,
            misfire_grace_time=120,
        )

        # 5. Hỏi lịch Sprint Review (Thứ 5, 9:00)
        self.scheduler.add_job(
            self.task_ask_sprint_review,
            CronTrigger(day_of_week="thu", hour=review_ask_h, minute=review_ask_m, timezone=self.tz),
            id="ask_sprint_review",
            name="Hỏi lịch Sprint Review",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # 6. Hỏi lịch Sprint Planning (Thứ 2, 9:00)
        self.scheduler.add_job(
            self.task_ask_sprint_planning,
            CronTrigger(day_of_week="mon", hour=planning_ask_h, minute=planning_ask_m, timezone=self.tz),
            id="ask_sprint_planning",
            name="Hỏi lịch Sprint Planning",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # 7. Kiểm tra & nhắc chuẩn bị Sprint Review (16:00 hàng ngày)
        self.scheduler.add_job(
            self.task_sprint_review_prep_reminder,
            CronTrigger(day_of_week=weekdays, hour=16, minute=0, timezone=self.tz),
            id="sprint_review_prep",
            name="Nhắc Chuẩn Bị Sprint Review",
            replace_existing=True,
            misfire_grace_time=300,
        )

        # 8. Tổng kết tuần (Thứ 6, 8:30)
        self.scheduler.add_job(
            self.task_weekly_summary,
            CronTrigger(day_of_week="fri", hour=8, minute=30, timezone=self.tz),
            id="weekly_summary",
            name="Tổng kết tuần",
            replace_existing=True,
        )

        # 9. Morning digest (8:00 T2-T6)
        self.scheduler.add_job(
            self.task_morning_digest,
            CronTrigger(day_of_week=weekdays, hour=8, minute=0, timezone=self.tz),
            id="morning_digest",
            name="Morning Digest",
            replace_existing=True,
        )

        # 10. Kiểm tra nguy cơ trễ deadline (15:00 T4, T5)
        self.scheduler.add_job(
            self.task_deadline_warning,
            CronTrigger(day_of_week="wed,thu", hour=15, minute=0, timezone=self.tz),
            id="deadline_warning",
            name="Cảnh Báo Deadline",
            replace_existing=True,
        )

        logger.info(f"[Scheduler] Đã đăng ký {len(self.scheduler.get_jobs())} tasks")

    # ------------------------------------------------------------------
    # Task Implementations
    # ------------------------------------------------------------------

    def task_daily_meeting_reminder(self):
        """Task 1: Nhắc họp daily standup."""
        try:
            logger.info("[Task] Gửi nhắc họp daily")
            msg = MessageTemplates.daily_meeting_reminder()
            self.bot.send_text(msg)
        except Exception as e:
            logger.error(f"[Task:daily_meeting] Lỗi: {e}")

    def task_logwork_reminder(self):
        """Task 4: Nhắc log work cuối ngày."""
        try:
            logger.info("[Task] Gửi nhắc log work")
            msg = MessageTemplates.logwork_reminder()
            self.bot.send_text(msg)
        except Exception as e:
            logger.error(f"[Task:logwork_reminder] Lỗi: {e}")

    def task_check_logwork(self):
        """Task 2: Kiểm tra ai chưa log work hôm qua."""
        try:
            logger.info("[Task] Kiểm tra log work hôm qua")

            # Hôm qua (bỏ qua cuối tuần)
            yesterday = date.today() - timedelta(days=1)
            if yesterday.weekday() >= 5:
                yesterday = yesterday - timedelta(days=yesterday.weekday() - 4)

            missing = self.logwork_scraper.get_missing_users(yesterday)
            logger.info(f"[Task:check_logwork] Người chưa log work: {missing}")

            msg = MessageTemplates.missing_logwork_report(missing, yesterday)
            self.bot.send_text(msg)

            # Gửi alert riêng nếu quá nhiều người chưa log
            threshold = self.cfg.team.alert_threshold
            if len(missing) >= threshold:
                self.bot.send_alert(
                    f"*{len(missing)} người* chưa log work hôm qua ({yesterday.strftime('%d/%m/%Y')})!\n"
                    "Cần follow up ngay! 🚨"
                )
        except Exception as e:
            logger.error(f"[Task:check_logwork] Lỗi: {e}\n{traceback.format_exc()}")

    def task_check_daily_standup(self):
        """Task 3: Kiểm tra ai chưa điền daily standup."""
        try:
            logger.info("[Task] Kiểm tra daily standup hôm nay")

            missing = self.daily_scraper.get_missing_users()
            logger.info(f"[Task:check_daily] Người chưa điền: {missing}")

            msg = MessageTemplates.missing_daily_report(missing)
            self.bot.send_text(msg)
        except Exception as e:
            logger.error(f"[Task:check_daily] Lỗi: {e}\n{traceback.format_exc()}")

    def task_ask_sprint_review(self):
        """Task 5: Hỏi lịch sprint review (Thứ 5)."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            logger.info(f"[Task] Hỏi lịch sprint review - {sprint.name}")

            # Kiểm tra đã có lịch chưa
            existing_event = sprint.get_event("review")
            if existing_event and existing_event.days_until() > 0:
                logger.info(f"[Task:ask_review] Sprint review đã được lên lịch: {existing_event.scheduled_date}")
                # Vẫn nhắc nếu sắp đến
                if existing_event.days_until() <= 7:
                    self.task_sprint_review_prep_reminder()
                return

            msg = MessageTemplates.sprint_review_ask(sprint.name)
            self.bot.send_text(msg)
        except Exception as e:
            logger.error(f"[Task:ask_review] Lỗi: {e}")

    def task_ask_sprint_planning(self):
        """Task 6: Hỏi lịch sprint planning (Thứ 2)."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            logger.info(f"[Task] Hỏi lịch sprint planning")

            # Tính tên sprint tiếp theo
            try:
                num = int(sprint.name.split()[-1]) + 1
                next_name = f"Sprint {num}"
            except (ValueError, IndexError):
                next_name = "tiếp theo"

            # Kiểm tra có đang ở tuần cuối sprint không
            if self.sprint_manager.is_sprint_week_ending():
                msg = MessageTemplates.sprint_planning_ask(next_name)
                self.bot.send_text(msg)
            else:
                logger.info(f"[Task:ask_planning] Sprint chưa kết thúc, bỏ qua (còn {sprint.days_remaining()} ngày)")
        except Exception as e:
            logger.error(f"[Task:ask_planning] Lỗi: {e}")

    def task_sprint_review_prep_reminder(self):
        """Task 7: Nhắc chuẩn bị trước sprint review."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            review_event = sprint.get_event("review")

            if not review_event:
                logger.debug("[Task:review_prep] Chưa có lịch sprint review")
                return

            days_until = review_event.days_until()

            # Chỉ nhắc ở các mốc quan trọng
            reminder_days = {7, 3, 1, 0}
            if days_until not in reminder_days:
                return

            review_date = datetime.strptime(review_event.scheduled_date, "%Y-%m-%d")
            date_display = review_date.strftime("%d/%m/%Y") + f" {review_event.scheduled_time}"

            logger.info(f"[Task] Nhắc chuẩn bị sprint review - còn {days_until} ngày")
            msg = MessageTemplates.sprint_review_prep(sprint.name, date_display, days_until)
            self.bot.send_text(msg)

        except Exception as e:
            logger.error(f"[Task:review_prep] Lỗi: {e}")

    def task_weekly_summary(self):
        """Task 8: Tổng kết tuần (Thứ 6)."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            stats = self.sprint_manager.get_sprint_stats()

            logger.info("[Task] Gửi tổng kết tuần")
            msg = MessageTemplates.weekly_summary(
                sprint_name=sprint.name,
                days_remaining=stats["days_remaining"],
                top_contributors=[],
            )
            self.bot.send_text(msg)
        except Exception as e:
            logger.error(f"[Task:weekly_summary] Lỗi: {e}")

    def task_morning_digest(self):
        """Task 9: Morning digest đầu ngày."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            stats = self.sprint_manager.get_sprint_stats()

            logger.info("[Task] Gửi morning digest")
            msg = MessageTemplates.morning_digest(
                sprint_name=sprint.name,
                days_remaining=stats["days_remaining"],
                tasks_in_progress=stats.get("planned_tasks", 0) - stats.get("completed_tasks", 0),
                tasks_done=stats.get("completed_tasks", 0),
                blockers=[],
            )
            self.bot.send_text(msg)
        except Exception as e:
            logger.error(f"[Task:morning_digest] Lỗi: {e}")

    def task_deadline_warning(self):
        """Task 10: Cảnh báo nguy cơ trễ deadline."""
        try:
            sprint = self.sprint_manager.get_current_sprint()
            days_remaining = sprint.days_remaining()

            # Chỉ cảnh báo khi gần hết sprint (< 3 ngày)
            if days_remaining > 3:
                return

            stats = self.sprint_manager.get_sprint_stats()
            velocity = stats.get("velocity_percent", 100)

            if velocity < 70:
                logger.info(f"[Task] Cảnh báo deadline - velocity {velocity}%")
                msg = MessageTemplates.overtime_warning(
                    sprint.name,
                    [f"Velocity thấp: {velocity}% - Còn {days_remaining} ngày"]
                )
                self.bot.send_alert(msg)
        except Exception as e:
            logger.error(f"[Task:deadline_warning] Lỗi: {e}")

    # ------------------------------------------------------------------
    # Manual Trigger (for testing)
    # ------------------------------------------------------------------

    def run_task_now(self, task_id: str) -> bool:
        """Chạy ngay một task theo ID (dùng để test)."""
        task_map = {
            "daily_meeting": self.task_daily_meeting_reminder,
            "logwork_reminder": self.task_logwork_reminder,
            "check_logwork": self.task_check_logwork,
            "check_daily": self.task_check_daily_standup,
            "ask_review": self.task_ask_sprint_review,
            "ask_planning": self.task_ask_sprint_planning,
            "review_prep": self.task_sprint_review_prep_reminder,
            "weekly_summary": self.task_weekly_summary,
            "morning_digest": self.task_morning_digest,
        }

        task_fn = task_map.get(task_id)
        if not task_fn:
            logger.error(f"[Scheduler] Không tìm thấy task: {task_id}")
            return False

        logger.info(f"[Scheduler] Chạy ngay task: {task_id}")
        task_fn()
        return True

    # ------------------------------------------------------------------
    # Event Listeners
    # ------------------------------------------------------------------

    def _on_job_error(self, event):
        logger.error(
            f"[Scheduler] ❌ Job '{event.job_id}' thất bại: {event.exception}\n"
            f"{traceback.format_tb(event.traceback)}"
        )

    def _on_job_executed(self, event):
        logger.debug(f"[Scheduler] ✅ Job '{event.job_id}' hoàn thành")

    def _log_jobs(self):
        """Log danh sách tất cả jobs đã đăng ký."""
        logger.info("[Scheduler] Danh sách tác vụ đã đăng ký:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.id}: {job.name} | Next: {job.next_run_time}")
