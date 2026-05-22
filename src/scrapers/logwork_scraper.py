"""
Logwork Scraper - Kiểm tra ai chưa log đủ giờ.

Trang: https://10.36.36.63:8618/op_pm/Worklog?fav=...
URL đã có filter "Yesterday" sẵn → truy cập là có dữ liệu hôm qua.

Bảng hiển thị: Task | User | Date | Activity | Time spent | Work notes

Logic:
- Parse toàn bộ bảng
- Group by User → cộng tổng Time spent
- Ai tổng < 7.5h hoặc không xuất hiện = chưa đủ log work
"""
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from loguru import logger

from config import get_config
from .base_scraper import BaseScraper, ScrapingError


class LogworkScraper(BaseScraper):

    def __init__(self):
        super().__init__()
        self.worklog_url = self.cfg.worklog_url
        self.min_hours = self.cfg.logwork_min_hours
        self.team = self.load_team()
        self.team_names = [m["name"] for m in self.team]

    def get_missing_users(self, target_date: Optional[date] = None) -> List[str]:
        """
        Trả về danh sách thành viên chưa log đủ giờ.

        Returns:
            List[dict]: [{"name": "...", "position": "...", "logged_hours": 0.0}]
        """
        result = self.fetch_logwork_data()
        return result.get("missing", [])

    def fetch_logwork_data(self) -> Dict[str, Any]:
        """
        Lấy toàn bộ dữ liệu logwork từ trang.

        Returns:
            {
                "logged": [{"name": "...", "position": "...", "hours": 8.0}],
                "missing": [{"name": "...", "position": "...", "hours": 0.0}],
                "summary": {"total_hours": 30.0, "logged_count": 5, "missing_count": 1}
            }
        """
        if not self.worklog_url:
            logger.warning("[Logwork] INTERNAL_WORKLOG_URL chưa cấu hình → dùng mock data")
            return self._mock_data()

        logger.info(f"[Logwork] Fetching: {self.worklog_url}")
        resp = self.get(self.worklog_url)

        if not resp:
            logger.error("[Logwork] Không thể tải trang worklog")
            return self._mock_data()

        return self._parse_page(resp.text)

    def _parse_page(self, html: str) -> Dict[str, Any]:
        """Parse HTML bảng Time Spent."""
        soup = self.parse_html(html)

        # Tìm bảng chứa dữ liệu worklog
        # Trang op_pm có cột: Task | User | Date | Activity | Time spent | Work notes
        table = self._find_worklog_table(soup)

        if not table:
            logger.warning("[Logwork] Không tìm thấy bảng dữ liệu")
            return self._build_result({})

        # Parse từng dòng → tích lũy giờ theo user
        user_hours: Dict[str, float] = {}

        rows = table.find_all("tr")
        header_row = rows[0] if rows else None
        col_index = self._detect_column_index(header_row)

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            user = self._extract_user(cells, col_index.get("user", 1))
            hours = self._extract_hours(cells, col_index.get("time_spent", 4))

            if user:
                user_hours[user] = user_hours.get(user, 0.0) + hours

        logger.info(f"[Logwork] Parsed {len(user_hours)} users: {user_hours}")
        return self._build_result(user_hours)

    def _find_worklog_table(self, soup):
        """Tìm bảng worklog trong HTML."""
        # Thử theo class/id phổ biến
        for selector in [
            {"class": re.compile(r"worklog|time.?spent|timesheet", re.I)},
            {"id": re.compile(r"worklog|timespent|timesheet", re.I)},
        ]:
            table = soup.find("table", selector)
            if table:
                return table

        # Fallback: tìm bảng có header chứa "User" và "Time"
        for table in soup.find_all("table"):
            header_text = table.get_text().lower()
            if "user" in header_text and ("time" in header_text or "spent" in header_text):
                return table

        # Cuối cùng: lấy bảng đầu tiên có đủ cột
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if rows and len(rows[0].find_all(["th", "td"])) >= 4:
                return table

        return None

    def _detect_column_index(self, header_row) -> Dict[str, int]:
        """Tự động xác định index của cột User và Time Spent."""
        indices = {"user": 1, "time_spent": 4}  # default theo ảnh chụp

        if not header_row:
            return indices

        cols = header_row.find_all(["th", "td"])
        for i, col in enumerate(cols):
            text = col.get_text(strip=True).lower()
            if text in ("user", "người dùng", "member", "nhân viên"):
                indices["user"] = i
            elif "time" in text or "spent" in text or "giờ" in text or "hours" in text:
                indices["time_spent"] = i

        return indices

    def _extract_user(self, cells, user_col_idx: int) -> Optional[str]:
        """Lấy tên user từ cell."""
        if user_col_idx >= len(cells):
            return None
        cell = cells[user_col_idx]

        # Thử lấy từ title attribute, alt text, hoặc text thuần
        user = (
            cell.get("title")
            or cell.find("img", {"alt": True}) and cell.find("img")["alt"]
            or cell.get_text(strip=True)
        )
        return user.strip() if user else None

    def _extract_hours(self, cells, time_col_idx: int) -> float:
        """
        Parse số giờ từ cell.
        Hỗ trợ: "7.5h", "7,5h", "7.5", "7h30m", "450m"
        """
        if time_col_idx >= len(cells):
            return 0.0

        text = cells[time_col_idx].get_text(strip=True).lower()
        if not text or text in ("-", "n/a", "0"):
            return 0.0

        # Dạng "7h30m" hoặc "7h 30m"
        hm_match = re.search(r"(\d+)\s*h\s*(\d+)\s*m", text)
        if hm_match:
            return int(hm_match.group(1)) + int(hm_match.group(2)) / 60

        # Dạng "450m" (phút)
        m_match = re.match(r"^(\d+)\s*m$", text)
        if m_match:
            return int(m_match.group(1)) / 60

        # Dạng "7.5h" hoặc "7,5h" hoặc "7.5"
        num_match = re.search(r"[\d.,]+", text)
        if num_match:
            num_str = num_match.group(0).replace(",", ".")
            try:
                return float(num_str)
            except ValueError:
                pass

        return 0.0

    def _build_result(self, user_hours: Dict[str, float]) -> Dict[str, Any]:
        """
        Đối chiếu với team.json, phân loại logged / missing.
        """
        logged = []
        missing = []

        for member in self.team:
            name = member["name"]
            position = member.get("position", "")
            hours = user_hours.get(name, 0.0)

            entry = {"name": name, "position": position, "hours": hours}

            if hours >= self.min_hours:
                logged.append(entry)
            else:
                missing.append(entry)

        # Người log work nhưng không trong team.json
        for user, hours in user_hours.items():
            if user not in self.team_names:
                logger.debug(f"[Logwork] User ngoài team: {user} ({hours}h)")

        total_hours = sum(user_hours.values())
        logger.info(
            f"[Logwork] Kết quả: {len(logged)} đủ giờ, {len(missing)} thiếu "
            f"(ngưỡng: {self.min_hours}h)"
        )

        return {
            "logged": logged,
            "missing": missing,
            "summary": {
                "total_hours": round(total_hours, 1),
                "logged_count": len(logged),
                "missing_count": len(missing),
                "min_hours": self.min_hours,
            },
        }

    def _mock_data(self) -> Dict[str, Any]:
        """Mock data khi URL chưa cấu hình - dùng để test."""
        logger.info("[Logwork] Dùng MOCK data")
        user_hours = {}
        for i, m in enumerate(self.team):
            # 70% đủ giờ, 30% thiếu
            user_hours[m["name"]] = 8.0 if i % 3 != 2 else 3.0
        return self._build_result(user_hours)
