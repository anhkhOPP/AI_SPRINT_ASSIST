"""
Các template tin nhắn cho AI Sprint Assistant.
Tất cả nội dung nhắn tin được quản lý tập trung tại đây.
"""
from datetime import datetime, date
from typing import List, Optional

import pytz

from config import get_config


def _now_vn() -> datetime:
    tz = pytz.timezone(get_config().schedule.timezone)
    return datetime.now(tz)


class MessageTemplates:
    """Tập hợp tất cả template tin nhắn."""

    # ================================================================
    # DAILY MEETING REMINDER (9:10)
    # ================================================================

    @staticmethod
    def daily_meeting_reminder() -> str:
        now = _now_vn()
        weekday_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
        weekday = weekday_names[now.weekday()]
        date_str = now.strftime("%d/%m/%Y")

        return (
            f"🕘 *DAILY STANDUP - {weekday} {date_str}*\n\n"
            "Đã đến giờ họp daily! Mọi người vào meeting nhé 🚀\n\n"
            "📋 *Agenda:*\n"
            "• Hôm qua tôi đã làm gì?\n"
            "• Hôm nay tôi sẽ làm gì?\n"
            "• Có vấn đề/blockers gì không?\n\n"
            "_Họp ngắn gọn, tối đa 15 phút_ ⏱️"
        )

    # ================================================================
    # LOG WORK REMINDER (17:30)
    # ================================================================

    @staticmethod
    def logwork_reminder() -> str:
        now = _now_vn()
        date_str = now.strftime("%d/%m/%Y")

        return (
            f"📝 *NHẮC LOG WORK - {date_str}*\n\n"
            "Cuối ngày rồi! Đừng quên log work hôm nay nhé mọi người! 💪\n\n"
            "✅ *Checklist log work:*\n"
            "• Điền đủ số giờ cho từng task\n"
            "• Cập nhật trạng thái task (In Progress / Done)\n"
            "• Ghi chú nếu có blockers\n"
            "• Điền daily report nếu chưa điền\n\n"
            "🔗 Log work tại: hệ thống nội bộ\n\n"
            "_Hạn chót: *18:00* hôm nay_ ⏰"
        )

    # ================================================================
    # MISSING LOG WORK (9:30 - kiểm tra hôm qua)
    # ================================================================

    @staticmethod
    def missing_logwork_report(missing_users: List[str], check_date: Optional[date] = None) -> str:
        if check_date is None:
            check_date = _now_vn().date()

        date_str = check_date.strftime("%d/%m/%Y")

        if not missing_users:
            return (
                f"✅ *LOG WORK - {date_str}*\n\n"
                "Tuyệt vời! Tất cả thành viên đã log work đầy đủ! 🎉\n"
                "Cảm ơn mọi người đã nghiêm túc! 👏"
            )

        user_list = "\n".join(f"  • {u}" for u in missing_users)
        count = len(missing_users)

        return (
            f"⚠️ *LOG WORK CHƯA HOÀN THÀNH - {date_str}*\n\n"
            f"Có *{count} người* chưa log work hôm qua:\n\n"
            f"{user_list}\n\n"
            "Vui lòng log work *ngay hôm nay trước 9:30* nhé!\n"
            "_Bot sẽ kiểm tra lại sau._ 🔍"
        )

    # ================================================================
    # MISSING DAILY STANDUP (10:00 - kiểm tra hôm nay)
    # ================================================================

    @staticmethod
    def missing_daily_report(missing_users: List[str]) -> str:
        now = _now_vn()
        date_str = now.strftime("%d/%m/%Y")

        if not missing_users:
            return (
                f"✅ *DAILY STANDUP - {date_str}*\n\n"
                "Mọi người đã điền daily đầy đủ! 🎉\n"
                "Sẵn sàng cho buổi họp! 🚀"
            )

        user_list = "\n".join(f"  • {u}" for u in missing_users)
        count = len(missing_users)

        return (
            f"⚠️ *CHƯA ĐIỀN DAILY - {date_str}*\n\n"
            f"Có *{count} người* chưa điền daily hôm nay:\n\n"
            f"{user_list}\n\n"
            "⏰ Vui lòng điền *trước 10:00* để chuẩn bị cho buổi họp daily nhé!\n"
            "_Không có daily = không biết bạn đang làm gì_ 😅"
        )

    # ================================================================
    # SPRINT REVIEW ASK (Thứ 5)
    # ================================================================

    @staticmethod
    def sprint_review_ask(sprint_name: str = "") -> str:
        sprint_info = f" cho *{sprint_name}*" if sprint_name else ""

        return (
            f"📅 *LỊCH SPRINT REVIEW{sprint_info.upper()}*\n\n"
            "Hôm nay là thứ 5, sắp đến sprint review rồi! 🎯\n\n"
            "❓ *PM/Leader ơi, sprint review lần này:*\n"
            "• Sẽ họp vào ngày nào?\n"
            "• Mấy giờ bắt đầu?\n"
            "• Link meeting là gì?\n\n"
            "Vui lòng trả lời để bot nhắc cả nhóm chuẩn bị nhé!\n\n"
            "_(Hoặc dùng lệnh: `/set_review YYYY-MM-DD HH:MM`)_"
        )

    # ================================================================
    # SPRINT PLANNING ASK (Thứ 2)
    # ================================================================

    @staticmethod
    def sprint_planning_ask(next_sprint_name: str = "") -> str:
        next_sprint = f" *{next_sprint_name}*" if next_sprint_name else ""

        return (
            f"📅 *LỊCH SPRINT PLANNING{next_sprint.upper()}*\n\n"
            "Hôm nay là thứ 2, tuần mới bắt đầu! 💪\n\n"
            "❓ *PM/Leader ơi, sprint planning lần này:*\n"
            "• Sẽ họp vào ngày nào?\n"
            "• Mấy giờ bắt đầu?\n"
            "• Backlog đã sẵn sàng chưa?\n\n"
            "Vui lòng trả lời để bot thông báo cả nhóm nhé!\n\n"
            "_(Hoặc dùng lệnh: `/set_planning YYYY-MM-DD HH:MM`)_"
        )

    # ================================================================
    # SPRINT REVIEW PREPARATION (trước ngày họp)
    # ================================================================

    @staticmethod
    def sprint_review_prep(sprint_name: str, review_date: str, days_until: int) -> str:
        urgency = ""
        if days_until == 0:
            urgency = "🔴 *HÔM NAY* là ngày Sprint Review!"
        elif days_until == 1:
            urgency = "🟡 *NGÀY MAI* là Sprint Review!"
        elif days_until <= 3:
            urgency = f"🟠 Còn *{days_until} ngày* nữa là Sprint Review!"
        else:
            urgency = f"🟢 Còn *{days_until} ngày* nữa là Sprint Review."

        return (
            f"🚀 *CHUẨN BỊ SPRINT REVIEW - {sprint_name}*\n\n"
            f"{urgency}\n"
            f"📅 Ngày họp: *{review_date}*\n\n"
            "✅ *Checklist chuẩn bị:*\n"
            "• [ ] Demo các feature đã hoàn thành\n"
            "• [ ] Chuẩn bị slide/báo cáo kết quả sprint\n"
            "• [ ] Thu thập metrics (velocity, burndown)\n"
            "• [ ] Liệt kê những gì done / not done\n"
            "• [ ] Chuẩn bị câu hỏi cho stakeholders\n"
            "• [ ] Test lại lần cuối trước khi demo\n"
            "• [ ] Cập nhật trạng thái tất cả tasks\n\n"
            "_Chuẩn bị kỹ = Sprint Review thành công!_ 🎯"
        )

    # ================================================================
    # SPRINT VELOCITY REPORT (cuối sprint)
    # ================================================================

    @staticmethod
    def sprint_velocity_report(
        sprint_name: str,
        planned_points: int,
        completed_points: int,
        completed_tasks: int,
        total_tasks: int,
    ) -> str:
        velocity_pct = (completed_points / planned_points * 100) if planned_points > 0 else 0
        task_pct = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        emoji = "🏆" if velocity_pct >= 90 else "👍" if velocity_pct >= 70 else "⚠️"

        return (
            f"{emoji} *SPRINT REPORT - {sprint_name}*\n\n"
            f"📊 *Velocity:*\n"
            f"• Story points: {completed_points}/{planned_points} ({velocity_pct:.0f}%)\n"
            f"• Tasks: {completed_tasks}/{total_tasks} ({task_pct:.0f}%)\n\n"
            f"{'🎉 Sprint thành công!' if velocity_pct >= 90 else '💪 Sprint kết thúc. Review để cải thiện!'}"
        )

    # ================================================================
    # WEEKLY SUMMARY (Thứ 6)
    # ================================================================

    @staticmethod
    def weekly_summary(
        sprint_name: str,
        days_remaining: int,
        top_contributors: List[str],
    ) -> str:
        top_list = "\n".join(f"  🥇 {u}" for u in top_contributors[:3]) if top_contributors else "  _(Chưa có dữ liệu)_"

        return (
            f"📊 *TỔNG KẾT TUẦN - {sprint_name}*\n\n"
            f"⏳ Còn *{days_remaining} ngày* trong sprint\n\n"
            f"🏆 *Top contributors tuần này:*\n{top_list}\n\n"
            "Chúc mọi người cuối tuần vui vẻ! 🎉\n"
            "_Tuần sau tiếp tục cố gắng nhé!_ 💪"
        )

    # ================================================================
    # MORNING DIGEST (Đầu ngày)
    # ================================================================

    @staticmethod
    def morning_digest(
        sprint_name: str,
        days_remaining: int,
        tasks_in_progress: int,
        tasks_done: int,
        blockers: List[str],
    ) -> str:
        blocker_section = ""
        if blockers:
            blocker_list = "\n".join(f"  ⛔ {b}" for b in blockers)
            blocker_section = f"\n\n🚨 *Blockers cần giải quyết:*\n{blocker_list}"

        return (
            f"🌅 *GOOD MORNING TEAM!*\n\n"
            f"📌 Sprint: *{sprint_name}* - Còn *{days_remaining} ngày*\n"
            f"📊 Tasks: ✅ {tasks_done} done | 🔄 {tasks_in_progress} in progress"
            f"{blocker_section}\n\n"
            "Chúc mọi người một ngày làm việc hiệu quả! 🚀"
        )

    # ================================================================
    # OVERTIME WARNING
    # ================================================================

    @staticmethod
    def overtime_warning(sprint_name: str, at_risk_tasks: List[str]) -> str:
        task_list = "\n".join(f"  ⚠️ {t}" for t in at_risk_tasks)
        return (
            f"🚨 *CẢNH BÁO NGUY CƠ TRỄ DEADLINE - {sprint_name}*\n\n"
            f"Các tasks có nguy cơ không hoàn thành đúng hạn:\n{task_list}\n\n"
            "Cần action ngay! 💬 Liên hệ PM hoặc tạo blocker ticket."
        )
