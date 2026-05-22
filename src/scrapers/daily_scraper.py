"""
Daily Standup Scraper - Kiểm tra ai chưa điền daily.

Trang cha cố định:
  https://10.36.36.63:8618/op_pm/HtmlDocument/Detail/578820bf-...

Luồng:
1. Truy cập trang cha → parse sidebar
2. Tìm link có tên "Daily Meeting X - DD-MMM-YYYY" khớp với hôm nay
3. Truy cập document đó
4. Parse bảng: Member | Hôm qua | Hôm nay | Blockers | Adhoc
5. Ai có cả 2 cột "Hôm qua" + "Hôm nay" đều trống = chưa điền
"""
import re
from datetime import date
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from loguru import logger

from config import get_config
from .base_scraper import BaseScraper


class DailyScraper(BaseScraper):

    # Format tên document: "Daily Meeting 7 - 21-May-2026"
    DAILY_TITLE_PATTERN = re.compile(
        r"Daily Meeting\s+\d+\s*[-–]\s*(\d{1,2}-\w{3}-\d{4})",
        re.IGNORECASE,
    )
    # Format ngày trong tên document: 21-May-2026
    DATE_FORMAT = "%d-%b-%Y"

    def __init__(self):
        super().__init__()
        self.parent_url = self.cfg.daily_parent_url
        self.base_url = self.cfg.base_url
        self.team = self.load_team()
        self.team_names = [m["name"] for m in self.team]

    def get_missing_users(self, target_date: Optional[date] = None) -> List[Dict]:
        """
        Trả về danh sách thành viên chưa điền daily hôm nay.

        Returns:
            List[dict]: [{"name": "...", "position": "..."}]
        """
        result = self.fetch_daily_data(target_date)
        return result.get("missing", [])

    def fetch_daily_data(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Lấy dữ liệu daily standup của ngày chỉ định.

        Returns:
            {
                "date": "2026-05-22",
                "document_url": "...",
                "submitted": [{"name": "...", "position": "..."}],
                "missing": [{"name": "...", "position": "..."}],
                "entries": [{"name": ..., "yesterday": ..., "today": ..., ...}]
            }
        """
        if target_date is None:
            target_date = date.today()

        if not self.parent_url:
            logger.warning("[Daily] INTERNAL_DAILY_PARENT_URL chưa cấu hình → dùng mock data")
            return self._mock_data(target_date)

        # Bước 1: Tìm URL document của ngày hôm nay
        doc_url = self._find_today_document(target_date)
        if not doc_url:
            logger.warning(f"[Daily] Không tìm thấy document ngày {target_date}")
            return self._not_found_result(target_date)

        # Bước 2: Parse bảng daily
        logger.info(f"[Daily] Đọc document: {doc_url}")
        resp = self.get(doc_url)
        if not resp:
            logger.error(f"[Daily] Không tải được document: {doc_url}")
            return self._not_found_result(target_date)

        return self._parse_daily_document(resp.text, target_date, doc_url)

    # ------------------------------------------------------------------
    # Bước 1: Tìm document của hôm nay trong sidebar
    # ------------------------------------------------------------------

    def _find_today_document(self, target_date: date) -> Optional[str]:
        """
        Tìm document daily meeting của ngày chỉ định.

        Navigation tree được nhúng dưới dạng JSON trong HTML trang cha.
        Mỗi entry có dạng: {"id":"uuid","name":"Daily Meeting X - DD-MMM-YYYY",...}
        """
        logger.info(f"[Daily] Tìm document ngày {target_date} trong: {self.parent_url}")
        resp = self.get(self.parent_url)
        if not resp:
            return None

        target_str = target_date.strftime(self.DATE_FORMAT)  # VD: "22-May-2026"
        html = resp.text

        # Lấy parent document ID từ URL
        parent_id = self.parent_url.split("/")[-1].split("?")[0]
        base = self.cfg.base_url.rstrip("/")

        # Parse JSON navigation data nhúng trong HTML
        # Format: {"id":"UUID","parentId":"...","htmlSectionId":"...","name":" Daily Meeting X - DD-MMM-YYYY",...}
        # Dùng \{ để chỉ match "id" ở đầu object JSON (tránh nhầm parentId, htmlSectionId)
        pattern = re.compile(
            r'\{"id":"([0-9a-f\-]{36})"[^}]{0,400}"name":"([^"]*)"',
            re.DOTALL
        )

        for match in pattern.finditer(html):
            nav_id = match.group(1)
            name = match.group(2).strip()  # Strip dấu cách đầu/cuối

            if "daily meeting" not in name.lower():
                continue

            if target_str.lower() in name.lower():
                url = f"{base}/HtmlDocument/Detail/{parent_id}?docNavId={nav_id}"
                logger.info(f"[Daily] Tìm thấy: {name!r} → {url}")
                return url

        logger.warning(f"[Daily] Không tìm thấy document '{target_str}'")

        # Debug: in vài document gần nhất
        recent = re.findall(r'"name"\s*:\s*"(Daily Meeting[^"]+)"', html, re.IGNORECASE)
        if recent:
            logger.debug(f"[Daily] Documents có sẵn (cuối): {recent[-5:]}")
        return None

    # ------------------------------------------------------------------
    # Bước 2: Parse bảng daily trong document
    # ------------------------------------------------------------------

    def _parse_daily_document(
        self, html: str, target_date: date, doc_url: str
    ) -> Dict[str, Any]:
        """
        Parse bảng daily standup.

        Cấu trúc bảng (từ ảnh):
        Member | Hôm qua tôi làm gì? | Hôm nay tôi sẽ làm gì? | Blockers | Adhoc
        """
        soup = self.parse_html(html)

        # Tìm bảng daily (tìm bảng có cột "Member" hoặc "Hôm qua")
        table = self._find_daily_table(soup)
        if not table:
            logger.warning("[Daily] Không tìm thấy bảng daily trong document")
            return self._not_found_result(target_date)

        col_idx = self._detect_daily_columns(table)
        entries = []
        submitted = []
        missing = []

        rows = table.find_all("tr")[1:]  # Bỏ header
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            name = self._get_cell_text(cells, col_idx["member"])
            if not name:
                continue

            yesterday = self._get_cell_text(cells, col_idx["yesterday"])
            today = self._get_cell_text(cells, col_idx["today"])
            blockers = self._get_cell_text(cells, col_idx.get("blockers", -1))

            # Đã điền nếu ít nhất 1 trong 2 cột có nội dung
            is_submitted = bool(yesterday or today)

            entry = {
                "name": name,
                "yesterday": yesterday,
                "today": today,
                "blockers": blockers,
                "submitted": is_submitted,
            }
            entries.append(entry)

            # Đối chiếu với team.json để lấy position
            member_info = self._get_member_info(name)
            person = {"name": name, "position": member_info.get("position", "")}

            if is_submitted:
                submitted.append(person)
            else:
                missing.append(person)

        logger.info(
            f"[Daily] {len(submitted)} đã điền, {len(missing)} chưa điền"
        )

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "document_url": doc_url,
            "submitted": submitted,
            "missing": missing,
            "entries": entries,
        }

    def _find_daily_table(self, soup):
        """Tìm bảng daily standup trong document."""
        keywords = re.compile(r"hôm qua|yesterday|hôm nay|today|member|thành viên", re.I)

        for table in soup.find_all("table"):
            header_text = ""
            first_row = table.find("tr")
            if first_row:
                header_text = first_row.get_text().lower()
            if re.search(r"hôm qua|yesterday|hôm nay|today|member", header_text, re.I):
                return table

        # Fallback: bảng đầu tiên có đủ cột
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if rows and len(rows[0].find_all(["th", "td"])) >= 3:
                return table

        return None

    def _detect_daily_columns(self, table) -> Dict[str, int]:
        """Tự động xác định index các cột quan trọng."""
        # Default theo cấu trúc bảng trong ảnh:
        # 0: Member | 1: Hôm qua | 2: Hôm nay | 3: Blockers | 4: Adhoc
        indices = {"member": 0, "yesterday": 1, "today": 2, "blockers": 3}

        header_row = table.find("tr")
        if not header_row:
            return indices

        cols = header_row.find_all(["th", "td"])
        for i, col in enumerate(cols):
            text = col.get_text(strip=True).lower()
            if re.search(r"member|thành viên|tên", text):
                indices["member"] = i
            elif re.search(r"hôm qua|yesterday|done|làm gì.*qua", text):
                indices["yesterday"] = i
            elif re.search(r"hôm nay|today|plan|sẽ làm", text):
                indices["today"] = i
            elif re.search(r"block|cản trở|impediment", text):
                indices["blockers"] = i

        return indices

    def _get_cell_text(self, cells: list, idx: int) -> str:
        if idx < 0 or idx >= len(cells):
            return ""
        return cells[idx].get_text(separator=" ", strip=True)

    def _get_member_info(self, name: str) -> Dict:
        """Tìm thông tin thành viên trong team.json theo tên."""
        for m in self.team:
            if m["name"].lower() == name.lower():
                return m
            # Fuzzy match: so sánh họ tên tắt
            if name.lower() in m["name"].lower() or m["name"].lower() in name.lower():
                return m
        return {"name": name, "position": ""}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _not_found_result(self, target_date: date) -> Dict[str, Any]:
        """Kết quả khi không tìm thấy document."""
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "document_url": None,
            "submitted": [],
            "missing": [
                {"name": m["name"], "position": m.get("position", "")}
                for m in self.team
            ],
            "entries": [],
            "error": "Không tìm thấy document daily hôm nay",
        }

    def _mock_data(self, target_date: date) -> Dict[str, Any]:
        """Mock data khi URL chưa cấu hình."""
        logger.info("[Daily] Dùng MOCK data")
        submitted = []
        missing = []
        entries = []

        for i, m in enumerate(self.team):
            person = {"name": m["name"], "position": m.get("position", "")}
            if i % 4 != 3:  # 75% đã điền
                submitted.append(person)
                entries.append({
                    "name": m["name"],
                    "yesterday": "Làm task ABC, review code",
                    "today": "Tiếp tục task ABC, họp daily",
                    "blockers": "",
                    "submitted": True,
                })
            else:
                missing.append(person)
                entries.append({
                    "name": m["name"],
                    "yesterday": "",
                    "today": "",
                    "blockers": "",
                    "submitted": False,
                })

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "document_url": None,
            "submitted": submitted,
            "missing": missing,
            "entries": entries,
        }
