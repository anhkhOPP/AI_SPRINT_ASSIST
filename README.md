# 🤖 AI Sprint Assistant

Trợ lý AI quản lý Sprint tích hợp Google Chat, tự động đọc hệ thống nội bộ `op_pm`.

---

## ✅ Tính năng

| Lịch | Kênh | Tính năng |
|------|------|-----------|
| 09:00 Thứ 2 | 💬 DM PM | Hỏi lịch Sprint Planning |
| 09:00 Thứ 5 | 💬 DM PM | Hỏi lịch Sprint Review |
| 09:10 T2-T6 | 📢 Group | Nhắc họp Daily Standup |
| 09:30 T2-T6 | 📢 Group | Báo ai chưa log đủ giờ hôm qua |
| 10:00 T2-T6 | 📢 Group | Báo ai chưa điền daily hôm nay |
| 16:00 T2-T6 | 📢 Group | Nhắc chuẩn bị Sprint Review (mốc 7/3/1/0 ngày) |
| 17:30 T2-T6 | 📢 Group | Nhắc log work cuối ngày |

---

## 🚀 Cài đặt nhanh

### Bước 1: Cài dependencies
```bash
pip install -r requirements.txt
```

### Bước 2: Cấu hình .env
```bash
cp .env.example .env
```

Điền các thông tin sau vào `.env`:

```env
# Webhook group nhóm (BẮT BUỘC)
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/...

# Webhook Space riêng của PM (để nhận DM từ bot)
GOOGLE_CHAT_PM_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/...

# Tài khoản đăng nhập op_pm
INTERNAL_USERNAME=your_username
INTERNAL_PASSWORD=your_password

# URL Worklog với filter Yesterday (cố định)
INTERNAL_WORKLOG_URL=https://10.36.36.63:8618/op_pm/Worklog?fav=28728b78-...

# URL trang Scrum Meeting Notes (chứa Daily Meeting)
INTERNAL_DAILY_PARENT_URL=https://10.36.36.63:8618/op_pm/HtmlDocument/Detail/578820bf-...

# Thông tin sprint
CURRENT_SPRINT_NAME=Sprint 19
CURRENT_SPRINT_START=2026-05-13
```

### Bước 3: Cấu hình team.json
Chỉnh sửa file `team.json` với danh sách thực tế:
```json
[
  { "name": "Nguyễn Văn A", "email": "a@company.com", "position": "Developer" },
  { "name": "Trần Thị B",   "email": "b@company.com", "position": "QA" },
  { "name": "Lê Văn C",     "email": "c@company.com", "position": "Tech Lead" }
]
```

### Bước 4: Tạo Google Chat Space riêng cho PM

1. Mở Google Chat → click **"+"** cạnh Spaces → **Create Space**
2. Đặt tên: `🤖 Sprint Bot - PM`
3. Chỉ thêm mình bạn
4. Vào Space → **Apps & Integrations** → **Add webhooks** → Copy URL
5. Dán vào `GOOGLE_CHAT_PM_WEBHOOK_URL` trong `.env`

### Bước 5: Chạy
```bash
python main.py
```

---

## 🧪 Test từng tính năng

```bash
# Nhắc họp daily
python main.py --test daily_meeting

# Check log work (gửi vào group)
python main.py --test check_logwork

# Check daily standup (gửi vào group)
python main.py --test check_daily

# Hỏi PM lịch Sprint Review (gửi DM)
python main.py --test ask_review

# Hỏi PM lịch Sprint Planning (gửi DM)
python main.py --test ask_planning

# Nhắc chuẩn bị Sprint Review
python main.py --test review_prep

# Xem trạng thái sprint
python main.py --status
```

---

## 💬 Lệnh PM dùng để phản hồi bot

Khi bot hỏi lịch qua DM, PM reply trong Space riêng:

```
/set_review 26/05 14:00 https://meet.google.com/xxx
→ Bot lưu lịch, xác nhận với PM, thông báo vào group

/set_planning 27/05 09:00 https://meet.google.com/yyy
→ Bot lưu lịch, xác nhận với PM, thông báo vào group

/sprint
→ Xem thông tin sprint hiện tại

/help
→ Xem danh sách lệnh
```

---

## ⚙️ Cách scraper hoạt động

### Logwork (09:30)
```
GET https://10.36.36.63:8618/op_pm/Worklog?fav=...
  (URL đã có filter "Yesterday" sẵn)
→ Parse bảng: Task | User | Date | Activity | Time Spent
→ Group by User → cộng tổng giờ
→ Ai tổng < 7.5h hoặc không có = thiếu
→ Gửi báo cáo vào group
```

### Daily Standup (10:00)
```
GET trang Scrum Meeting Notes (URL cố định)
→ Parse sidebar → tìm link "Daily Meeting X - DD-MMM-YYYY" hôm nay
→ GET document đó
→ Parse bảng: Member | Hôm qua | Hôm nay | Blockers
→ Ai cột "Hôm qua" và "Hôm nay" đều trống = chưa điền
→ Gửi báo cáo vào group
```

### Login tự động
```
POST /op_pm/login { username, password }
→ Lưu session cookie
→ Khi session hết hạn (bị redirect về login) → tự đăng nhập lại
→ Không cần bạn can thiệp
```

---

## 🐳 Docker

```bash
cd docker
docker-compose up -d

# Xem logs
docker-compose logs -f
```

---

## 📁 Cấu trúc

```
├── main.py                    # Entry point
├── .env.example               # Template cấu hình
├── team.json                  # Danh sách thành viên + position
├── config/config.py           # Đọc và quản lý config
├── src/
│   ├── bot/
│   │   ├── google_chat.py     # Gửi tin nhắn (group + DM PM)
│   │   └── webhook_server.py  # Flask server nhận lệnh từ PM
│   ├── scrapers/
│   │   ├── base_scraper.py    # Login tự động + HTTP session
│   │   ├── logwork_scraper.py # Đọc bảng Time Spent
│   │   └── daily_scraper.py   # Tìm và đọc document Daily Meeting
│   ├── scheduler/tasks.py     # Tất cả scheduled tasks
│   ├── sprint/manager.py      # Quản lý sprint, lịch sự kiện
│   └── reminders/messages.py  # Template tất cả tin nhắn
└── tests/                     # Unit tests
```
