"""
Base Scraper với tự động đăng nhập form HTML.

Luồng xác thực:
1. POST username/password vào login endpoint
2. Server trả về session cookie → lưu vào session
3. Dùng session đó cho các request tiếp theo
4. Khi nhận 401 hoặc bị redirect về trang login → tự đăng nhập lại
5. Retry request gốc sau khi đăng nhập lại thành công
"""
import re
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import date

import requests
import urllib3
from bs4 import BeautifulSoup
from loguru import logger

from config import get_config

# Tắt warning SSL cho cert tự ký (internal server)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LoginError(Exception):
    pass


class ScrapingError(Exception):
    pass


class BaseScraper(ABC):

    def __init__(self):
        cfg = get_config()
        self.cfg = cfg.internal
        self.session = requests.Session()
        self.session.verify = False  # Bỏ qua SSL tự ký
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
        })
        self._logged_in = False

    # ------------------------------------------------------------------
    # Login tự động
    # ------------------------------------------------------------------

    def ensure_logged_in(self) -> bool:
        """Đảm bảo đã đăng nhập trước khi gửi request."""
        if not self._logged_in:
            return self.login()
        return True

    def login(self) -> bool:
        """
        Đăng nhập vào op_pm (ASP.NET Identity Server / OpenID Connect).

        Luồng:
        1. GET base URL → tự redirect về trang login
        2. Lấy CSRF token + ReturnUrl từ hidden fields trong form
        3. POST Username + Password + hidden fields
        4. Server redirect về op_pm qua OIDC callback
        """
        base_url = self.cfg.base_url
        logger.info(f"[Auth] Đang đăng nhập vào: {base_url}")

        try:
            # Bước 1: GET base URL, sẽ tự redirect về trang login
            resp = self.session.get(base_url, timeout=15, allow_redirects=True)
            actual_login_url = resp.url  # URL thực của trang login sau redirect
            logger.debug(f"[Auth] Trang login thực tế: {actual_login_url}")

            soup = BeautifulSoup(resp.text, "lxml")

            # Bước 2: Lấy tất cả hidden fields (CSRF token, ReturnUrl, ...)
            form_data = {}
            form = soup.find("form")
            if form:
                for hidden in form.find_all("input", {"type": "hidden"}):
                    name = hidden.get("name", "")
                    value = hidden.get("value", "")
                    if name:
                        form_data[name] = value
                        logger.debug(f"[Auth] Hidden field: {name}")

            # Bước 3: Điền thông tin đăng nhập
            form_data[self.cfg.login_field_username] = self.cfg.username
            form_data[self.cfg.login_field_password] = self.cfg.password
            form_data["RememberLogin"] = "true"
            form_data["button"] = "login"

            # Bước 4: POST form
            login_resp = self.session.post(
                actual_login_url,
                data=form_data,
                timeout=20,
                allow_redirects=True,
            )

            # Bước 5: Kiểm tra kết quả
            if self._is_login_successful(login_resp):
                self._logged_in = True
                logger.info(f"[Auth] ✅ Đăng nhập thành công: {self.cfg.username}")
                return True

            logger.error(f"[Auth] ❌ Đăng nhập thất bại (status={login_resp.status_code})")
            logger.debug(f"[Auth] URL sau login: {login_resp.url}")
            return False

        except requests.RequestException as e:
            logger.error(f"[Auth] Lỗi kết nối khi đăng nhập: {e}")
            return False

    def _is_login_successful(self, resp: requests.Response) -> bool:
        """
        Xác định đăng nhập thành công hay không.
        Logic: Nếu sau POST không bị redirect về trang login = thành công.
        """
        final_url = resp.url.lower()
        login_indicators = ["/login", "/signin", "/auth", "login="]

        # Nếu URL cuối cùng vẫn là trang login → thất bại
        for indicator in login_indicators:
            if indicator in final_url:
                return False

        # Kiểm tra response có chứa form login không
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            login_form = soup.find("form", {"action": re.compile(r"login|signin|auth", re.I)})
            if login_form:
                return False

        return resp.status_code in (200, 302)

    def _extract_csrf(self, html: str) -> Optional[str]:
        """Tìm CSRF token trong HTML."""
        soup = BeautifulSoup(html, "lxml")
        for name in ["csrf_token", "_token", "csrfmiddlewaretoken", "__RequestVerificationToken"]:
            inp = soup.find("input", {"name": name})
            if inp:
                return inp.get("value", "")
        # Tìm trong meta tag
        meta = soup.find("meta", {"name": re.compile(r"csrf", re.I)})
        if meta:
            return meta.get("content", "")
        return None

    # ------------------------------------------------------------------
    # HTTP requests với auto re-login
    # ------------------------------------------------------------------

    def get(self, url: str, params: Optional[Dict] = None, retry: int = 2) -> Optional[requests.Response]:
        """GET request với tự động re-login khi session hết hạn."""
        self.ensure_logged_in()

        for attempt in range(retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20, allow_redirects=True)

                # Bị redirect về trang login → session hết hạn
                if self._is_redirected_to_login(resp):
                    if attempt < retry:
                        logger.info("[Auth] Session hết hạn, đang đăng nhập lại...")
                        self._logged_in = False
                        if self.login():
                            continue
                    logger.error("[Auth] Không thể đăng nhập lại")
                    return None

                if resp.status_code == 200:
                    return resp

                logger.warning(f"[Scraper] HTTP {resp.status_code}: {url}")
                return None

            except requests.RequestException as e:
                if attempt < retry:
                    wait = 2 ** attempt
                    logger.warning(f"[Scraper] Retry {attempt + 1}/{retry} sau {wait}s: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"[Scraper] Thất bại sau {retry + 1} lần: {e}")
                    return None

        return None

    def _is_redirected_to_login(self, resp: requests.Response) -> bool:
        """Kiểm tra có bị redirect về trang login không."""
        url = resp.url.lower()
        return any(x in url for x in ["/login", "/signin", "/auth/login"])

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    # ------------------------------------------------------------------
    # Load team members
    # ------------------------------------------------------------------

    @staticmethod
    def load_team() -> List[Dict[str, Any]]:
        """Đọc danh sách thành viên từ team.json."""
        import json
        from pathlib import Path

        team_file = Path("team.json")
        if not team_file.exists():
            logger.warning("[Scraper] Không tìm thấy team.json")
            return []
        try:
            with open(team_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[Scraper] Lỗi đọc team.json: {e}")
            return []

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_missing_users(self, target_date: Optional[date] = None) -> List[str]:
        pass
