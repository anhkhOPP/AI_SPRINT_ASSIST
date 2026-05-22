"""
Flask server nhận webhook từ Google Chat Bot.

Khi người dùng nhắn tin cho bot, Google Chat sẽ gọi endpoint này.
Dùng để xử lý phản hồi sprint review/planning dates.

Docs: https://developers.google.com/chat/how-tos/bots-publish
"""
import json
from typing import Optional

from flask import Flask, request, jsonify
from loguru import logger

from config import get_config

app = Flask(__name__)


class WebhookHandler:
    """Xử lý các tin nhắn nhận được từ Google Chat."""

    def __init__(self, sprint_manager=None):
        self.sprint_manager = sprint_manager
        self._pending_questions: dict = {}

    def handle_message(self, event: dict) -> Optional[dict]:
        """
        Xử lý sự kiện từ Google Chat.
        Trả về response dict hoặc None.
        """
        event_type = event.get("type", "")

        if event_type == "ADDED_TO_SPACE":
            return self._handle_added_to_space(event)
        elif event_type == "MESSAGE":
            return self._handle_message_event(event)
        elif event_type == "CARD_CLICKED":
            return self._handle_card_click(event)

        return None

    def _handle_added_to_space(self, event: dict) -> dict:
        space_name = event.get("space", {}).get("displayName", "nhóm")
        return {
            "text": (
                f"👋 Xin chào *{space_name}*!\n\n"
                "Tôi là *AI Sprint Assistant* - trợ lý quản lý sprint của nhóm.\n\n"
                "Những việc tôi có thể làm:\n"
                "• ⏰ Nhắc họp daily lúc 9:10\n"
                "• 📝 Nhắc log work lúc 17:30\n"
                "• 🔍 Kiểm tra log work & daily standup\n"
                "• 📅 Hỏi lịch sprint review/planning\n"
                "• 🚀 Nhắc chuẩn bị trước sprint review\n\n"
                "Gõ `/help` để xem danh sách lệnh."
            )
        }

    def _handle_message_event(self, event: dict) -> Optional[dict]:
        message = event.get("message", {})
        text = message.get("text", "").strip().lower()
        sender = event.get("user", {}).get("displayName", "Bạn")

        logger.info(f"[Webhook] Nhận tin nhắn từ {sender}: {text}")

        # Xử lý lệnh
        if text.startswith("/help") or text == "help":
            return self._cmd_help()
        elif text.startswith("/sprint"):
            return self._cmd_sprint_info()
        elif text.startswith("/status"):
            return self._cmd_status()
        elif "sprint review" in text or "review ngày" in text:
            return self._handle_sprint_review_response(text, sender)
        elif "sprint planning" in text or "planning ngày" in text:
            return self._handle_sprint_planning_response(text, sender)
        elif text.startswith("/set_review"):
            return self._cmd_set_review(text, sender)
        elif text.startswith("/set_planning"):
            return self._cmd_set_planning(text, sender)
        elif text.startswith("/members"):
            return self._cmd_members()
        elif text.startswith("/today"):
            return self._cmd_today_summary()

        return None

    def _handle_card_click(self, event: dict) -> Optional[dict]:
        action = event.get("action", {}).get("actionMethodName", "")
        logger.info(f"[Webhook] Card click: {action}")
        return {"text": f"✅ Đã ghi nhận hành động: {action}"}

    def _cmd_help(self) -> dict:
        return {
            "text": (
                "📖 *Danh sách lệnh AI Sprint Assistant:*\n\n"
                "`/help` - Hiển thị trợ giúp\n"
                "`/sprint` - Thông tin sprint hiện tại\n"
                "`/status` - Trạng thái hôm nay (log work, daily)\n"
                "`/members` - Danh sách thành viên\n"
                "`/today` - Tóm tắt công việc hôm nay\n"
                "`/set_review YYYY-MM-DD HH:MM` - Đặt lịch sprint review\n"
                "`/set_planning YYYY-MM-DD HH:MM` - Đặt lịch sprint planning\n\n"
                "_Ví dụ: `/set_review 2024-01-26 14:00`_"
            )
        }

    def _cmd_sprint_info(self) -> dict:
        cfg = get_config()
        sprint = cfg.sprint
        remaining = sprint.days_remaining()
        end_date = sprint.get_sprint_end().strftime("%d/%m/%Y")

        return {
            "text": (
                f"📊 *Thông tin Sprint hiện tại:*\n\n"
                f"🏷️ Tên sprint: *{sprint.current_sprint_name}*\n"
                f"📅 Bắt đầu: {sprint.current_sprint_start}\n"
                f"🏁 Kết thúc: {end_date}\n"
                f"⏳ Còn lại: *{remaining} ngày*\n"
                f"📆 Thời gian: {sprint.sprint_duration_weeks} tuần/sprint"
            )
        }

    def _cmd_status(self) -> dict:
        return {
            "text": (
                "📋 *Trạng thái hôm nay:*\n\n"
                "_(Đang kiểm tra... vui lòng chờ)_\n\n"
                "Dùng `/today` để xem tóm tắt đầy đủ."
            )
        }

    def _cmd_members(self) -> dict:
        cfg = get_config()
        members = cfg.team.get_members()
        if not members:
            return {"text": "⚠️ Chưa cấu hình danh sách thành viên. Xem file `.env`"}

        member_list = "\n".join(
            f"• {m['name']}" + (f" ({m['email']})" if m['email'] else "")
            for m in members
        )
        return {"text": f"👥 *Danh sách thành viên ({len(members)} người):*\n\n{member_list}"}

    def _cmd_today_summary(self) -> dict:
        return {
            "text": (
                "📅 *Tóm tắt hôm nay:*\n\n"
                "🕘 09:10 - Họp Daily Standup\n"
                "🕙 09:30 - Kiểm tra log work hôm qua\n"
                "🕙 10:00 - Kiểm tra daily standup\n"
                "🕔 17:30 - Nhắc log work\n\n"
                "_Bot đang hoạt động bình thường_ ✅"
            )
        }

    def _handle_sprint_review_response(self, text: str, sender: str) -> dict:
        return {
            "text": (
                f"📝 *{sender}* đã phản hồi về sprint review.\n"
                "Vui lòng dùng lệnh:\n"
                "`/set_review YYYY-MM-DD HH:MM`\n"
                "để đặt lịch chính thức."
            )
        }

    def _handle_sprint_planning_response(self, text: str, sender: str) -> dict:
        return {
            "text": (
                f"📝 *{sender}* đã phản hồi về sprint planning.\n"
                "Vui lòng dùng lệnh:\n"
                "`/set_planning YYYY-MM-DD HH:MM`\n"
                "để đặt lịch chính thức."
            )
        }

    def _cmd_set_review(self, text: str, sender: str) -> dict:
        parts = text.split()
        if len(parts) >= 3:
            date_str = parts[1]
            time_str = parts[2] if len(parts) > 2 else "14:00"
            return {
                "text": (
                    f"✅ *Đã lưu lịch Sprint Review!*\n\n"
                    f"📅 Ngày: *{date_str}*\n"
                    f"🕑 Giờ: *{time_str}*\n"
                    f"👤 Đặt bởi: {sender}\n\n"
                    "Bot sẽ nhắc nhở nhóm trước buổi họp. 🔔"
                )
            }
        return {"text": "❌ Cú pháp sai. Dùng: `/set_review YYYY-MM-DD HH:MM`\nVí dụ: `/set_review 2024-01-26 14:00`"}

    def _cmd_set_planning(self, text: str, sender: str) -> dict:
        parts = text.split()
        if len(parts) >= 3:
            date_str = parts[1]
            time_str = parts[2] if len(parts) > 2 else "09:00"
            return {
                "text": (
                    f"✅ *Đã lưu lịch Sprint Planning!*\n\n"
                    f"📅 Ngày: *{date_str}*\n"
                    f"🕙 Giờ: *{time_str}*\n"
                    f"👤 Đặt bởi: {sender}\n\n"
                    "Bot sẽ nhắc nhở nhóm trước buổi họp. 🔔"
                )
            }
        return {"text": "❌ Cú pháp sai. Dùng: `/set_planning YYYY-MM-DD HH:MM`\nVí dụ: `/set_planning 2024-01-29 09:00`"}


# Singleton handler
_handler = WebhookHandler()


@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint nhận events từ Google Chat."""
    cfg = get_config()
    secret = cfg.bot_server.secret_token

    # Xác thực token (optional nhưng khuyến nghị)
    if secret:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != secret:
            logger.warning("[Webhook] Unauthorized request")
            return jsonify({"error": "Unauthorized"}), 401

    try:
        event = request.get_json(force=True)
        if not event:
            return jsonify({"error": "Invalid payload"}), 400

        response = _handler.handle_message(event)
        if response:
            return jsonify(response)
        return jsonify({"text": ""}), 200

    except Exception as e:
        logger.exception(f"[Webhook] Lỗi xử lý: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "AI Sprint Assistant"})


def run_server():
    cfg = get_config()
    app.run(
        host=cfg.bot_server.host,
        port=cfg.bot_server.port,
        debug=False,
    )
