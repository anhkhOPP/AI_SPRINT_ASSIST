"""
Base scraper cho các trang web nội bộ.

Hỗ trợ nhiều phương thức xác thực:
- session_cookie: Dùng cookie session từ browser
- basic_auth: HTTP Basic Authentication
- oauth2: Bearer token
- ldap: LDAP (qua Basic Auth)
- form_login: Đăng nhập form HTML (tự động)

QUAN TRỌNG: Trang web nội bộ KHÔNG public ra ngoài.
Scraper chỉ chạy trong mạng nội bộ / VPN.
"""
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import date

import requests
from bs4 import BeautifulSoup
from loguru import logger

from config import get_config


class AuthenticationError(Exception):
    """Lỗi xác thực vào trang nội bộ."""


class ScrapingError(Exception):
    """Lỗi khi scrape dữ liệu."""


class BaseScraper(ABC):
    """
    Lớp cơ sở cho tất cả scrapers.
    Xử lý authentication và HTTP session.
    """

    def __init__(self):
        cfg = get_config()
        self.site_cfg = cfg.internal_site
        self.session = requests.Session()
        self._authenticated = False
        self._setup_session()

    def _setup_session(self):
        """Thiết lập session theo phương thức auth được cấu hình."""
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (AI Sprint Assistant Bot)",
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
        })

        auth_type = self.site_cfg.auth_type.lower()

        if auth_type == "session_cookie":
            self._setup_cookie_auth()
        elif auth_type in ("basic_auth", "ldap"):
            self._setup_basic_auth()
        elif auth_type == "oauth2":
            self._setup_oauth2()
        elif auth_type == "form_login":
            # Form login sẽ được xử lý khi gọi lần đầu
            pass
        else:
            logger.warning(f"Phương thức auth không xác định: {auth_type}")

    def _setup_cookie_auth(self):
        """Thiết lập xác thực qua session cookie."""
        cookie_value = self.site_cfg.session_cookie
        cookie_name = self.site_cfg.cookie_name

        if not cookie_value:
            logger.warning("Session cookie chưa được cấu hình (INTERNAL_SESSION_COOKIE)")
            return

        self.session.cookies.set(
            cookie_name,
            cookie_value,
            domain=self._extract_domain(self.site_cfg.logwork_url),
        )
        self._authenticated = True
        logger.info(f"[Auth] Đã thiết lập cookie auth: {cookie_name}=***")

    def _setup_basic_auth(self):
        """Thiết lập HTTP Basic Authentication."""
        username = self.site_cfg.username
        password = self.site_cfg.password

        if not username or not password:
            logger.warning("Username/Password chưa được cấu hình")
            return

        self.session.auth = (username, password)
        self._authenticated = True
        logger.info(f"[Auth] Đã thiết lập basic auth cho user: {username}")

    def _setup_oauth2(self):
        """Thiết lập OAuth2 Bearer token."""
        token = self.site_cfg.oauth_token

        if not token:
            logger.warning("OAuth token chưa được cấu hình (INTERNAL_OAUTH_TOKEN)")
            return

        self.session.headers["Authorization"] = f"Bearer {token}"
        self._authenticated = True
        logger.info("[Auth] Đã thiết lập OAuth2 Bearer token")

    def do_form_login(self, login_url: str, username_field: str = "username", password_field: str = "password") -> bool:
        """
        Đăng nhập qua form HTML.
        Tự động tìm và submit form đăng nhập.
        """
        username = self.site_cfg.username
        password = self.site_cfg.password

        if not username or not password:
            logger.error("[Auth] Chưa cấu hình username/password cho form login")
            return False

        try:
            # Lấy trang đăng nhập để lấy CSRF token
            resp = self.session.get(login_url, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")

            # Tìm CSRF token (nếu có)
            csrf_token = None
            csrf_input = soup.find("input", {"name": ["csrf_token", "_token", "authenticity_token"]})
            if csrf_input:
                csrf_token = csrf_input.get("value", "")

            # Submit form
            form_data = {
                username_field: username,
                password_field: password,
            }
            if csrf_token:
                form_data["csrf_token"] = csrf_token

            login_resp = self.session.post(login_url, data=form_data, timeout=10)

            # Kiểm tra đăng nhập thành công (dựa vào redirect hoặc nội dung)
            if login_resp.status_code in (200, 302):
                self._authenticated = True
                logger.info(f"[Auth] Form login thành công cho {username}")
                return True

            logger.error(f"[Auth] Form login thất bại: {login_resp.status_code}")
            return False

        except requests.RequestException as e:
            logger.error(f"[Auth] Lỗi form login: {e}")
            return False

    def get(self, url: str, params: Optional[Dict] = None, retry: int = 3) -> Optional[requests.Response]:
        """GET request với retry logic."""
        for attempt in range(retry):
            try:
                resp = self.session.get(url, params=params, timeout=15)

                if resp.status_code == 401:
                    raise AuthenticationError(f"Xác thực thất bại (401) khi truy cập: {url}")
                if resp.status_code == 403:
                    raise AuthenticationError(f"Không có quyền truy cập (403): {url}")
                if resp.status_code == 404:
                    raise ScrapingError(f"Không tìm thấy trang (404): {url}")
                if resp.status_code >= 500:
                    raise ScrapingError(f"Lỗi server ({resp.status_code}): {url}")

                resp.raise_for_status()
                return resp

            except AuthenticationError:
                raise
            except (requests.RequestException, ScrapingError) as e:
                if attempt < retry - 1:
                    wait = 2 ** attempt
                    logger.warning(f"[Scraper] Retry {attempt + 1}/{retry} sau {wait}s: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"[Scraper] Thất bại sau {retry} lần thử: {e}")
                    return None

        return None

    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML với lxml parser."""
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Trích xuất domain từ URL."""
        if not url:
            return ""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""

    @abstractmethod
    def fetch_data(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Lấy dữ liệu từ trang web. Subclass phải implement."""

    @abstractmethod
    def get_missing_users(self, target_date: Optional[date] = None) -> List[str]:
        """Lấy danh sách người chưa thực hiện. Subclass phải implement."""
