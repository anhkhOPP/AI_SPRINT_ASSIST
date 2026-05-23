"""
Flask Webhook Server - Received reply từ PM qua Google Chat.

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
    Hỗ trợ cả lệnh cứng (/set_review) và ngôn ngữ tự nhiên (nhờ Gemini AI).
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

    # Thử dùng AI để hiểu ngôn ngữ tự nhiên
    return _handle_natural_language(text, sender)


def _handle_natural_language(text: str, sender: str) -> str:
    """Dùng Gemini AI để parse lệnh ngôn ngữ tự nhiên từ PM."""
    try:
        from src.ai.gemini import GeminiAI
        ai = GeminiAI()

        if not ai.enabled:
            return (
                "Xin chào! Dùng các lệnh sau:\n\n"
                "`/set_review DD/MM HH:MM [phòng] [link]`\n"
                "`/set_planning DD/MM HH:MM [phòng] [link]`\n"
                "`/sprint` - xem thông tin sprint\n"
                "`/help` - xem trợ giúp"
            )

        # Kiểm tra xem text có liên quan đến lịch họp không
        keywords = ["review", "planning", "họp", "lịch", "ngày", "giờ", "phòng", "sprint"]
        if not any(kw in text.lower() for kw in keywords):
            return (
                "Xin chào! Tôi có thể giúp bạn:\n\n"
                "📅 Đặt lịch Sprint Review/Planning - chỉ cần nhắn tự nhiên:\n"
                "_\"họp review ngày 26/5 lúc 2h chiều phòng A3\"_\n\n"
                "Hoặc dùng lệnh: `/help`"
            )

        logger.info(f"[AI] Đang parse ngôn ngữ tự nhiên: {text}")
        parsed = ai.parse_schedule_from_text(text)

        if not parsed or not parsed.get("date"):
            return (
                "🤔 Tôi chưa hiểu rõ thông tin lịch họp.\n\n"
                "Bạn có thể nói rõ hơn không? Ví dụ:\n"
                "_\"sprint review ngày 26/5, 14:00, phòng A3\"_\n\n"
                "Hoặc dùng lệnh trực tiếp:\n"
                "`/set_review 26/05 14:00 Phòng A3`"
            )

        event_type = parsed.get("event_type", "review")
        date_str = parsed["date"]
        time_str = parsed.get("time", "14:00")
        room = parsed.get("room", "")
        link = parsed.get("link", "")

        logger.info(f"[AI] Parse thành công: type={event_type} date={date_str} time={time_str} room={room}")

        # Gọi lại handler tương ứng
        cmd = f"/{event_type}_{'review' if 'review' in event_type else 'planning'}"
        if event_type == "review":
            return _cmd_set_review(f"/set_review {date_str} {time_str} {room} {link}", sender)
        else:
            return _cmd_set_planning(f"/set_planning {date_str} {time_str} {room} {link}", sender)

    except Exception as e:
        logger.error(f"[AI] Lỗi xử lý ngôn ngữ tự nhiên: {e}")
        return "❌ Có lỗi xảy ra. Vui lòng dùng lệnh: `/set_review DD/MM HH:MM`"


def _cmd_set_review(text: str, sender: str) -> str:
    """Xử lý lệnh /set_review DD/MM HH:MM [link]."""
    parsed = _parse_event_command(text)
    if not parsed:
        return (
            "❌ Cú pháp sai. Dùng:\n"
            "`/set_review DD/MM HH:MM [phòng_họp] [link]`\n\n"
            "_Ví dụ: `/set_review 26/05 14:00 Phòng A3 https://meet.google.com/xxx`_"
        )

    event_date, event_time, meeting_link, meeting_room = parsed
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
    confirm_msg = MessageTemplates.confirm_sprint_event("review", event_date, event_time, meeting_link, meeting_room)

    # Thông báo vào group nhóm
    from src.bot.google_chat import GoogleChatBot
    bot = GoogleChatBot()
    announce_msg = MessageTemplates.announce_sprint_event(
        sprint.name, "review", event_date, event_time, meeting_link, meeting_room
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

    event_date, event_time, meeting_link, meeting_room = parsed
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
        "_Format date: DD/MM (năm tự lấy hiện tại)_\n"
        "_Format giờ: HH:MM (24h)_"
    )


def _parse_event_command(text: str):
    """
    Parse lệnh: /set_review DD/MM HH:MM [phòng_họp] [link]
    Returns: (event_date, event_time, meeting_link, meeting_room) hoặc None

    Ví dụ:
      /set_review 26/05 14:00 Phòng A3 https://meet.google.com/xxx
      /set_review 26/05 14:00 https://meet.google.com/xxx
      /set_review 26/05 14:00 Phòng B2
    """
    parts = text.split(None, 1)
    if len(parts) < 2:
        return None

    args = parts[1].strip()

    # Tìm date: DD/MM hoặc DD-MM
    date_match = re.search(r"(\d{1,2})[/\-](\d{1,2})", args)
    if not date_match:
        return None

    day = int(date_match.group(1))
    month = int(date_match.group(2))
    year = datetime.now().year
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

    # Tìm phòng họp (optional) - text không phải link, không phải ngày/giờ
    remaining = args
    remaining = re.sub(r"\d{1,2}[/\-]\d{1,2}", "", remaining)  # bỏ ngày
    remaining = re.sub(r"\d{1,2}:\d{2}", "", remaining)          # bỏ giờ
    remaining = re.sub(r"https?://\S+", "", remaining)            # bỏ link
    meeting_room = remaining.strip().strip(",").strip()

    return event_date, event_time, meeting_link, meeting_room


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
        logger.warning("[Webhook] Empty or invalid JSON payload")
        return jsonify({"error": "Invalid payload"}), 400

    # Hỗ trợ 2 format:
    # 1. Chat App: {"type": "MESSAGE", "message": {...}, "user": {...}}
    # 2. GSuite Add-on: {"chat": {"eventType": "MESSAGE", "message": {...}, "user": {...}}}
    chat_data = event.get("chat", {})
    if chat_data:
        # GSuite Add-on format:
        # chat.user, chat.eventTime, chat.messagePayload.message.text
        sender = chat_data.get("user", {}).get("displayName", "PM")
        payload = chat_data.get("messagePayload", {})
        message_obj = payload.get("message", payload)  # fallback: dùng payload trực tiếp
        # Nếu có messagePayload → đây là MESSAGE event
        event_type = "MESSAGE" if payload else chat_data.get("eventType", "")
    else:
        # Chat App format
        event_type = event.get("type", "")
        sender = event.get("user", {}).get("displayName", "PM")
        message_obj = event.get("message", {})

    logger.info(f"[Webhook] ═══ EVENT RECEIVED ═══")
    logger.info(f"[Webhook] Format : {'Add-on' if chat_data else 'Chat App'}")
    logger.info(f"[Webhook] Type   : {repr(event_type)}")
    logger.info(f"[Webhook] Sender : {sender}")
    logger.info(f"[Webhook] Message: {message_obj.get('text', '(empty)')[:100]}")
    # Log toàn bộ chat_data để debug
    import json
    logger.info(f"[Webhook] chat keys: {list(chat_data.keys()) if chat_data else '(none)'}")
    logger.info(f"[Webhook] chat data: {json.dumps(chat_data, ensure_ascii=False)[:500]}")

    if event_type in ("ADDED_TO_SPACE", "addedToSpace"):
        logger.info("[Webhook] ── Bot added to Space ──")
        _send_reply_async(
            "👋 Xin chào! Tôi là *AI Sprint Assistant*.\n\nNhắn tin tự nhiên để đặt lịch sprint, hoặc gõ `/help`.",
            via_pm=True
        )
        return jsonify({}), 200

    if event_type in ("MESSAGE", "message"):
        msg_text = (
            message_obj.get("text", "")
            or message_obj.get("argumentText", "")
        ).strip()
        logger.info(f"[Webhook] ── Processing message ──")
        logger.info(f"[Webhook] Text: {repr(msg_text)}")

        if msg_text:
            reply = handle_pm_message(msg_text, sender)
            logger.info(f"[Webhook] Reply: {reply[:80]}...")
            _send_reply_async(reply, via_pm=True)
        else:
            logger.warning("[Webhook] Message text rỗng")
        return jsonify({}), 200

    logger.info(f"[Webhook] Unhandled event type: {event_type}")
    return jsonify({}), 200


def _send_reply_async(text: str, via_pm: bool = True):
    """Gửi reply qua incoming webhook thay vì HTTP response."""
    logger.info(f"[Webhook] ── Bước 3: Gửi reply ──")
    logger.info(f"[Webhook] Channel: {'PM Space' if via_pm else 'Group'}")
    logger.info(f"[Webhook] Content: {text[:80]}...")
    try:
        from src.bot.google_chat import GoogleChatBot
        from config import get_config
        cfg = get_config()
        pm_url = cfg.google_chat.pm_webhook_url
        logger.info(f"[Webhook] PM webhook URL: {'✅ Có' if pm_url else '❌ Not configured'}")

        bot = GoogleChatBot()
        if via_pm:
            ok = bot.send_pm(text)
        else:
            ok = bot.send_group(text)

        logger.info(f"[Webhook] Send reply: {'✅ Thành công' if ok else '❌ Thất bại'}")
    except Exception as e:
        logger.error(f"[Webhook] ❌ Reply send error: {e}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "AI Sprint Assistant"})


@app.route("/set_review", methods=["GET"])
def api_set_review():
    """
    PM dùng URL này để đặt lịch Sprint Review.
    Ví dụ: /set_review?date=26/05&time=14:00&room=Phòng A3&link=https://meet.google.com/xxx
    """
    date_str = request.args.get("date", "")
    time_str = request.args.get("time", "14:00")
    room = request.args.get("room", "")
    link = request.args.get("link", "")

    if not date_str:
        return jsonify({"error": "Thiếu tham số 'date'. VD: ?date=26/05&time=14:00&room=Phòng A3"}), 400

    result = handle_pm_message(f"/set_review {date_str} {time_str} {room} {link}", "PM")
    return jsonify({"result": result})


@app.route("/set_planning", methods=["GET"])
def api_set_planning():
    """
    PM dùng URL này để đặt lịch Sprint Planning.
    Ví dụ: /set_planning?date=27/05&time=09:00&room=Phòng B2
    """
    date_str = request.args.get("date", "")
    time_str = request.args.get("time", "09:00")
    room = request.args.get("room", "")
    link = request.args.get("link", "")

    if not date_str:
        return jsonify({"error": "Thiếu tham số 'date'. VD: ?date=27/05&time=09:00"}), 400

    result = handle_pm_message(f"/set_planning {date_str} {time_str} {room} {link}", "PM")
    return jsonify({"result": result})


def run_server():
    cfg = get_config()
    logger.info(f"[Server] Starting at {cfg.bot_server.host}:{cfg.bot_server.port}")
    app.run(host=cfg.bot_server.host, port=cfg.bot_server.port, debug=False)
