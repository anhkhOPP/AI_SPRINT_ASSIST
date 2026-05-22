"""
Google Chat Bot - Gửi tin nhắn qua Incoming Webhook.

Hỗ trợ 2 kênh:
- group_webhook_url : gửi vào Space nhóm chung
- pm_webhook_url    : gửi vào Space riêng của PM (DM-like)
"""
import json
from typing import Optional, List

import requests
from loguru import logger

from config import get_config


class GoogleChatBot:

    def __init__(self):
        cfg = get_config()
        self._group_url = cfg.google_chat.group_webhook_url
        self._pm_url = cfg.google_chat.pm_webhook_url
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json; charset=utf-8"})

    # ------------------------------------------------------------------
    # Gửi vào group nhóm
    # ------------------------------------------------------------------

    def send_group(self, text: str) -> bool:
        """Gửi tin nhắn text vào nhóm."""
        return self._post(self._group_url, {"text": text})

    # ------------------------------------------------------------------
    # Gửi DM riêng cho PM
    # ------------------------------------------------------------------

    def send_pm(self, text: str) -> bool:
        """Gửi tin nhắn vào Space riêng của PM."""
        if not self._pm_url:
            logger.warning("[Bot] PM webhook chưa cấu hình (GOOGLE_CHAT_PM_WEBHOOK_URL)")
            return False
        return self._post(self._pm_url, {"text": text})

    # ------------------------------------------------------------------
    # Các loại tin nhắn cụ thể
    # ------------------------------------------------------------------

    def notify_daily_meeting(self, message: str) -> bool:
        return self.send_group(message)

    def notify_missing_logwork(self, message: str) -> bool:
        return self.send_group(message)

    def notify_missing_daily(self, message: str) -> bool:
        return self.send_group(message)

    def notify_logwork_reminder(self, message: str) -> bool:
        return self.send_group(message)

    def notify_sprint_review_prep(self, message: str) -> bool:
        return self.send_group(message)

    def ask_pm_sprint_review(self, message: str) -> bool:
        """Hỏi PM lịch Sprint Review qua DM."""
        return self.send_pm(message)

    def ask_pm_sprint_planning(self, message: str) -> bool:
        """Hỏi PM lịch Sprint Planning qua DM."""
        return self.send_pm(message)

    def confirm_pm(self, message: str) -> bool:
        """Xác nhận lại với PM sau khi nhận lịch."""
        return self.send_pm(message)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post(self, url: str, payload: dict) -> bool:
        if not url:
            logger.warning("[Bot] Webhook URL trống, bỏ qua.")
            return False
        try:
            resp = self._session.post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.debug(f"[Bot] Gửi OK → {url[:60]}...")
                return True
            logger.error(f"[Bot] Gửi thất bại {resp.status_code}: {resp.text[:200]}")
            return False
        except requests.RequestException as e:
            logger.error(f"[Bot] Lỗi kết nối: {e}")
            return False
