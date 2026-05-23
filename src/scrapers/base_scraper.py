"""
Base Scraper - xử lý login ASP.NET Identity Server + OIDC flow.

Luồng đăng nhập:
  1. GET op_pm (8618) → redirect → trang login Identity Server (8611)
  2. POST credentials → redirect → OIDC callback (8611/connect/authorize/callback)
  3. Trang callback chứa form auto-submit → POST về op_pm/signin-oidc (8618)
  4. op_pm set session cookie → đăng nhập thành công
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
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
        })
        self._logged_in = False

    # ------------------------------------------------------------------
    # Public: đảm bảo đã login trước khi dùng
    # ------------------------------------------------------------------

    def ensure_logged_in(self) -> bool:
        if not self._logged_in:
            return self.login()
        return True

    def login(self) -> bool:
        """
        Đăng nhập vào op_pm qua ASP.NET Identity Server (OIDC).

        Bước 1: GET op_pm → auto redirect về login page (8611)
        Bước 2: Lấy CSRF token + hidden fields từ form login
        Bước 3: POST credentials → redirect về OIDC callback page
        Bước 4: Parse form_post trong callback page
        Bước 5: POST form_post về signin-oidc của op_pm (8618)
        Bước 6: Kiểm tra session cookie của op_pm đã được set chưa
        """
        base_url = self.cfg.base_url
        logger.info(f"[Auth] Bắt đầu đăng nhập: {base_url}")

        try:
            # --- Bước 1: GET base URL → redirect về trang login ---
            r1 = self.session.get(base_url, timeout=15, allow_redirects=True)
            login_page_url = r1.url
            logger.debug(f"[Auth] Trang login: {login_page_url}")

            # --- Bước 2: Lấy hidden fields từ form login ---
            soup1 = BeautifulSoup(r1.text, "lxml")
            form_data = self._extract_all_form_fields(soup1)
            form_data[self.cfg.login_field_username] = self.cfg.username
            form_data[self.cfg.login_field_password] = self.cfg.password
            form_data["RememberLogin"] = "true"
            form_data["button"] = "login"

            logger.debug(f"[Auth] POST fields: {[k for k in form_data if 'pass' not in k.lower()]}")

            # --- Bước 3: POST credentials với allow_redirects=True ---
            # requests sẽ follow redirect tới trang OIDC callback (status=200)
            r2 = self.session.post(
                login_page_url,
                data=form_data,
                timeout=20,
                allow_redirects=True,
            )
            logger.debug(f"[Auth] After POST login: url={r2.url} status={r2.status_code}")

            current_resp = r2

            # --- Bước 4 & 5: Nếu gặp OIDC form_post → submit thủ công ---
            # Trang callback chứa form auto-submit về /signin-oidc
            # requests không chạy JS nên phải submit tay
            if current_resp.status_code == 200:
                oidc_form = self._find_oidc_form(current_resp.text)
                if oidc_form:
                    action_url, oidc_data = oidc_form
                    logger.info(f"[Auth] OIDC form_post → {action_url}")
                    r3 = self.session.post(
                        action_url,
                        data=oidc_data,
                        timeout=20,
                        allow_redirects=True,
                    )
                    current_resp = r3
                    logger.debug(f"[Auth] After signin-oidc: {current_resp.url} status={current_resp.status_code}")
                else:
                    logger.debug(f"[Auth] Không có OIDC form (có thể đã logged in), URL: {current_resp.url}")

            # --- Bước 6: Kiểm tra đã vào được op_pm chưa ---
            if self._is_logged_in(current_resp):
                self._logged_in = True
                logger.info(f"[Auth] ✅ Login successful: {self.cfg.username}")
                return True

            logger.error(f"[Auth] Login failed. URL cuối: {current_resp.url}")
            return False

        except requests.RequestException as e:
            logger.error(f"[Auth] Connection error: {e}")
            return False

    def _follow_redirects(self, resp: requests.Response, max_steps: int = 10) -> Optional[requests.Response]:
        """Follow redirect thủ công, trả về response đầu tiên có status 200."""
        current = resp
        for step in range(max_steps):
            if current.status_code == 200:
                return current

            if current.status_code in (301, 302, 303, 307, 308):
                location = current.headers.get("Location", "")
                if not location:
                    return current

                # Tạo URL đầy đủ nếu là relative URL
                if location.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(current.url)
                    location = f"{parsed.scheme}://{parsed.netloc}{location}"

                logger.debug(f"[Auth] Redirect {step+1}: {location}")
                try:
                    current = self.session.get(location, timeout=15, allow_redirects=False)
                except requests.RequestException as e:
                    logger.error(f"[Auth] Lỗi redirect: {e}")
                    return None
            else:
                return current

        logger.warning(f"[Auth] Quá nhiều redirect (>{max_steps})")
        return current

    def _find_oidc_form(self, html: str) -> Optional[tuple]:
        """
        Tìm OIDC form_post trong HTML.
        Form có action trỏ về /signin-oidc và chứa code/state.

        Returns: (action_url, form_data_dict) hoặc None
        """
        soup = BeautifulSoup(html, "lxml")

        for form in soup.find_all("form"):
            action = form.get("action", "")
            method = form.get("method", "get").lower()

            if method != "post":
                continue

            # Kiểm tra action trỏ về signin-oidc
            if "signin-oidc" not in action and "signin" not in action.lower():
                continue

            # Lấy tất cả hidden inputs
            form_data = {}
            for inp in form.find_all("input"):
                name = inp.get("name", "")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value

            # Xác nhận có code/state (đây là OIDC response)
            if "code" in form_data or "state" in form_data:
                logger.debug(f"[Auth] Found OIDC form: action={action}, fields={list(form_data.keys())}")
                return action, form_data

        # Fallback: lấy form đầu tiên có method=post và có hidden inputs
        for form in soup.find_all("form"):
            if form.get("method", "get").lower() == "post":
                action = form.get("action", "")
                if not action:
                    continue
                form_data = {}
                for inp in form.find_all("input", {"type": "hidden"}):
                    name = inp.get("name", "")
                    if name:
                        form_data[name] = inp.get("value", "")
                if form_data and ("code" in form_data or "state" in form_data):
                    logger.debug(f"[Auth] OIDC form (fallback): action={action}")
                    return action, form_data

        return None

    def _extract_all_form_fields(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Lấy tất cả hidden fields từ form đầu tiên."""
        form_data = {}
        form = soup.find("form")
        if form:
            for inp in form.find_all("input", {"type": "hidden"}):
                name = inp.get("name", "")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value
        return form_data

    def _is_logged_in(self, resp: requests.Response) -> bool:
        """Kiểm tra đã đăng nhập thành công vào op_pm chưa."""
        url = resp.url.lower()

        # Đang ở op_pm = thành công
        if "/op_pm" in url and "login" not in url:
            return True

        # Vẫn ở trang login = thất bại
        if "/account/login" in url or "/login?" in url:
            return False

        # Kiểm tra HTML: nếu vẫn có form đăng nhập = thất bại
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            has_username = soup.find("input", {"name": re.compile(r"^Username$", re.I)})
            has_password = soup.find("input", {"type": "password"})
            if has_username and has_password:
                return False

        return resp.status_code == 200

    # ------------------------------------------------------------------
    # HTTP GET với auto re-login
    # ------------------------------------------------------------------

    def get(self, url: str, params: Optional[Dict] = None, retry: int = 2) -> Optional[requests.Response]:
        """GET với tự động re-login khi session hết hạn."""
        self.ensure_logged_in()

        for attempt in range(retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20, allow_redirects=True)

                # Bị redirect về login → session hết hạn
                if "/account/login" in resp.url.lower() or "/login?" in resp.url.lower():
                    if attempt < retry:
                        logger.info("[Auth] Session expired, re-logging in...")
                        self._logged_in = False
                        if self.login():
                            continue
                    logger.error("[Auth] Re-login failed")
                    return None

                if resp.status_code == 200:
                    return resp

                logger.warning(f"[Scraper] HTTP {resp.status_code}: {url}")
                return None

            except requests.RequestException as e:
                if attempt < retry:
                    wait = 2 ** attempt
                    logger.warning(f"[Scraper] Retry {attempt+1}/{retry} sau {wait}s: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"[Scraper] Thất bại: {e}")
                    return None
        return None

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def load_team() -> List[Dict[str, Any]]:
        """Đọc danh sách thành viên từ team.json."""
        import json
        from pathlib import Path
        team_file = Path("team.json")
        if not team_file.exists():
            logger.warning("[Scraper] team.json not found")
            return []
        try:
            with open(team_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[Scraper] Error reading team.json: {e}")
            return []

    @abstractmethod
    def get_missing_users(self, target_date: Optional[date] = None) -> List[str]:
        pass
