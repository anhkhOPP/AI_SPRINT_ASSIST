from .gemini import GeminiAI
from .claude import ClaudeAI
from typing import Optional, Dict, List


class AIClient:
    """
    AI Client với fallback tự động: Gemini → Claude.
    Nếu Gemini error/none key → tự chuyển sang Claude.
    """

    def __init__(self):
        from config import get_config
        cfg = get_config()
        self._gemini = GeminiAI() if cfg.gemini.is_enabled() else None
        self._claude = ClaudeAI() if cfg.claude.is_enabled() else None
        self.enabled = bool(self._gemini or self._claude)

        if self._gemini:
            primary = f"Gemini ({self._gemini.model})"
            backup = f"Claude ({self._claude.model})" if self._claude else "none"
        elif self._claude:
            primary = f"Claude ({self._claude.model})"
            backup = "none"
        else:
            primary = "none"
            backup = "none"

        from loguru import logger
        logger.info(f"[AI] Primary: {primary} | Backup: {backup}")

    def parse_schedule_from_text(self, text: str) -> Optional[Dict[str, str]]:
        """Parse lịch họp từ ngôn ngữ tự nhiên. Gemini trước, Claude nếu lỗi."""
        result = self._try_gemini("parse_schedule_from_text", text)
        if result is None and self._claude:
            from loguru import logger
            logger.info("[AI] Gemini failed → switching to Claude")
            result = self._claude.parse_schedule_from_text(text)
        return result

    def summarize_daily(
        self, entries: List[Dict], sprint_name: str, days_remaining: int
    ) -> Optional[str]:
        """Tóm tắt daily standup. Gemini trước, Claude nếu lỗi."""
        result = self._try_gemini("summarize_daily", entries, sprint_name, days_remaining)
        if result is None and self._claude:
            from loguru import logger
            logger.info("[AI] Gemini failed → switching to Claude")
            result = self._claude.summarize_daily(entries, sprint_name, days_remaining)
        return result

    def _try_gemini(self, method: str, *args):
        """Gọi Gemini, trả về None nếu none hoặc lỗi."""
        if not self._gemini:
            return None
        try:
            return getattr(self._gemini, method)(*args)
        except Exception as e:
            from loguru import logger
            logger.warning(f"[AI] Gemini error ({method}): {e}")
            return None


def get_ai() -> AIClient:
    """Trả về AI client với fallback Gemini → Claude."""
    return AIClient()


__all__ = ["GeminiAI", "ClaudeAI", "AIClient", "get_ai"]
