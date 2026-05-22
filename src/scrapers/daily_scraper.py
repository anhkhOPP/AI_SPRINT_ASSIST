"""
Daily Standup Scraper - Kiểm tra ai chưa điền daily.

Trang Print URL trả về toàn bộ HTML tĩnh chứa tất cả daily meetings.
Không cần Playwright - requests đọc được trực tiếp.

Luồng:
1. GET Print URL của document → nhận HTML tĩnh 1.6MB chứa tất cả meetings
2. Tìm vị trí ngày cần check (VD: "22-May-2026")
3. Tìm <table sau vị trí đó → extract HTML bảng
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
        Dùng Print URL để lấy HTML tĩnh chứa toàn bộ các meetings.
        """
        if target_date is None:
            target_date = date.today()

        if not self.parent_url:
            logger.warning("[Daily] INTERNAL_DAILY_PARENT_URL chưa cấu hình → dùng mock data")
            return self._mock_data(target_date)

        # Lấy parent document ID từ URL
        parent_id = self.parent_url.split("/")[-1].split("?")[0]
        base = self.cfg.base_url.rstrip("/")
        print_url = f"{base}/HtmlDocument/Print/{parent_id}"

        logger.info(f"[Daily] GET Print URL: {print_url}")
        resp = self.get(print_url)
        if not resp:
            logger.error("[Daily] Không tải được Print URL")
            return self._not_found_result(target_date)

        return self._parse_print_html(resp.text, target_date, print_url)

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
    # Parse Print HTML (toàn bộ document tĩnh)
    # ------------------------------------------------------------------

    def _parse_print_html(self, html: str, target_date: date, doc_url: str) -> Dict[str, Any]:
        """
        Parse HTML từ Print URL.
        Tìm ngày target_date → lấy <table ngay sau đó → parse bảng.
        """
        target_str = target_date.strftime(self.DATE_FORMAT)  # VD: "22-May-2026"

        # Tìm vị trí của ngày cần check
        idx = html.find(target_str)
        if idx < 0:
            logger.warning(f"[Daily] Không tìm thấy '{target_str}' trong Print HTML")
            return self._not_found_result(target_date)

        logger.info(f"[Daily] Tìm thấy '{target_str}' tại vị trí {idx}")

        # Tìm <table sau vị trí ngày đó
        table_start = html.find("<table", idx)
        if table_start < 0:
            logger.warning(f"[Daily] Không tìm thấy <table sau '{target_str}'")
            return self._not_found_result(target_date)

        # Tìm </table> tương ứng (có thể lồng nhau)
        table_end = html.find("</table>", table_start)
        if table_end < 0:
            return self._not_found_result(target_date)
        table_end += len("</table>")

        table_html = html[table_start:table_end]
        logger.info(f"[Daily] Extracted table HTML: {len(table_html)} ký tự")

        # Parse bảng với BeautifulSoup
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(f"<html><body>{table_html}</body></html>", "html.parser")
        table = soup.find("table")

        if not table:
            logger.warning("[Daily] Không parse được bảng từ HTML")
            return self._not_found_result(target_date)

        return self._parse_table(table, target_date, doc_url)

    def _parse_table(self, table, target_date: date, doc_url: str) -> Dict[str, Any]:
        """Parse bảng daily standup đã tìm thấy."""
        col_idx = self._detect_daily_columns(table)
        entries = []
        submitted = []
        missing = []

        rows = table.find_all("tr")[1:]  # Bỏ header
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            name = self._get_cell_text(cells, col_idx["member"]).strip()
            if not name:
                continue

            yesterday = self._get_cell_text(cells, col_idx["yesterday"])
            today = self._get_cell_text(cells, col_idx["today"])
            blockers = self._get_cell_text(cells, col_idx.get("blockers", -1))

            # Đã điền nếu ít nhất 1 trong 2 cột có nội dung thực
            is_submitted = bool(
                yesterday.strip() and yesterday.strip() not in ("", "\xa0", "&nbsp;")
                or today.strip() and today.strip() not in ("", "\xa0", "&nbsp;")
            )

            entry = {
                "name": name,
                "yesterday": yesterday,
                "today": today,
                "blockers": blockers,
                "submitted": is_submitted,
            }
            entries.append(entry)

            member_info = self._get_member_info(name)
            person = {"name": name, "position": member_info.get("position", "")}

            if is_submitted:
                submitted.append(person)
            else:
                missing.append(person)

        logger.info(f"[Daily] {len(submitted)} đã điền, {len(missing)} chưa điền")

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "document_url": doc_url,
            "submitted": submitted,
            "missing": missing,
            "entries": entries,
        }

    # ------------------------------------------------------------------
    # Bước 2: Render trang bằng Playwright (backup - không cần nữa)
    # ------------------------------------------------------------------

    def _fetch_rendered_html(self, url: str) -> Optional[str]:
        """
        Dùng Playwright để render trang có JavaScript.
        Playwright tự login vào op_pm (OIDC flow) rồi mở trang cần đọc.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright chưa được cài. Chạy:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        base_url = self.cfg.base_url
        username = self.cfg.username
        password = self.cfg.password

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--ignore-certificate-errors", "--no-sandbox"],
            )
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            try:
                # Bước 1: Mở op_pm → redirect về login page
                page.goto(base_url, timeout=20000, wait_until="domcontentloaded")

                # Bước 2: Điền form login
                page.wait_for_selector("input[name='Username']", timeout=10000)
                page.fill("input[name='Username']", username)
                page.fill("input[name='Password']", password)
                page.click("button[value='login']")

                # Bước 3: Chờ redirect về op_pm sau OIDC flow
                page.wait_for_url(f"**/op_pm/**", timeout=20000)
                logger.info(f"[Playwright] Đăng nhập thành công, URL: {page.url[:60]}")

                # Bước 4: Mở trang document cần đọc
                page.goto(url, timeout=20000, wait_until="networkidle")

                # Bước 5: Chờ nội dung daily table render
                try:
                    page.wait_for_selector("table", timeout=15000)
                    # Chờ thêm để đảm bảo render xong
                    page.wait_for_timeout(2000)
                except Exception:
                    logger.warning("[Playwright] Timeout chờ bảng, lấy HTML hiện tại")

                html = page.content()
                logger.info(f"[Playwright] HTML length: {len(html)}")
                return html

            except Exception as e:
                logger.error(f"[Playwright] Lỗi: {e}")
                return None
            finally:
                browser.close()

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
