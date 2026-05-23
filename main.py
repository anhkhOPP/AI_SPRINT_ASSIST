"""
AI Sprint Assistant - Entry Point

Cách chạy:
  python main.py                     # Chạy đầy đủ (scheduler + webhook server)
  python main.py --scheduler-only    # Chỉ scheduler
  python main.py --test <task_id>    # Test ngay một task
  python main.py --status            # Xem trạng thái sprint

Các task_id để test:
  daily_meeting   - Nhắc họp daily
  logwork_reminder - Nhắc log work
  check_logwork   - Check ai chưa log work hôm qua
  check_daily     - Check ai chưa điền daily
  ask_review      - Hỏi PM lịch Sprint Review (DM)
  ask_planning    - Hỏi PM lịch Sprint Planning (DM)
  review_prep     - Nhắc chuẩn bị Sprint Review
"""
import sys
import time
import signal
import threading
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# Cấu hình logger
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>",
    level="INFO",
)
import os as _os
_log_file = "/var/log/sprint-bot/app.log" if _os.path.isdir("/var/log/sprint-bot") else "logs/sprint_assistant.log"
logger.add(
    _log_file,
    rotation="50 MB",
    retention="30 days",
    compression="gz",
    level="DEBUG",
    encoding="utf-8",
)

# Tạo thư mục cần thiết
for d in ["logs", "data", "credentials"]:
    Path(d).mkdir(exist_ok=True)


BANNER = """
╔══════════════════════════════════════════════════════╗
║        🤖  AI SPRINT ASSISTANT  🤖                   ║
╠══════════════════════════════════════════════════════╣
║  09:00 Thứ 2  → Hỏi PM lịch Sprint Planning (DM)    ║
║  09:00 Thứ 5  → Hỏi PM lịch Sprint Review (DM)      ║
║  09:10 T2-T6  → Nhắc họp Daily (group)              ║
║  09:30 T2-T6  → Check Log Work hôm qua (group)      ║
║  10:00 T2-T6  → Check Daily Standup (group)         ║
║  16:00 T2-T6  → Nhắc chuẩn bị Sprint Review         ║
║  17:30 T2-T6  → Nhắc Log Work cuối ngày (group)     ║
╚══════════════════════════════════════════════════════╝
"""


def run_full(scheduler_only: bool = False):
    from config import get_config
    from src.scheduler.tasks import TaskScheduler

    print(BANNER)
    cfg = get_config()

    logger.info(f"Sprint hiện tại : {cfg.sprint.name}")
    logger.info(f"Trang nội bộ    : {cfg.internal.base_url}")
    logger.info(f"Ngưỡng log work : {cfg.internal.logwork_min_hours}h/ngày")
    logger.info(f"Webhook group   : {'✅' if cfg.google_chat.group_webhook_url else '❌ Chưa cấu hình'}")
    logger.info(f"Webhook PM (DM) : {'✅' if cfg.google_chat.pm_webhook_url else '⚠️  Chưa cấu hình'}")

    scheduler = TaskScheduler()
    scheduler.start()

    if not scheduler_only:
        from src.bot.webhook_server import run_server
        thread = threading.Thread(target=run_server, name="WebhookServer", daemon=True)
        thread.start()
        logger.info(f"Webhook server  : http://{cfg.bot_server.host}:{cfg.bot_server.port}")

    def shutdown(sig, frame):
        logger.info("Đang dừng bot...")
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("✅ Bot đang chạy. Nhấn Ctrl+C để dừng.\n")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()


def run_test(task_id: str):
    from src.scheduler.tasks import TaskScheduler
    logger.info(f"🧪 Test task: {task_id}")
    scheduler = TaskScheduler()
    scheduler.run_now(task_id)


def run_status():
    from config import get_config
    from src.sprint.manager import SprintManager

    cfg = get_config()
    mgr = SprintManager()
    sprint = mgr.get_current_sprint()
    stats = mgr.get_sprint_stats()

    print(f"\n{'='*50}")
    print(f"📊 Sprint: {sprint.name}")
    print(f"{'='*50}")
    print(f"  Bắt đầu : {sprint.start_date}")
    print(f"  Kết thúc: {sprint.end_date}")
    print(f"  Còn lại : {stats['days_remaining']} ngày")
    print(f"  Velocity: {stats['velocity_percent']}%")
    if stats.get("upcoming_events"):
        print(f"\n  Sự kiện sắp tới:")
        for ev in stats["upcoming_events"]:
            print(f"    • {ev['event_type'].upper()}: {ev['scheduled_date']} {ev['scheduled_time']}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="AI Sprint Assistant")
    parser.add_argument("--scheduler-only", action="store_true")
    parser.add_argument("--test", metavar="TASK_ID")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.test:
        run_test(args.test)
    elif args.status:
        run_status()
    else:
        run_full(scheduler_only=args.scheduler_only)


if __name__ == "__main__":
    main()
