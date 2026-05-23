"""
Claude AI Module - Anthropic Claude API.

Thay thế Gemini với Claude - tiếng Việt tốt hơn, ổn định hơn.
Model khuyến nghị: claude-haiku-4-5 (nhanh, rẻ) hoặc claude-sonnet-4-5 (mạnh hơn)
"""
import json
import re
import time
from typing import Optional, Dict, List

import requests
from loguru import logger

from config import get_config


class ClaudeAI:

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self):
        cfg = get_config()
        self.api_key = cfg.claude.api_key
        self.model = cfg.claude.model
        self.enabled = cfg.claude.is_enabled()

        if not self.enabled:
            logger.warning("[Claude] ANTHROPIC_API_KEY chưa cấu hình.")

    # ------------------------------------------------------------------
    # Tính năng 1: Parse lịch họp từ ngôn ngữ tự nhiên
    # ------------------------------------------------------------------

    def parse_schedule_from_text(self, text: str) -> Optional[Dict[str, str]]:
        """
        Trích xuất thông tin lịch họp từ text tự nhiên của PM.

        Input:  "họp review cuối sprint ngày 30 tháng 5, 2 giờ chiều, phòng A3"
        Output: {"date": "30/05", "time": "14:00", "room": "Phòng A3",
                 "link": "", "event_type": "review"}
        """
        if not self.enabled:
            return None

        prompt = f"""Trích xuất thông tin lịch họp từ đoạn văn tiếng Việt sau và trả về JSON.

Văn bản: "{text}"

Trả về JSON với các trường:
- date: ngày dạng DD/MM (ví dụ "30/05"), để "" nếu không có
- time: giờ dạng HH:MM 24h (ví dụ "14:00"), để "" nếu không có
- room: tên phòng họp, để "" nếu không có
- link: link meeting nếu có, để "" nếu không có
- event_type: "review" nếu sprint review, "planning" nếu sprint planning

Chỉ trả về JSON, không có text khác."""

        response = self._call_api(prompt)
        if not response:
            return None

        return self._parse_json_response(response)

    # ------------------------------------------------------------------
    # Tính năng 2: Tóm tắt Daily Standup
    # ------------------------------------------------------------------

    def summarize_daily(
        self,
        entries: List[Dict],
        sprint_name: str,
        days_remaining: int,
    ) -> Optional[str]:
        """Tóm tắt nội dung daily standup, phát hiện blockers và rủi ro."""
        if not self.enabled:
            return None

        if not entries:
            return None

        daily_content = self._format_entries_for_ai(entries)

        prompt = f"""Bạn là Scrum Master AI. Hãy phân tích daily standup của nhóm phần mềm.

Sprint: {sprint_name} (còn {days_remaining} ngày)

Nội dung daily:
{daily_content}

Yêu cầu:
- Chỉ nêu các điểm đáng chú ý (blockers, rủi ro, conflict tiềm ẩn, task chậm tiến độ)
- Ngắn gọn tối đa 5 dòng
- Dùng emoji phù hợp
- Nếu không có gì đặc biệt: trả về đúng "✅ Daily bình thường, không có blockers."
- KHÔNG liệt kê lại công việc của từng người"""

        return self._call_api(prompt)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_api(self, prompt: str, retry: int = 3) -> Optional[str]:
        """Gọi Claude API với retry khi bị rate limit."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        }

        for attempt in range(retry):
            try:
                resp = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=20,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("content", [{}])[0].get("text", "")
                    logger.debug(f"[Claude] OK: {text[:80]}...")
                    return text.strip()

                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning(f"[Claude] Rate limit, chờ {wait}s")
                    time.sleep(wait)
                    continue

                logger.error(f"[Claude] API lỗi {resp.status_code}: {resp.text[:200]}")
                return None

            except requests.RequestException as e:
                if attempt < retry - 1:
                    time.sleep(5)
                else:
                    logger.error(f"[Claude] Kết nối lỗi: {e}")
                    return None

        return None

    def _parse_json_response(self, text: str) -> Optional[Dict[str, str]]:
        json_match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if not json_match:
            return None
        try:
            data = json.loads(json_match.group(0))
            return {
                "date": data.get("date", "").strip(),
                "time": data.get("time", "").strip(),
                "room": data.get("room", "").strip(),
                "link": data.get("link", "").strip(),
                "event_type": data.get("event_type", "review").strip(),
            }
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _format_entries_for_ai(entries: List[Dict]) -> str:
        lines = []
        for e in entries:
            name = e.get("name", "")
            yesterday = e.get("yesterday", "").strip()
            today = e.get("today", "").strip()
            blockers = e.get("blockers", "").strip()

            if not (yesterday or today):
                lines.append(f"- {name}: (chưa điền)")
                continue

            line = f"- {name}:"
            if yesterday:
                line += f"\n  Hôm qua: {yesterday[:200]}"
            if today:
                line += f"\n  Hôm nay: {today[:200]}"
            if blockers and blockers not in ("", "\xa0"):
                line += f"\n  ⚠️ Blockers: {blockers[:200]}"
            lines.append(line)
        return "\n".join(lines)
