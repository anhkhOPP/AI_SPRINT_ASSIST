"""
Gemini AI Module - Tích hợp Google Gemini API.

Hai tính năng chính:
1. parse_schedule_from_text() - Hiểu lệnh tự nhiên của PM để đặt lịch
2. summarize_daily() - Tóm tắt và phân tích nội dung daily standup
"""
import json
import re
from typing import Optional, Dict, Any, List

import requests
from loguru import logger

from config import get_config


class GeminiAI:

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self):
        cfg = get_config()
        self.api_key = cfg.gemini.api_key
        # Bỏ prefix "models/" nếu user điền đầy đủ
        self.model = cfg.gemini.model.replace("models/", "").strip() or "gemini-2.0-flash"
        self.enabled = cfg.gemini.is_enabled()

        if not self.enabled:
            logger.warning("[Gemini] API key chưa cấu hình (GEMINI_API_KEY). AI features bị tắt.")

    # ------------------------------------------------------------------
    # Tính năng 1: Parse lịch họp từ ngôn ngữ tự nhiên
    # ------------------------------------------------------------------

    def parse_schedule_from_text(self, text: str) -> Optional[Dict[str, str]]:
        """
        Trích xuất thông tin lịch họp từ text tự nhiên của PM.

        Input: "họp review cuối sprint ngày 30 tháng 5, 2 giờ chiều, phòng A3"
        Output: {"date": "30/05", "time": "14:00", "room": "Phòng A3", "link": ""}

        Returns None nếu không parse được hoặc AI không khả dụng.
        """
        if not self.enabled:
            return None

        prompt = f"""Bạn là trợ lý trích xuất thông tin lịch họp từ văn bản tiếng Việt.

Từ đoạn văn sau, hãy trích xuất thông tin và trả về JSON:
"{text}"

Trả về JSON với các trường:
- date: ngày họp dạng DD/MM (ví dụ: "26/05"), để trống nếu không có
- time: giờ họp dạng HH:MM 24h (ví dụ: "14:00"), để trống nếu không có  
- room: tên phòng họp (ví dụ: "Phòng A3"), để trống nếu không có
- link: link meeting nếu có, để trống nếu không có
- event_type: "review" nếu là sprint review, "planning" nếu là sprint planning

Chỉ trả về JSON thuần túy, không có text thêm."""

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
        """
        Tóm tắt nội dung daily standup và phát hiện vấn đề.

        Input: danh sách entries từ daily scraper
        Output: chuỗi text tóm tắt thông minh
        """
        if not self.enabled:
            return None

        if not entries:
            return None

        # Chuẩn bị nội dung daily để gửi cho AI
        daily_content = self._format_entries_for_ai(entries)

        prompt = f"""Bạn là Scrum Master AI, hãy tóm tắt daily standup của nhóm phát triển phần mềm.

Sprint: {sprint_name} (còn {days_remaining} ngày)

Nội dung daily hôm nay:
{daily_content}

Hãy phân tích và trả về tóm tắt ngắn gọn bằng tiếng Việt, bao gồm:
1. Các blockers/vấn đề cần giải quyết ngay (nếu có)
2. Những điểm cần chú ý hoặc tiềm ẩn rủi ro (nếu có)
3. Nhận xét ngắn về tiến độ sprint (nếu cần)

Yêu cầu:
- Ngắn gọn, súc tích (tối đa 5-6 dòng)
- Chỉ nêu những điểm quan trọng, bỏ qua nếu mọi thứ bình thường
- Dùng emoji phù hợp
- Nếu không có gì đặc biệt, chỉ cần trả về: "✅ Daily bình thường, không có blockers."
- KHÔNG liệt kê lại toàn bộ công việc của từng người"""

        response = self._call_api(prompt)
        if not response:
            return None

        return response.strip()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_api(self, prompt: str) -> Optional[str]:
        """Gọi Gemini API và trả về text response."""
        url = self.API_URL.format(model=self.model)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 500,
            },
        }

        try:
            resp = requests.post(
                url,
                json=payload,
                params={"key": self.api_key},
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                logger.debug(f"[Gemini] Response: {text[:100]}...")
                return text

            logger.error(f"[Gemini] API lỗi {resp.status_code}: {resp.text[:200]}")
            return None

        except requests.RequestException as e:
            logger.error(f"[Gemini] Kết nối lỗi: {e}")
            return None

    def _parse_json_response(self, text: str) -> Optional[Dict[str, str]]:
        """Parse JSON từ response của Gemini."""
        # Tìm JSON trong response (có thể có markdown code block)
        json_match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if not json_match:
            logger.warning(f"[Gemini] Không tìm thấy JSON trong response: {text[:100]}")
            return None

        try:
            data = json.loads(json_match.group(0))
            # Đảm bảo có đủ các trường cần thiết
            return {
                "date": data.get("date", "").strip(),
                "time": data.get("time", "").strip(),
                "room": data.get("room", "").strip(),
                "link": data.get("link", "").strip(),
                "event_type": data.get("event_type", "review").strip(),
            }
        except json.JSONDecodeError as e:
            logger.error(f"[Gemini] JSON parse lỗi: {e}")
            return None

    @staticmethod
    def _format_entries_for_ai(entries: List[Dict]) -> str:
        """Format danh sách daily entries thành text để gửi cho AI."""
        lines = []
        for entry in entries:
            name = entry.get("name", "")
            yesterday = entry.get("yesterday", "").strip()
            today = entry.get("today", "").strip()
            blockers = entry.get("blockers", "").strip()

            if not (yesterday or today):
                lines.append(f"- {name}: (chưa điền daily)")
                continue

            line = f"- {name}:"
            if yesterday:
                line += f"\n  Hôm qua: {yesterday[:200]}"
            if today:
                line += f"\n  Hôm nay: {today[:200]}"
            if blockers and blockers not in ("", "\xa0", "&nbsp;"):
                line += f"\n  ⚠️ Blockers: {blockers[:200]}"
            lines.append(line)

        return "\n".join(lines)
