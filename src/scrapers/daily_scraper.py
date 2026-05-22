"""
Scraper cho trang web Daily Standup nội bộ.

Kiểm tra ai đã điền daily standup form hôm nay.
Hỗ trợ: HTML table, JSON API, Google Forms, Confluence, custom form.
"""
import os
from datetime import date, datetime
from typing import Dict, Any, List, Optional

from loguru import logger

from config import get_config
from .base_scraper import BaseScraper, ScrapingError


class DailyScraper(BaseScraper):
    """
    Scraper kiểm tra trạng thái daily standup.

    Cách hoạt động:
    1. Truy cập trang daily report nội bộ
    2. Kiểm tra ai đã submit daily form hôm nay
    3. Trả về danh sách người chưa điền
    """

    PARSER_FORMAT = os.getenv("INTERNAL_DAILY_FORMAT", "html_table")

    def __init__(self):
        super().__init__()
        cfg = get_config()
        self.daily_url = cfg.internal_site.daily_url
        self.team_members = [m["name"] for m in cfg.team.get_members()]

    def fetch_data(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Lấy dữ liệu daily standup theo ngày.

        Returns:
            {
                "date": "2024-01-15",
                "submitted": ["Nguyen Van A", ...],
                "missing": ["Le Van C"],
                "entries": [{"user": ..., "yesterday": ..., "today": ..., "blockers": ...}]
            }
        """
        if target_date is None:
            target_date = date.today()

        if not self.daily_url:
            logger.warning("[DailyScraper] INTERNAL_DAILY_URL chưa cấu hình, dùng mock data")
            return self._mock_data(target_date)

        try:
            if self.PARSER_FORMAT == "json_api":
                return self._fetch_json_api(target_date)
            elif self.PARSER_FORMAT == "google_forms":
                return self._fetch_google_forms(target_date)
            elif self.PARSER_FORMAT == "confluence":
                return self._fetch_confluence(target_date)
            else:
                return self._fetch_html_table(target_date)

        except Exception as e:
            logger.error(f"[DailyScraper] Lỗi fetch data: {e}")
            return self._mock_data(target_date)

    def get_missing_users(self, target_date: Optional[date] = None) -> List[str]:
        """Lấy danh sách người chưa điền daily."""
        data = self.fetch_data(target_date)
        return data.get("missing", [])

    def get_daily_entries(self, target_date: Optional[date] = None) -> List[Dict]:
        """Lấy nội dung daily của từng người."""
        data = self.fetch_data(target_date)
        return data.get("entries", [])

    # ------------------------------------------------------------------
    # HTML Table Parser
    # ------------------------------------------------------------------

    def _fetch_html_table(self, target_date: date) -> Dict[str, Any]:
        """Parse bảng HTML chứa daily standup."""
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{self.daily_url}?date={date_str}"

        logger.info(f"[DailyScraper] Fetching HTML: {url}")
        resp = self.get(url)

        if not resp:
            raise ScrapingError("Không thể truy cập trang daily standup")

        soup = self.parse_html(resp.text)

        # Tìm bảng daily (customize theo trang của bạn)
        table = (
            soup.find("table", {"class": "daily-table"})
            or soup.find("table", {"id": "daily-report"})
            or soup.find("table", {"class": ["standup", "daily", "report"]})
            or soup.find("table")
        )

        if not table:
            logger.warning("[DailyScraper] Không tìm thấy bảng daily")
            return self._build_result(target_date, [], self.team_members, [])

        submitted, entries = self._parse_daily_table(table)
        missing = [m for m in self.team_members if m not in submitted]

        return self._build_result(target_date, submitted, missing, entries)

    def _parse_daily_table(self, table) -> tuple:
        """
        Parse bảng HTML để lấy thông tin daily.

        Customize theo cấu trúc bảng của trang nội bộ bạn.
        Giả sử cấu trúc: Name | Yesterday | Today | Blockers | Status
        """
        submitted = []
        entries = []
        rows = table.find_all("tr")[1:]  # Bỏ header

        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue

            user_name = cols[0].get_text(strip=True)
            if not user_name:
                continue

            # Lấy nội dung các cột (customize theo cấu trúc bảng)
            yesterday = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            today = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            blockers = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            status = cols[4].get_text(strip=True) if len(cols) > 4 else ""

            # Xác định đã submit chưa
            is_submitted = bool(
                yesterday or today
            ) and status.lower() not in ("pending", "chờ", "")

            if is_submitted:
                submitted.append(user_name)

            entries.append({
                "user": user_name,
                "yesterday": yesterday,
                "today": today,
                "blockers": blockers,
                "submitted": is_submitted,
            })

        return submitted, entries

    # ------------------------------------------------------------------
    # JSON API Parser
    # ------------------------------------------------------------------

    def _fetch_json_api(self, target_date: date) -> Dict[str, Any]:
        """Fetch daily từ JSON API."""
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{self.daily_url}/api/daily"

        logger.info(f"[DailyScraper] Fetching JSON API: {url}")
        resp = self.get(url, params={"date": date_str})

        if not resp:
            raise ScrapingError("Không thể truy cập API daily")

        data = resp.json()
        submitted = []
        entries = []

        reports = data.get("reports", data.get("data", data.get("items", [])))
        for report in reports:
            user = (
                report.get("user", {}).get("name")
                or report.get("username")
                or report.get("name", "")
            )
            if not user:
                continue

            entry = {
                "user": user,
                "yesterday": report.get("yesterday", report.get("done_yesterday", "")),
                "today": report.get("today", report.get("plan_today", "")),
                "blockers": report.get("blockers", report.get("impediments", "")),
                "submitted": report.get("submitted", True),
            }
            entries.append(entry)

            if entry["submitted"]:
                submitted.append(user)

        missing = [m for m in self.team_members if m not in submitted]
        return self._build_result(target_date, submitted, missing, entries, raw=data)

    # ------------------------------------------------------------------
    # Google Forms Parser (dùng Google Sheets API để đọc responses)
    # ------------------------------------------------------------------

    def _fetch_google_forms(self, target_date: date) -> Dict[str, Any]:
        """
        Fetch daily từ Google Forms (qua Google Sheets linked spreadsheet).
        Cần cấu hình GOOGLE_SHEETS_ID trong .env.
        """
        sheets_id = os.getenv("GOOGLE_SHEETS_DAILY_ID", "")
        if not sheets_id:
            raise ScrapingError("GOOGLE_SHEETS_DAILY_ID chưa cấu hình")

        date_str = target_date.strftime("%d/%m/%Y")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheets_id}/values/A:E"

        resp = self.get(url)
        if not resp:
            raise ScrapingError("Không thể đọc Google Sheets")

        data = resp.json()
        rows = data.get("values", [])

        submitted = []
        entries = []

        # Giả sử cột: Timestamp | Email | Name | Yesterday | Today | Blockers
        for row in rows[1:]:  # Bỏ header
            if len(row) < 3:
                continue

            timestamp = row[0] if len(row) > 0 else ""
            # Kiểm tra ngày submit
            if date_str not in timestamp:
                continue

            user = row[2] if len(row) > 2 else row[1]
            entry = {
                "user": user,
                "yesterday": row[3] if len(row) > 3 else "",
                "today": row[4] if len(row) > 4 else "",
                "blockers": row[5] if len(row) > 5 else "",
                "submitted": True,
            }
            submitted.append(user)
            entries.append(entry)

        missing = [m for m in self.team_members if m not in submitted]
        return self._build_result(target_date, submitted, missing, entries)

    # ------------------------------------------------------------------
    # Confluence Parser
    # ------------------------------------------------------------------

    def _fetch_confluence(self, target_date: date) -> Dict[str, Any]:
        """Fetch daily từ Confluence page."""
        date_str = target_date.strftime("%d/%m/%Y")
        logger.info(f"[DailyScraper] Fetching Confluence: {self.daily_url}")

        resp = self.get(self.daily_url)
        if not resp:
            raise ScrapingError("Không thể truy cập Confluence")

        soup = self.parse_html(resp.text)
        submitted = []
        entries = []

        # Tìm section của ngày hôm nay
        date_headers = soup.find_all(["h2", "h3", "h4"], text=lambda t: t and date_str in t)

        if date_headers:
            header = date_headers[0]
            sibling = header.find_next_sibling()

            while sibling and sibling.name not in ["h2", "h3"]:
                # Tìm tên thành viên trong section
                for item in sibling.find_all(["li", "p", "td"]):
                    text = item.get_text(strip=True)
                    for member in self.team_members:
                        if member.lower() in text.lower() and member not in submitted:
                            submitted.append(member)
                            entries.append({
                                "user": member,
                                "yesterday": "",
                                "today": text,
                                "blockers": "",
                                "submitted": True,
                            })
                sibling = sibling.find_next_sibling()

        missing = [m for m in self.team_members if m not in submitted]
        return self._build_result(target_date, submitted, missing, entries)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
        target_date: date,
        submitted: List[str],
        missing: List[str],
        entries: List[Dict],
        raw: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "submitted": submitted,
            "missing": missing,
            "submitted_count": len(submitted),
            "missing_count": len(missing),
            "entries": entries,
            "raw_data": raw or {},
        }

    def _mock_data(self, target_date: date) -> Dict[str, Any]:
        """Mock data khi URL chưa cấu hình."""
        members = self.team_members or ["Nguyen Van A", "Tran Thi B", "Le Van C", "Pham Thi D"]
        submitted = members[:max(1, int(len(members) * 0.75))]
        missing = [m for m in members if m not in submitted]
        entries = [
            {
                "user": m,
                "yesterday": "Làm feature X",
                "today": "Tiếp tục feature X, review code",
                "blockers": "",
                "submitted": True,
            }
            for m in submitted
        ]

        logger.info(f"[DailyScraper] Dùng MOCK data cho {target_date}")
        return self._build_result(target_date, submitted, missing, entries)
