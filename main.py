"""
AI Sprint Assistant - Entry Point

Chạy bot theo hai chế độ:
1. `python main.py` - Chạy đầy đủ (scheduler + webhook server)
2. `python main.py --scheduler-only` - Chỉ chạy scheduler (không có webhook server)
3. `python main.py --test <task_id>` - Chạy ngay một task cụ thể để test
4. `python main.py --status` - Hiển thị trạng thái sprint hiện tại

Ví dụ:
  python main.py --test daily_meeting
  python main.py --test check_logwork
  python main.py --test ask_review
  python main.py --status
"""
import sys
import time
import signal
import threading
import argparse
import os
from pathlib import Path

# Thêm thư mục gốc vào Python path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# Cấu hình logger
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    "logs/sprint_assistant.log",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level="DEBUG",
    encoding="utf-8",
)

# Tạo thư mục cần thiết
Path("logs").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)
Path("credentials").mkdir(exist_ok=True)


def print_banner():
    banner = """
╔══════════════════════════════════════════════════════════════╗
║          🤖  AI SPRINT ASSISTANT  🤖                         ║
║          Trợ lý quản lý Sprint thông minh                    ║
║          Powered by Google Chat + APScheduler                ║
╠══════════════════════════════════════════════════════════════╣
║  📅 Daily Meeting Reminder     09:10  (Mon-Fri)              ║
║  🔍 Check Log Work Yesterday   09:30  (Mon-Fri)              ║
║  📝 Check Daily Standup        10:00  (Mon-Fri)              ║
║  ⏰ Log Work Reminder          17:30  (Mon-Fri)              ║
║  ❓ Ask Sprint Review          09:00  (Thursday)             ║
║  ❓ Ask Sprint Planning        09:00  (Monday)               ║
║  🚀 Sprint Review Prep         16:00  (Daily)                ║
║  📊 Weekly Summary             08:30  (Friday)               ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def run_full(args):
    """Chạy đầy đủ: scheduler + webhook server."""
    from config import get_config
    from src.scheduler.tasks import TaskScheduler

    print_banner()
    cfg = get_config()

    logger.info("🚀 Khởi động AI Sprint Assistant...")
    logger.info(f"  Timezone: {cfg.schedule.timezone}")
    logger.info(f"  Sprint: {cfg.sprint.current_sprint_name}")
    logger.info(f"  Webhook URL: {'✅ Đã cấu hình' if cfg.google_chat.webhook_url else '❌ Chưa cấu hình'}")

    # Khởi động scheduler
    scheduler = TaskScheduler()
    scheduler.start()

    # Khởi động webhook server nếu không phải scheduler-only
    if not args.scheduler_only:
        from src.bot.webhook_server import app, run_server

        server_thread = threading.Thread(
            target=run_server,
            name="WebhookServer",
            daemon=True,
        )
        server_thread.start()
        logger.info(f"🌐 Webhook server đang chạy tại http://{cfg.bot_server.host}:{cfg.bot_server.port}")

    # Handle graceful shutdown
    def shutdown(signum, frame):
        logger.info("🛑 Nhận tín hiệu dừng, shutdown gracefully...")
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("✅ AI Sprint Assistant đang chạy. Nhấn Ctrl+C để dừng.\n")

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("🛑 Đang dừng...")
        scheduler.stop()


def run_test(task_id: str):
    """Chạy ngay một task cụ thể để test."""
    from src.scheduler.tasks import TaskScheduler

    logger.info(f"🧪 Test task: {task_id}")
    scheduler = TaskScheduler()
    success = scheduler.run_task_now(task_id)

    if success:
        logger.info(f"✅ Task '{task_id}' đã chạy thành công!")
    else:
        logger.error(f"❌ Task '{task_id}' không tìm thấy. Các task có sẵn:")
        logger.error("  daily_meeting, logwork_reminder, check_logwork, check_daily")
        logger.error("  ask_review, ask_planning, review_prep, weekly_summary, morning_digest")


def run_status():
    """Hiển thị trạng thái sprint hiện tại."""
    from config import get_config
    from src.sprint.manager import SprintManager

    cfg = get_config()
    manager = SprintManager()
    sprint = manager.get_current_sprint()
    stats = manager.get_sprint_stats()

    print("\n" + "="*60)
    print(f"📊 TRẠNG THÁI SPRINT: {sprint.name}")
    print("="*60)
    print(f"  📅 Bắt đầu:    {sprint.start_date}")
    print(f"  🏁 Kết thúc:   {sprint.end_date}")
    print(f"  ⏳ Còn lại:    {stats['days_remaining']} ngày")
    print(f"  🎯 Trạng thái: {sprint.state}")
    print(f"  📈 Velocity:   {stats['velocity_percent']}%")
    print(f"  ✅ Tasks done: {stats['completed_tasks']}/{stats['planned_tasks']}")

    if stats.get("upcoming_events"):
        print(f"\n  📅 Sự kiện sắp tới:")
        for ev in stats["upcoming_events"]:
            print(f"    - {ev['event_type'].upper()}: {ev['scheduled_date']} {ev['scheduled_time']}")

    team_members = cfg.team.get_members()
    print(f"\n  👥 Team ({len(team_members)} người):")
    for m in team_members:
        print(f"    - {m['name']}" + (f" <{m['email']}>" if m['email'] else ""))

    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="AI Sprint Assistant - Trợ lý quản lý Sprint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scheduler-only",
        action="store_true",
        help="Chỉ chạy scheduler, không khởi động webhook server",
    )
    parser.add_argument(
        "--test",
        metavar="TASK_ID",
        help="Chạy ngay một task cụ thể (daily_meeting, check_logwork, ...)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Hiển thị trạng thái sprint hiện tại",
    )

    args = parser.parse_args()

    if args.test:
        run_test(args.test)
    elif args.status:
        run_status()
    else:
        run_full(args)


if __name__ == "__main__":
    main()
