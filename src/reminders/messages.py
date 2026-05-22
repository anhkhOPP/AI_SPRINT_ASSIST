"""
Template tất cả tin nhắn gửi qua Google Chat.
"""
from datetime import datetime, date
from typing import List, Dict, Optional

import pytz

from config import get_config


def _now_vn() -> datetime:
    tz = pytz.timezone(get_config().schedule.timezone)
    return datetime.now(tz)


def _format_missing_list(members: List[Dict]) -> str:
    """Format danh sách thành viên thiếu kèm position."""
    lines = []
    for m in members:
        name = m.get("name", "")
        pos = m.get("position", "")
        hours = m.get("hours")
        line = f"  • {name}"
        if pos:
            line += f" _({pos})_"
        if hours is not None:
            line += f" - đã log *{hours}h*"
        lines.append(line)
    return "\n".join(lines)


class MessageTemplates:

    # ================================================================
    # 1. NHẮC HỌP DAILY (09:10)
    # ================================================================

    @staticmethod
    def daily_meeting_reminder() -> str:
        now = _now_vn()
        days_vn = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
        weekday = days_vn[now.weekday()]
        date_str = now.strftime("%d/%m/%Y")

        return (
            f"🕘 *DAILY STANDUP - {weekday} {date_str}*\n\n"
            "Đến giờ họp daily rồi! Mọi người vào meeting nhé 🚀\n\n"
            "📋 *Nội dung standup:*\n"
            "• Hôm qua tôi đã làm gì?\n"
            "• Hôm nay tôi sẽ làm gì?\n"
            "• Có blockers gì không?\n\n"
            "_Tối đa 15 phút_ ⏱️"
        )

    # ================================================================
    # 2. NHẮC LOG WORK (17:30)
    # ================================================================

    @staticmethod
    def logwork_reminder(min_hours: float = 7.5) -> str:
        now = _now_vn()
        date_str = now.strftime("%d/%m/%Y")

        return (
            f"📝 *NHẮC LOG WORK - {date_str}*\n\n"
            f"Cuối ngày rồi! Đừng quên log work nhé mọi người 💪\n\n"
            f"✅ *Checklist:*\n"
            f"• Log đủ *{min_hours}h* cho hôm nay\n"
            f"• Điền work notes mô tả đã làm gì\n"
            f"• Cập nhật trạng thái task\n"
            f"• Điền daily nếu chưa điền\n\n"
            f"_Hạn chót trước 18:00_ ⏰"
        )

    # ================================================================
    # 3. BÁO AI CHƯA LOG WORK (09:30)
    # ================================================================

    @staticmethod
    def missing_logwork_report(
        missing: List[Dict],
        min_hours: float = 7.5,
        check_date: Optional[date] = None,
    ) -> str:
        if check_date is None:
            check_date = _now_vn().date()
        date_str = check_date.strftime("%d/%m/%Y")

        if not missing:
            return (
                f"✅ *LOG WORK - {date_str}*\n\n"
                f"Tất cả thành viên đã log đủ *{min_hours}h* hôm qua! 🎉\n"
                "Cảm ơn mọi người đã nghiêm túc! 👏"
            )

        count = len(missing)
        member_list = _format_missing_list(missing)

        return (
            f"⚠️ *LOG WORK CHƯA ĐỦ - {date_str}*\n\n"
            f"*{count} người* chưa log đủ *{min_hours}h* hôm qua:\n\n"
            f"{member_list}\n\n"
            f"Vui lòng bổ sung log work nhé! 🙏"
        )

    # ================================================================
    # 4. BÁO AI CHƯA ĐIỀN DAILY (10:00)
    # ================================================================

    @staticmethod
    def missing_daily_report(missing: List[Dict]) -> str:
        now = _now_vn()
        date_str = now.strftime("%d/%m/%Y")

        if not missing:
            return (
                f"✅ *DAILY STANDUP - {date_str}*\n\n"
                "Mọi người đã điền daily đầy đủ! 🎉\n"
                "Sẵn sàng cho buổi họp! 🚀"
            )

        count = len(missing)
        member_list = _format_missing_list(missing)

        return (
            f"⚠️ *CHƯA ĐIỀN DAILY - {date_str}*\n\n"
            f"*{count} người* chưa điền daily hôm nay:\n\n"
            f"{member_list}\n\n"
            "Điền trước khi họp nhé! ⏰"
        )

    # ================================================================
    # 5. HỎI PM LỊCH SPRINT REVIEW (Thứ 5 - gửi DM)
    # ================================================================

    @staticmethod
    def ask_pm_sprint_review(sprint_name: str) -> str:
        now = _now_vn()
        date_str = now.strftime("%d/%m/%Y")

        return (
            f"📅 *HỎI LỊCH SPRINT REVIEW - {sprint_name}*\n\n"
            f"Hôm nay {date_str} (Thứ 5) - sắp đến sprint review rồi!\n\n"
            "❓ *Sprint Review lần này:*\n"
            "• Họp ngày nào?\n"
            "• Mấy giờ bắt đầu?\n"
            "• Link meeting?\n\n"
            "Reply theo format:\n"
            "`/set_review DD/MM HH:MM [link]`\n\n"
            "_Ví dụ: `/set_review 26/05 14:00 https://meet.google.com/xxx`_"
        )

    # ================================================================
    # 6. HỎI PM LỊCH SPRINT PLANNING (Thứ 2 - gửi DM)
    # ================================================================

    @staticmethod
    def ask_pm_sprint_planning(sprint_name: str, next_sprint_name: str) -> str:
        now = _now_vn()
        date_str = now.strftime("%d/%m/%Y")

        return (
            f"📅 *HỎI LỊCH SPRINT PLANNING - {next_sprint_name}*\n\n"
            f"Hôm nay {date_str} (Thứ 2) - tuần mới bắt đầu!\n\n"
            "❓ *Sprint Planning lần này:*\n"
            "• Họp ngày nào?\n"
            "• Mấy giờ bắt đầu?\n"
            "• Backlog đã sẵn sàng chưa?\n\n"
            "Reply theo format:\n"
            "`/set_planning DD/MM HH:MM [link]`\n\n"
            "_Ví dụ: `/set_planning 27/05 09:00 https://meet.google.com/xxx`_"
        )

    # ================================================================
    # 7. NHẮC CHUẨN BỊ SPRINT REVIEW (gửi group)
    # ================================================================

    @staticmethod
    def sprint_review_prep(
        sprint_name: str, review_date: str, days_until: int, meeting_link: str = ""
    ) -> str:
        if days_until == 0:
            urgency = "🔴 *HÔM NAY* là ngày Sprint Review!"
        elif days_until == 1:
            urgency = "🟡 *NGÀY MAI* là Sprint Review!"
        elif days_until <= 3:
            urgency = f"🟠 Còn *{days_until} ngày* nữa là Sprint Review!"
        else:
            urgency = f"🟢 Còn *{days_until} ngày* nữa là Sprint Review."

        link_line = f"\n🔗 Link meeting: {meeting_link}" if meeting_link else ""

        return (
            f"🚀 *CHUẨN BỊ SPRINT REVIEW - {sprint_name}*\n\n"
            f"{urgency}\n"
            f"📅 Ngày họp: *{review_date}*{link_line}\n\n"
            "✅ *Checklist chuẩn bị:*\n"
            "• [ ] Demo các feature đã hoàn thành\n"
            "• [ ] Chuẩn bị slide/báo cáo kết quả\n"
            "• [ ] Cập nhật trạng thái tất cả tasks\n"
            "• [ ] Thu thập metrics (velocity, burndown)\n"
            "• [ ] Liệt kê done / not done\n"
            "• [ ] Test lại lần cuối trước demo\n\n"
            "_Chuẩn bị kỹ = Sprint Review thành công!_ 🎯"
        )

    # ================================================================
    # XÁC NHẬN LỊch VỚI PM (gửi DM sau khi PM set lịch)
    # ================================================================

    @staticmethod
    def confirm_sprint_event(
        event_type: str, event_date: str, event_time: str, meeting_link: str = ""
    ) -> str:
        type_label = "Sprint Review" if event_type == "review" else "Sprint Planning"
        link_line = f"\n🔗 Link: {meeting_link}" if meeting_link else ""

        return (
            f"✅ *Đã lưu lịch {type_label}!*\n\n"
            f"📅 Ngày: *{event_date}*\n"
            f"🕑 Giờ: *{event_time}*{link_line}\n\n"
            "Bot sẽ nhắc nhóm chuẩn bị đúng hạn 🔔"
        )

    # ================================================================
    # THÔNG BÁO LỊCH VÀO GROUP (sau khi PM xác nhận)
    # ================================================================

    @staticmethod
    def announce_sprint_event(
        sprint_name: str, event_type: str, event_date: str,
        event_time: str, meeting_link: str = ""
    ) -> str:
        type_label = "Sprint Review" if event_type == "review" else "Sprint Planning"
        emoji = "🎯" if event_type == "review" else "📋"
        link_line = f"\n🔗 Link meeting: {meeting_link}" if meeting_link else ""

        return (
            f"{emoji} *LỊCH {type_label.upper()} - {sprint_name}*\n\n"
            f"📅 Ngày: *{event_date}*\n"
            f"🕑 Giờ: *{event_time}*{link_line}\n\n"
            "Mọi người note lịch vào calendar nhé! 📆"
        )
