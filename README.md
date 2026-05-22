# 🤖 AI Sprint Assistant

> Trợ lý AI quản lý Sprint thông minh cho nhóm phát triển phần mềm, tích hợp Google Chat.

---

## 📋 Tính năng

### Tính năng yêu cầu

| # | Tính năng | Lịch | Chi tiết |
|---|-----------|------|---------|
| 1 | ⏰ **Nhắc họp Daily** | 09:10 T2-T6 | Gửi vào nhóm Google Chat, kèm agenda standup |
| 2 | 📝 **Nhắc Log Work** | 17:30 T2-T6 | Nhắc cuối ngày với checklist log work |
| 3 | 🔍 **Check Log Work hôm qua** | 09:30 T2-T6 | Đọc trang nội bộ, nêu tên người chưa log work |
| 4 | 📊 **Check Daily Standup** | 10:00 T2-T6 | Đọc trang nội bộ, nêu tên người chưa điền daily |
| 5 | ❓ **Hỏi lịch Sprint Review** | 09:00 Thứ 5 | Hỏi PM về ngày/giờ sprint review |
| 6 | ❓ **Hỏi lịch Sprint Planning** | 09:00 Thứ 2 | Hỏi PM về ngày/giờ sprint planning tuần tới |
| 7 | 🚀 **Nhắc chuẩn bị Sprint Review** | 16:00 hàng ngày | Nhắc ở mốc 7 ngày, 3 ngày, 1 ngày, ngày họp |

### Tính năng bổ sung (gợi ý & đã implement)

| # | Tính năng | Lịch | Mô tả |
|---|-----------|------|-------|
| 8 | 🌅 **Morning Digest** | 08:00 T2-T6 | Tóm tắt sprint status đầu ngày |
| 9 | 📊 **Weekly Summary** | 08:30 Thứ 6 | Tổng kết tuần, velocity, top contributors |
| 10 | 🚨 **Deadline Warning** | 15:00 T4-T5 | Cảnh báo nguy cơ trễ sprint khi velocity thấp |
| 11 | 🤖 **Interactive Bot** | On-demand | Nhận lệnh từ nhóm qua webhook |
| 12 | 📈 **Sprint Metrics** | Theo dõi | Velocity, completion rate, sprint history |

### Lệnh bot hỗ trợ (gõ trong Google Chat)

```
/help           - Xem danh sách lệnh
/sprint         - Thông tin sprint hiện tại
/status         - Trạng thái hôm nay
/members        - Danh sách thành viên
/today          - Tóm tắt lịch hôm nay
/set_review  YYYY-MM-DD HH:MM  - Đặt lịch Sprint Review
/set_planning YYYY-MM-DD HH:MM - Đặt lịch Sprint Planning
```

---

## 🏗️ Kiến trúc

```
ai-sprint-assistant/
├── main.py                    # Entry point
├── requirements.txt
├── .env.example               # Template cấu hình
│
├── config/
│   └── config.py              # Cấu hình tập trung (đọc từ .env)
│
├── src/
│   ├── bot/
│   │   ├── google_chat.py     # Google Chat API (webhook sender)
│   │   └── webhook_server.py  # Flask server nhận tin nhắn từ bot
│   │
│   ├── scrapers/
│   │   ├── base_scraper.py    # Base class với auth support
│   │   ├── logwork_scraper.py # Scrape trang log work nội bộ
│   │   └── daily_scraper.py   # Scrape trang daily standup
│   │
│   ├── scheduler/
│   │   └── tasks.py           # APScheduler - tất cả scheduled tasks
│   │
│   ├── sprint/
│   │   └── manager.py         # Quản lý sprint lifecycle, events, metrics
│   │
│   └── reminders/
│       └── messages.py        # Template tất cả tin nhắn
│
├── tests/                     # Unit tests
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── data/                      # Runtime data (sprint JSON files)
```

---

## 🚀 Cài đặt & Chạy

### Yêu cầu
- Python 3.10+
- Quyền tạo Webhook trong Google Chat Space
- Truy cập mạng nội bộ (VPN nếu cần)

### Bước 1: Clone & Cài dependencies

```bash
git clone <repo-url>
cd ai-sprint-assistant
pip install -r requirements.txt
```

### Bước 2: Cấu hình .env

```bash
cp .env.example .env
# Chỉnh sửa .env với thông tin thực tế
```

**Các biến quan trọng nhất:**

```env
# 1. Webhook Google Chat (BẮT BUỘC)
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/XXXX/messages?key=...

# 2. URL trang nội bộ
INTERNAL_LOGWORK_URL=https://your-site.company.com/logwork
INTERNAL_DAILY_URL=https://your-site.company.com/daily

# 3. Xác thực trang nội bộ
INTERNAL_AUTH_TYPE=session_cookie   # hoặc basic_auth, oauth2
INTERNAL_SESSION_COOKIE=your_cookie_value

# 4. Danh sách thành viên
TEAM_MEMBERS=Nguyen Van A:a@company.com;Tran Thi B:b@company.com

# 5. Thông tin sprint
CURRENT_SPRINT_NAME=Sprint 15
CURRENT_SPRINT_START=2024-01-15
```

### Bước 3: Lấy Webhook URL Google Chat

1. Mở **Google Chat** → vào **Space/Room** của nhóm
2. Click vào tên Space → **Manage webhooks**
3. Click **Add webhook** → đặt tên → Copy URL
4. Dán URL vào `GOOGLE_CHAT_WEBHOOK_URL` trong `.env`

### Bước 4: Chạy

```bash
# Chạy đầy đủ (scheduler + webhook server)
python main.py

# Chỉ scheduler (không cần public URL)
python main.py --scheduler-only

# Xem trạng thái sprint
python main.py --status
```

---

## 🐳 Chạy với Docker

```bash
# Build và chạy
cd docker
docker-compose up -d

# Xem logs
docker-compose logs -f

# Dừng
docker-compose down
```

---

## 🧪 Test

```bash
# Chạy tất cả tests
pytest tests/ -v

# Test một task cụ thể (gửi tin nhắn thực vào Google Chat)
python main.py --test daily_meeting      # Nhắc họp daily
python main.py --test logwork_reminder   # Nhắc log work
python main.py --test check_logwork      # Check log work hôm qua
python main.py --test check_daily        # Check daily standup
python main.py --test ask_review         # Hỏi lịch sprint review
python main.py --test ask_planning       # Hỏi lịch sprint planning
python main.py --test review_prep        # Nhắc chuẩn bị review
python main.py --test weekly_summary     # Tổng kết tuần
python main.py --test morning_digest     # Morning digest
```

---

## ⚙️ Cấu hình Scraper trang nội bộ

Trang web nội bộ **KHÔNG public** ra ngoài - bot chỉ chạy trong mạng nội bộ hoặc VPN.

### Phương thức xác thực

#### Option 1: Session Cookie (Khuyến nghị)
Dùng khi trang dùng session-based auth (phổ biến nhất).

```env
INTERNAL_AUTH_TYPE=session_cookie
INTERNAL_COOKIE_NAME=JSESSIONID    # Hoặc tên cookie khác
INTERNAL_SESSION_COOKIE=abc123...  # Lấy từ DevTools > Application > Cookies
```

> **Cách lấy cookie:** Mở Chrome DevTools (F12) → Application → Cookies → Copy value

#### Option 2: Basic Auth
```env
INTERNAL_AUTH_TYPE=basic_auth
INTERNAL_USERNAME=your_username
INTERNAL_PASSWORD=your_password
```

#### Option 3: OAuth2 Bearer Token
```env
INTERNAL_AUTH_TYPE=oauth2
INTERNAL_OAUTH_TOKEN=eyJhbGc...
```

### Tùy chỉnh parser

Nếu trang nội bộ có cấu trúc đặc biệt, chỉnh sửa các hàm trong:
- `src/scrapers/logwork_scraper.py` → `_parse_logwork_table()`
- `src/scrapers/daily_scraper.py` → `_parse_daily_table()`

Hỗ trợ format: `html_table` | `json_api` | `jira` | `confluence` | `google_forms`

```env
INTERNAL_LOGWORK_FORMAT=json_api   # Nếu trang có JSON API
INTERNAL_DAILY_FORMAT=confluence   # Nếu dùng Confluence
```

---

## 📅 Tuỳ chỉnh lịch

Thay đổi giờ trong `.env`:

```env
DAILY_MEETING_TIME=09:10      # Giờ nhắc họp daily
LOGWORK_REMINDER_TIME=17:30   # Giờ nhắc log work
LOGWORK_CHECK_TIME=09:30      # Giờ check log work hôm qua
DAILY_CHECK_TIME=10:00        # Giờ check daily standup
```

---

## 💡 Gợi ý tính năng thêm

Dưới đây là các tính năng có thể phát triển thêm:

### Quản lý Sprint
- 📋 **Backlog reminder** - Nhắc PM chuẩn bị backlog trước Sprint Planning 2 ngày
- 🔄 **Auto advance sprint** - Tự động tạo sprint mới khi sprint hiện tại kết thúc
- 📊 **Burndown chart** - Tạo và gửi burndown chart hàng ngày
- 🏆 **Sprint retrospective reminder** - Nhắc chuẩn bị retrospective

### Theo dõi cá nhân
- 👤 **Personal task reminder** - Nhắc riêng từng người về task sắp deadline
- 📱 **DM người chưa log work** - Nhắn tin riêng (không chỉ nhóm)
- 🎯 **OKR tracking** - Theo dõi tiến độ OKR theo sprint

### Tích hợp công cụ
- 📎 **Jira integration** - Sync data từ Jira tự động
- 📊 **Google Sheets report** - Export báo cáo ra Google Sheets tuần/tháng
- 📧 **Email digest** - Gửi email tóm tắt cho manager
- 🔗 **Slack integration** - Hỗ trợ Slack ngoài Google Chat
- 📅 **Google Calendar** - Tự động tạo event trên Google Calendar

### AI & Analytics
- 🧠 **Sentiment analysis** - Phân tích mood team qua daily notes
- 📈 **Velocity prediction** - Dự đoán velocity sprint dựa trên lịch sử
- ⚠️ **Risk detection** - Tự động phát hiện task có nguy cơ trễ
- 💬 **Natural language** - Hỗ trợ lệnh bằng tiếng Việt tự nhiên

### Chất lượng & Quy trình
- ✅ **Code review reminder** - Nhắc review PR đang pending
- 🧪 **Test coverage alert** - Cảnh báo khi test coverage giảm
- 📝 **Meeting notes** - Tự động tạo template meeting notes
- 🔒 **On-call reminder** - Nhắc lịch on-call duty

---

## 🔒 Bảo mật

- File `.env` chứa credentials - **KHÔNG commit lên Git** (đã có trong `.gitignore`)
- Cookie session có thể hết hạn - cần cập nhật định kỳ
- Nên chạy bot trên server nội bộ hoặc VPN để bảo vệ credentials
- Sử dụng Docker secrets hoặc HashiCorp Vault trong production

---

## 📝 Giấy phép

MIT License - Sử dụng tự do cho dự án nội bộ.
