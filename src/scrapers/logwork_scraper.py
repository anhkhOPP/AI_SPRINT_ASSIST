"""
Scraper cho trang web log work nội bộ.

Hỗ trợ nhiều format trang web:
1. HTML table (Jira-like, Redmine, custom)
2. JSON API endpoint
3. Confluence page
4. Google Sheets (qua API)

Cấu hình INTERNAL_LOGWORK_URL và INTERNAL_LOGWORK_FORMAT để chọn parser phù hợp.
"""
import os
import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

from loguru import logger

from config import get_config
from .base_scraper import BaseScraper, ScrapingError


class LogworkScraper(BaseScraper):
    """
    Scraper kiểm tra trạng thái log work của các thành viên.

    Cách hoạt động:
    1. Đăng nhập vào trang nội bộ (theo cấu hình auth)
    2. Truy cập trang báo cáo log work
    3. Parse danh sách ai đã/chưa log work
    4. Trả về danh sách người chưa log work
    """

    # Format parser: "html_table" | "json_api" | "confluence" | "jira"
    PARSER_FORMAT = os.getenv("INTERNAL_LOGWORK_FORMAT", "html_table")

    def __init__(self):
        super().__init__()
        cfg = get_config()
        self.logwork_url = cfg.internal_site.logwork_url
        self.team_members = [m["name"] for m in cfg.team.get_members()]

    def fetch_data(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Lấy dữ liệu log work theo ngày.

        Args:
            target_date: Ngày cần kiểm tra (mặc định: hôm qua)

        Returns:
            {
                "date": "2024-01-15",
                "logged": ["Nguyen Van A", "Tran Thi B"],
                "missing": ["Le Van C"],
                "raw_data": {...}
            }
        """
        if target_date is None:
            # Mặc định kiểm tra hôm qua (vì check lúc 9:30 sáng)
            target_date = date.today() - timedelta(days=1)
            # Bỏ qua cuối tuần
            if target_date.weekday() >= 5:  # Thứ 7 hoặc CN
                target_date = target_date - timedelta(days=target_date.weekday() - 4)

        if not self.logwork_url:
            logger.warning("[LogworkScraper] INTERNAL_LOGWORK_URL chưa cấu hình, dùng mock data")
            return self._mock_data(target_date)

        try:
            if self.PARSER_FORMAT == "json_api":
                return self._fetch_json_api(target_date)
            elif self.PARSER_FORMAT == "jira":
                return self._fetch_jira(target_date)
            elif self.PARSER_FORMAT == "confluence":
                return self._fetch_confluence(target_date)
            else:
                return self._fetch_html_table(target_date)

        except Exception as e:
            logger.error(f"[LogworkScraper] Lỗi fetch data: {e}")
            return self._mock_data(target_date)

    def get_missing_users(self, target_date: Optional[date] = None) -> List[str]:
        """Lấy danh sách người chưa log work."""
        data = self.fetch_data(target_date)
        return data.get("missing", [])

    # ------------------------------------------------------------------
    # HTML Table Parser (trang HTML thông thường)
    # ------------------------------------------------------------------

    def _fetch_html_table(self, target_date: date) -> Dict[str, Any]:
        """Parse bảng HTML chứa thông tin log work."""
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{self.logwork_url}?date={date_str}"

        logger.info(f"[LogworkScraper] Fetching HTML: {url}")
        resp = self.get(url)

        if not resp:
            raise ScrapingError("Không thể truy cập trang log work")

        soup = self.parse_html(resp.text)

        # Tìm bảng log work (customize selector theo trang của bạn)
        # Ví dụ: <table class="logwork-table"> hoặc <table id="timesheet">
        table = (
            soup.find("table", {"class": "logwork-table"})
            or soup.find("table", {"id": "timesheet"})
            or soup.find("table", {"class": ["table", "worklog", "timesheet"]})
            or soup.find("table")  # fallback: lấy bảng đầu tiên
        )

        if not table:
            logger.warning("[LogworkScraper] Không tìm thấy bảng dữ liệu")
            return self._build_result(target_date, [], self.team_members)

        logged_users = self._parse_logwork_table(table, date_str)
        missing = [m for m in self.team_members if m not in logged_users]

        return self._build_result(target_date, logged_users, missing)

    def _parse_logwork_table(self, table, date_str: str) -> List[str]:
        """
        Parse bảng HTML để lấy danh sách người đã log work.

        Customize logic này theo cấu trúc bảng của trang nội bộ bạn.
        """
        logged = []
        rows = table.find_all("tr")[1:]  # Bỏ header row

        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue

            user_name = cols[0].get_text(strip=True)
            hours_logged = cols[1].get_text(strip=True)

            # Kiểm tra nếu có log work (giờ > 0)
            try:
                hours = float(hours_logged.replace("h", "").replace(",", ".").strip() or "0")
                if hours > 0:
                    logged.append(user_name)
            except ValueError:
                # Một số trang dùng checkbox hoặc ký hiệu khác
                if hours_logged and hours_logged.lower() not in ("0", "", "-", "n/a"):
                    logged.append(user_name)

        return logged

    # ------------------------------------------------------------------
    # JSON API Parser
    # ------------------------------------------------------------------

    def _fetch_json_api(self, target_date: date) -> Dict[str, Any]:
        """Fetch từ JSON API endpoint."""
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{self.logwork_url}/api/worklogs"

        logger.info(f"[LogworkScraper] Fetching JSON API: {url}")
        resp = self.get(url, params={"date": date_str, "format": "json"})

        if not resp:
            raise ScrapingError("Không thể truy cập API log work")

        try:
            data = resp.json()
        except Exception:
            raise ScrapingError("Response không phải JSON hợp lệ")

        # Parse theo cấu trúc JSON của trang bạn
        # Customize đây theo API response của hệ thống nội bộ
        logged_users = []
        worklogs = data.get("worklogs", data.get("data", data.get("items", [])))

        for entry in worklogs:
            user = (
                entry.get("user", {}).get("displayName")
                or entry.get("username")
                or entry.get("name")
                or entry.get("author", {}).get("displayName", "")
            )
            hours = float(entry.get("timeSpentSeconds", entry.get("hours", 0)) or 0)
            if hours > 0 and user:
                logged_users.append(user)

        missing = [m for m in self.team_members if m not in logged_users]
        return self._build_result(target_date, logged_users, missing, raw=data)

    # ------------------------------------------------------------------
    # Jira Worklog Parser
    # ------------------------------------------------------------------

    def _fetch_jira(self, target_date: date) -> Dict[str, Any]:
        """Fetch từ Jira REST API (nếu công ty dùng Jira)."""
        date_str = target_date.strftime("%Y-%m-%d")

        # Jira JQL query: worklogs có ngày target_date
        jql = f'worklogDate = "{date_str}" AND project in (currentUserProjects())'
        url = f"{self.logwork_url}/rest/api/2/search"

        logger.info(f"[LogworkScraper] Fetching Jira: {url}")
        resp = self.get(url, params={
            "jql": jql,
            "fields": "worklog,assignee",
            "expand": "changelog",
            "maxResults": 200,
        })

        if not resp:
            raise ScrapingError("Không thể truy cập Jira API")

        data = resp.json()
        logged_users = set()

        for issue in data.get("issues", []):
            worklogs = issue.get("fields", {}).get("worklog", {}).get("worklogs", [])
            for wl in worklogs:
                started = wl.get("started", "")[:10]
                if started == date_str:
                    author = wl.get("author", {}).get("displayName", "")
                    if author:
                        logged_users.add(author)

        missing = [m for m in self.team_members if m not in logged_users]
        return self._build_result(target_date, list(logged_users), missing, raw=data)

    # ------------------------------------------------------------------
    # Confluence Parser
    # ------------------------------------------------------------------

    def _fetch_confluence(self, target_date: date) -> Dict[str, Any]:
        """Fetch từ Confluence page (nếu log work trên Confluence)."""
        date_str = target_date.strftime("%d/%m/%Y")
        logger.info(f"[LogworkScraper] Fetching Confluence: {self.logwork_url}")

        resp = self.get(self.logwork_url)
        if not resp:
            raise ScrapingError("Không thể truy cập trang Confluence")

        soup = self.parse_html(resp.text)

        # Tìm section của ngày cần kiểm tra
        logged_users = []
        day_section = soup.find(text=lambda t: t and date_str in t)

        if day_section:
            parent = day_section.find_parent()
            if parent:
                # Tìm các tên trong section này
                for li in parent.find_all_next(["li", "td"], limit=50):
                    text = li.get_text(strip=True)
                    for member in self.team_members:
                        if member.lower() in text.lower():
                            logged_users.append(member)

        missing = [m for m in self.team_members if m not in logged_users]
        return self._build_result(target_date, logged_users, missing)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
        target_date: date,
        logged: List[str],
        missing: List[str],
        raw: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "logged": logged,
            "missing": missing,
            "logged_count": len(logged),
            "missing_count": len(missing),
            "raw_data": raw or {},
        }

    def _mock_data(self, target_date: date) -> Dict[str, Any]:
        """
        Mock data khi URL chưa cấu hình.
        Dùng để test bot mà không cần trang nội bộ thực sự.
        """
        members = self.team_members or ["Nguyen Van A", "Tran Thi B", "Le Van C", "Pham Thi D"]
        # Giả lập: 70% người đã log work
        logged = members[:max(1, int(len(members) * 0.7))]
        missing = [m for m in members if m not in logged]

        logger.info(f"[LogworkScraper] Dùng MOCK data cho {target_date}")
        return self._build_result(target_date, logged, missing)
