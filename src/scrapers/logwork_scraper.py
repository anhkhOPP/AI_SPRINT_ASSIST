"""
Logwork Scraper - dùng DataTables POST API của op_pm.

API endpoint: POST https://10.36.36.63:8618/op_pm/WorkLog
Response JSON: {"data": [{"logByUserId": "uuid", "spentTime": 7.5, "logByUser": {"item1": "Hoang Anh"}, ...}]}

Logic:
- Group by logByUserId → cộng tổng spentTime
- Match UUID với team.json → lấy tên đầy đủ + position
- Ai tổng < 7.5h hoặc không log = missing
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from loguru import logger

from config import get_config
from .base_scraper import BaseScraper


class LogworkScraper(BaseScraper):

    # DataTables column definitions (bắt buộc phải gửi)
    COLUMNS = [
        {"data": "issue.title",             "orderable": "false"},
        {"data": "logByUser.item1",          "orderable": "false"},
        {"data": "logTime",                  "orderable": "true"},
        {"data": "activityTypeEnum.name",   "orderable": "false"},
        {"data": "spentTime",               "orderable": "false"},
        {"data": "notes",                   "orderable": "false"},
        {"data": "issue.issueTypeEnum.name","orderable": "true"},
        {"data": "id",                      "orderable": "false"},
    ]

    def __init__(self):
        super().__init__()
        self.api_url = self._build_api_url()
        self.min_hours = self.cfg.logwork_min_hours
        self.team = self.load_team()

    def _build_api_url(self) -> str:
        """Lấy API URL từ INTERNAL_WORKLOG_URL (thay path cuối)."""
        worklog_url = self.cfg.worklog_url
        if worklog_url:
            # Lấy base URL và replace path
            from urllib.parse import urlparse
            parsed = urlparse(worklog_url)
            return f"{parsed.scheme}://{parsed.netloc}/op_pm/WorkLog"
        return self.cfg.base_url.rstrip("/") + "/../WorkLog"

    def get_missing_users(self, target_date: Optional[date] = None) -> List[Dict]:
        result = self.fetch_logwork_data(target_date)
        return result.get("missing", [])

    def fetch_logwork_data(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Lấy dữ liệu log work qua DataTables POST API.
        """
        if target_date is None:
            target_date = self._get_last_workday()

        if not self.cfg.worklog_url:
            logger.warning("[Logwork] INTERNAL_WORKLOG_URL not set → using mock")
            return self._mock_data()

        self.ensure_logged_in()

        date_str = target_date.strftime("%-d/%b/%Y")  # VD: "21/May/2026"
        date_range = f"{date_str} - {date_str}"

        uid_list = [m.get("uid", "") for m in self.team if m.get("uid")]

        post_data = self._build_post_data(date_range, uid_list)

        logger.info(f"[Logwork] POST API: {self.api_url} | date={date_range}")

        try:
            resp = self.session.post(
                self.api_url,
                data=post_data,
                timeout=20,
                allow_redirects=True,
            )

            if resp.status_code != 200:
                logger.error(f"[Logwork] API error: {resp.status_code}")
                return self._mock_data()

            data = resp.json()
            return self._parse_api_response(data, target_date)

        except Exception as e:
            logger.error(f"[Logwork] Lỗi: {e}")
            return self._mock_data()

    def _build_post_data(self, date_range: str, uid_list: List[str]) -> list:
        """Xây dựng DataTables POST parameters."""
        params = [
            ("draw", "1"),
            ("start", "0"),
            ("length", "500"),
            ("search[value]", ""),
            ("search[regex]", "false"),
            ("order[0][column]", "2"),
            ("order[0][dir]", "desc"),
            ("ws", ""),
            ("pId", ""),
            ("cId", ""),
            ("issueId", ""),
            ("activityTypeExcluded", "false"),
            ("pTypeExcluded", "false"),
            ("custExcluded", "false"),
            ("partnerExcluded", "false"),
            ("drt", "0"),
            ("dateRange", date_range),
            ("groupBy", ""),
            ("includeRef", "true"),
        ]

        # Thêm column definitions
        for i, col in enumerate(self.COLUMNS):
            params += [
                (f"columns[{i}][data]", col["data"]),
                (f"columns[{i}][name]", ""),
                (f"columns[{i}][searchable]", "true"),
                (f"columns[{i}][orderable]", col["orderable"]),
                (f"columns[{i}][search][value]", ""),
                (f"columns[{i}][search][regex]", "false"),
            ]

        # Thêm user IDs
        for uid in uid_list:
            if uid:
                params.append(("uIds[]", uid))

        return params

    def _parse_api_response(self, data: dict, target_date: date) -> Dict[str, Any]:
        """Parse JSON response từ DataTables API."""
        records = data.get("data", [])
        logger.info(f"[Logwork] Received {len(records)} records from API")

        # Group by logByUserId → tổng spentTime
        uid_hours: Dict[str, float] = {}
        uid_name: Dict[str, str] = {}

        for record in records:
            uid = record.get("logByUserId", "")
            hours = float(record.get("spentTime", 0) or 0)
            name = record.get("logByUser", {}).get("item1", "")

            if uid:
                uid_hours[uid] = uid_hours.get(uid, 0.0) + hours
                if uid not in uid_name:
                    uid_name[uid] = name

        logger.debug(f"[Logwork] Hours by UID: {uid_hours}")

        # Đối chiếu với team.json
        logged = []
        missing = []

        for member in self.team:
            uid = member.get("uid", "")
            name = member["name"]
            position = member.get("position", "")

            hours = uid_hours.get(uid, 0.0) if uid else 0.0
            entry = {"name": name, "position": position, "hours": round(hours, 1)}

            if hours >= self.min_hours:
                logged.append(entry)
            else:
                missing.append(entry)

        total = sum(uid_hours.values())
        logger.info(
            f"[Logwork] {len(logged)} passed, {len(missing)} missing "
            f"(threshold: {self.min_hours}h, date: {target_date})"
        )

        return {
            "logged": logged,
            "missing": missing,
            "summary": {
                "date": target_date.strftime("%Y-%m-%d"),
                "total_hours": round(total, 1),
                "logged_count": len(logged),
                "missing_count": len(missing),
                "min_hours": self.min_hours,
            },
        }

    @staticmethod
    def _get_last_workday() -> date:
        """Trả về ngày làm việc gần nhất (bỏ qua cuối tuần)."""
        yesterday = date.today() - timedelta(days=1)
        if yesterday.weekday() >= 5:
            yesterday -= timedelta(days=yesterday.weekday() - 4)
        return yesterday

    def _mock_data(self) -> Dict[str, Any]:
        logger.info("[Logwork] Using MOCK data")
        result = {"logged": [], "missing": [], "summary": {}}
        for i, m in enumerate(self.team):
            hours = 8.0 if i % 3 != 2 else 3.0
            entry = {"name": m["name"], "position": m.get("position", ""), "hours": hours}
            (result["logged"] if hours >= self.min_hours else result["missing"]).append(entry)
        result["summary"] = {
            "total_hours": sum(e["hours"] for e in result["logged"] + result["missing"]),
            "logged_count": len(result["logged"]),
            "missing_count": len(result["missing"]),
            "min_hours": self.min_hours,
        }
        return result
