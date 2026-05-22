"""
Module Google Chat Bot.

Hỗ trợ hai chế độ:
1. Incoming Webhook  - gửi tin nhắn một chiều vào Space/Room
2. Bot API (Service Account) - nhắn tin 2 chiều, xử lý lệnh

Tài liệu:
- https://developers.google.com/chat/how-tos/webhooks
- https://developers.google.com/chat/api/guides/message-formats
"""
import json
import hmac
import hashlib
import logging
from typing import Optional, List, Dict, Any

import requests
from loguru import logger

from config import get_config


class GoogleChatBot:
    """Client giao tiếp với Google Chat."""

    def __init__(self):
        cfg = get_config()
        self.webhook_url = cfg.google_chat.webhook_url
        self.alert_webhook_url = cfg.google_chat.alert_webhook_url or self.webhook_url
        self.space_id = cfg.google_chat.space_id
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json; charset=utf-8",
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_text(self, text: str, thread_key: Optional[str] = None) -> bool:
        """Gửi tin nhắn văn bản thuần vào nhóm."""
        payload = self._build_text_payload(text, thread_key)
        return self._post_webhook(self.webhook_url, payload)

    def send_card(self, card: Dict[str, Any], thread_key: Optional[str] = None) -> bool:
        """Gửi card message (rich format)."""
        payload = {"cardsV2": [card]}
        if thread_key:
            payload["thread"] = {"threadKey": thread_key}
        return self._post_webhook(self.webhook_url, payload)

    def send_alert(self, text: str) -> bool:
        """Gửi thông báo quan trọng (có thể tới webhook riêng)."""
        payload = self._build_text_payload(f"🚨 *CẢNH BÁO* 🚨\n{text}")
        return self._post_webhook(self.alert_webhook_url, payload)

    def send_reminder_card(
        self,
        title: str,
        body: str,
        emoji: str = "🔔",
        color: str = "#1E88E5",
        button_text: Optional[str] = None,
        button_url: Optional[str] = None,
    ) -> bool:
        """Gửi card nhắc nhở có định dạng đẹp."""
        widgets = [
            {
                "decoratedText": {
                    "text": body,
                    "wrapText": True,
                }
            }
        ]

        if button_text and button_url:
            widgets.append({
                "buttonList": {
                    "buttons": [
                        {
                            "text": button_text,
                            "onClick": {"openLink": {"url": button_url}},
                        }
                    ]
                }
            })

        card = {
            "cardId": "reminder_card",
            "card": {
                "header": {
                    "title": f"{emoji} {title}",
                    "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsoutlined/notifications/default/48px.svg",
                    "imageType": "CIRCLE",
                },
                "sections": [
                    {
                        "widgets": widgets,
                        "collapsible": False,
                    }
                ],
                "fixedFooter": {
                    "primaryButton": {
                        "text": "✅ Đã hiểu",
                        "color": {"red": 0.118, "green": 0.533, "blue": 0.898},
                        "disabled": True,
                    }
                },
            },
        }

        return self.send_card(card)

    def send_missing_users_card(
        self,
        title: str,
        missing_users: List[str],
        action_label: str,
        color: str = "#E53935",
    ) -> bool:
        """Gửi danh sách người dùng chưa thực hiện hành động."""
        if not missing_users:
            return self.send_text(f"✅ *{title}*\nTất cả thành viên đã hoàn thành!")

        user_list = "\n".join(f"• {u}" for u in missing_users)
        text = (
            f"⚠️ *{title}*\n\n"
            f"Những người chưa {action_label}:\n{user_list}\n\n"
            f"_Vui lòng thực hiện sớm nhé!_ 🙏"
        )
        return self.send_text(text)

    def send_sprint_question(
        self, question: str, context: str = ""
    ) -> bool:
        """Gửi câu hỏi tới nhóm (dùng cho hỏi sprint review/planning)."""
        text = f"❓ *CÂU HỎI TỪ BOT*\n\n{question}"
        if context:
            text += f"\n\n_{context}_"
        text += "\n\n_(Trả lời vào thread này hoặc nhắn riêng cho PM)_"
        return self.send_text(text)

    # ------------------------------------------------------------------
    # Webhook verification (dùng khi nhận message từ Google Chat)
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self, request_body: bytes, signature: str, secret: str
    ) -> bool:
        """Xác thực chữ ký từ Google Chat khi nhận webhook."""
        expected = hmac.new(
            secret.encode(), request_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_text_payload(
        self, text: str, thread_key: Optional[str] = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"text": text}
        if thread_key:
            payload["thread"] = {"threadKey": thread_key}
        return payload

    def _post_webhook(self, url: str, payload: Dict[str, Any]) -> bool:
        """POST payload tới Google Chat webhook."""
        if not url:
            logger.warning("Webhook URL chưa được cấu hình, bỏ qua gửi tin nhắn.")
            return False
        try:
            resp = self._session.post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.info(f"[GoogleChat] Gửi thành công: {resp.status_code}")
                return True
            else:
                logger.error(
                    f"[GoogleChat] Gửi thất bại: {resp.status_code} - {resp.text}"
                )
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"[GoogleChat] Lỗi kết nối: {e}")
            return False
