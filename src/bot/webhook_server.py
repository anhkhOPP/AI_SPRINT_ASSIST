"""
Flask Webhook Server - Nhận reply từ PM qua Google Chat.

Khi PM reply trong Space riêng (DM-like), Google Chat gọi endpoint này.
PM dùng các lệnh:
  /set_review  DD/MM HH:MM [link]   → Lưu lịch Sprint Review
  /set_planning DD/MM HH:MM [link]  → Lưu lịch Sprint Planning
  /sprint                            → Xem thông tin sprint
  /help                              → Xem trợ giúp

QUAN TRỌNG: Webhook server cần public URL để Google Chat gọi được.
Nếu chạy trong mạng nội bộ, dùng ngrok hoặc Cloudflare Tunnel.
"""
import re
from datetime import datetime

from flask import Flask, request, jsonify
from loguru import logger

from config import get_config

app = Flask(__name__)
_sprint_manager = None


def get_sprint_manager():
    global _sprint_manager
    if _sprint_manager is None:
        from src.sprint.manager import SprintManager
        _sprint_manager = SprintManager()
    return _sprint_manager


# ------------------------------------------------------------------
# Xử lý tin nhắn từ PM
# ------------------------------------------------------------------

def handle_pm_message(text: str, sender: str) -> str:
    """
    Xử lý lệnh PM gửi vào Space riêng.
    Trả về text phản hồi.
    """
    text = text.strip()
    logger.info(f"[Webhook] PM '{sender}': {text}")

    if text.startswith("/help"):
        return _help_text()

    if text.startswith("/sprint"):
        return _cmd_sprint_info()

    if text.lower().startswith("/set_review"):
        return _cmd_set_review(text, sender)

    if text.lower().startswith("/set_planning"):
        return _cmd_set_planning(text, sender)

    # Hướng dẫn nếu PM nhắn tự do
    return (
        "Xin chào! Dùng các lệnh sau:\n\n"
        "`/set_review DD/MM HH:MM [link]`\n"
        "`/set_planning DD/MM HH:MM [link]`\n"
        "`/sprint` - xem thông tin sprint\n"
        "`/help` - xem trợ giúp\n\n"
        "_Ví dụ: `/set_review 26/05 14:00 https://meet.google.com/xxx`_"
    )


def _cmd_set_review(text: str, sender: str) -> str:
    """Xử lý lệnh /set_review DD/MM HH:MM [link]."""
    parsed = _parse_event_command(text)
    if not parsed:
        return (
            "❌ Cú pháp sai. Dùng:\n"
            "`/set_review DD/MM HH:MM [link_meeting]`\n\n"
            "_Ví dụ: `/set_review 26/05 14:00 https://meet.google.com/xxx`_"
        )

    event_date, event_time, meeting_link = parsed
    sprint = get_sprint_manager().get_current_sprint()

    get_sprint_manager().update_sprint_event(
        event_type="review",
        scheduled_date=event_date,
        scheduled_time=event_time,
        meeting_link=meeting_link,
        created_by=sender,
    )

    # Xác nhận lại với PM
    from src.reminders.messages import MessageTemplates
    confirm_msg = MessageTemplates.confirm_sprint_event("review", event_date, event_time, meeting_link)

    # Thông báo vào group nhóm
    from src.bot.google_chat import GoogleChatBot
    bot = GoogleChatBot()
    announce_msg = MessageTemplates.announce_sprint_event(
        sprint.name, "review", event_date, event_time, meeting_link
    )
    bot.send_group(announce_msg)

    logger.info(f"[Webhook] Đã lưu Sprint Review: {event_date} {event_time}")
    return confirm_msg


def _cmd_set_planning(text: str, sender: str) -> str:
    """Xử lý lệnh /set_planning DD/MM HH:MM [link]."""
    parsed = _parse_event_command(text)
    if not parsed:
        return (
            "❌ Cú pháp sai. Dùng:\n"
            "`/set_planning DD/MM HH:MM [link_meeting]`\n\n"
            "_Ví dụ: `/set_planning 27/05 09:00 https://meet.google.com/xxx`_"
        )

    event_date, event_time, meeting_link = parsed
    sprint = get_sprint_manager().get_current_sprint()

    get_sprint_manager().update_sprint_event(
        event_type="planning",
        scheduled_date=event_date,
        scheduled_time=event_time,
        meeting_link=meeting_link,
        created_by=sender,
    )

    from src.reminders.messages import MessageTemplates
    confirm_msg = MessageTemplates.confirm_sprint_event("planning", event_date, event_time, meeting_link)

    from src.bot.google_chat import GoogleChatBot
    bot = GoogleChatBot()
    announce_msg = MessageTemplates.announce_sprint_event(
        sprint.name, "planning", event_date, event_time, meeting_link
    )
    bot.send_group(announce_msg)

    logger.info(f"[Webhook] Đã lưu Sprint Planning: {event_date} {event_time}")
    return confirm_msg


def _cmd_sprint_info() -> str:
    sprint = get_sprint_manager().get_current_sprint()
    stats = get_sprint_manager().get_sprint_stats()

    events_text = ""
    if stats.get("upcoming_events"):
        events_text = "\n\n📅 *Sự kiện sắp tới:*\n"
        for ev in stats["upcoming_events"]:
            events_text += f"  • {ev['event_type'].upper()}: {ev['scheduled_date']} {ev['scheduled_time']}\n"

    return (
        f"📊 *{sprint.name}*\n\n"
        f"📅 {sprint.start_date} → {sprint.end_date}\n"
        f"⏳ Còn *{stats['days_remaining']} ngày*\n"
        f"📈 Velocity: {stats['velocity_percent']}%"
        f"{events_text}"
    )


def _help_text() -> str:
    return (
        "📖 *Trợ giúp AI Sprint Assistant*\n\n"
        "`/set_review DD/MM HH:MM [link]`\n"
        "→ Lưu lịch Sprint Review, bot tự nhắc nhóm chuẩn bị\n\n"
        "`/set_planning DD/MM HH:MM [link]`\n"
        "→ Lưu lịch Sprint Planning, bot thông báo nhóm\n\n"
        "`/sprint`\n"
        "→ Xem thông tin sprint hiện tại\n\n"
        "`/help`\n"
        "→ Xem trợ giúp này\n\n"
        "_Format ngày: DD/MM (năm tự lấy hiện tại)_\n"
        "_Format giờ: HH:MM (24h)_"
    )


def _parse_event_command(text: str):
    """
    Parse lệnh: /set_review DD/MM HH:MM [link]
    Returns: (event_date "YYYY-MM-DD", event_time "HH:MM", meeting_link) hoặc None
    """
    # Bỏ tên lệnh
    parts = text.split(None, 1)
    if len(parts) < 2:
        return None

    args = parts[1].strip()

    # Tìm ngày: DD/MM hoặc DD-MM
    date_match = re.search(r"(\d{1,2})[/\-](\d{1,2})", args)
    if not date_match:
        return None

    day = int(date_match.group(1))
    month = int(date_match.group(2))
    year = datetime.now().year

    # Nếu tháng đã qua thì sang năm sau
    now = datetime.now()
    if month < now.month or (month == now.month and day < now.day):
        year += 1

    try:
        event_date = datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None

    # Tìm giờ: HH:MM
    time_match = re.search(r"(\d{1,2}):(\d{2})", args)
    if not time_match:
        return None

    event_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    # Tìm link (optional)
    link_match = re.search(r"https?://\S+", args)
    meeting_link = link_match.group(0) if link_match else ""

    return event_date, event_time, meeting_link


# ------------------------------------------------------------------
# Flask routes
# ------------------------------------------------------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint nhận events từ Google Chat."""
    cfg = get_config()

    # Xác thực token (nếu cấu hình)
    token = cfg.bot_server.secret_token
    if token:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {token}":
            logger.warning("[Webhook] Unauthorized request")
            return jsonify({"error": "Unauthorized"}), 401

    event = request.get_json(force=True, silent=True)
    if not event:
        return jsonify({"error": "Invalid payload"}), 400

    event_type = event.get("type", "")
    sender = event.get("user", {}).get("displayName", "PM")

    if event_type == "ADDED_TO_SPACE":
        return jsonify({
            "text": (
                "👋 Xin chào! Tôi là *AI Sprint Assistant*.\n\n"
                "Gõ `/help` để xem các lệnh hỗ trợ."
            )
        })

    if event_type == "MESSAGE":
        msg_text = event.get("message", {}).get("text", "").strip()
        if msg_text:
            reply = handle_pm_message(msg_text, sender)
            return jsonify({"text": reply})

    return jsonify({"text": ""}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "AI Sprint Assistant"})


def run_server():
    cfg = get_config()
    logger.info(f"[Server] Khởi động tại {cfg.bot_server.host}:{cfg.bot_server.port}")
    app.run(host=cfg.bot_server.host, port=cfg.bot_server.port, debug=False)
