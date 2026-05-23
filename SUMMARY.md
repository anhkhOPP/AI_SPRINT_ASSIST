# AI Sprint Assistant - Project Summary

## Overview
AI-powered sprint management bot integrated with Google Chat and op_pm internal system.

---

## Architecture

```
Google Chat (Group + PM Space)
        ↑↓ incoming webhook
  [Cloudflare Tunnel]
        ↑↓
  [Flask Webhook Server :5000]  ←→  [Gemini AI / Claude AI]
        ↑
  [APScheduler]
        ↓
  [Scrapers] ──→ op_pm (https://10.36.36.63:8618/op_pm)
        ↓            ├─ Login: Identity Server (8611, OIDC)
  [Sprint Manager]   ├─ Worklog: POST /WorkLog (DataTables API)
        ↓            └─ Daily: GET /HtmlDocument/Print/... (static HTML)
  [Google Chat Bot]
```

---

## Scheduled Tasks

| Time | Days | Channel | Action |
|------|------|---------|--------|
| 09:00 | Monday | DM PM | Ask sprint planning schedule |
| 09:00 | Thursday | DM PM | Ask sprint review schedule |
| 09:10 | Mon-Fri | Group | Daily meeting reminder |
| 09:30 | Mon-Fri | Group | Check logwork yesterday |
| 10:00 | Mon-Fri | Group | Check daily standup + AI summary |
| 12:00 | Sat (wk 1,4,5) | Group | Logwork reminder (4h threshold) |
| 16:00 | Mon-Fri | Group | Sprint review prep reminder |
| 17:30 | Mon-Sat (workdays) | Group | Logwork reminder EOD |

---

## Saturday Rules

| Week of Month | Status | Logwork Threshold |
|---------------|--------|-------------------|
| Week 1, 4, 5 | Working day | 4 hours |
| Week 2, 3 | Day off | N/A |

**Monday check logic:**
- If last Saturday was working → check Saturday logwork (4h)
- If last Saturday was off → check Friday logwork (7.5h)

Config: `SATURDAY_OFF_WEEKS=2,3` | `SATURDAY_MIN_HOURS=4.0`

---

## Internal System (op_pm)

### Authentication
- Type: ASP.NET Identity Server (OIDC, port 8611)
- Flow: GET op_pm → redirect to 8611 → POST credentials → OIDC callback → signin-oidc → session cookie
- SSL: self-signed cert (verify=False)
- Auto re-login when session expires

### Logwork Scraper
- URL: `POST /op_pm/WorkLog` (DataTables format)
- Date param: `dateRange=DD/MMM/YYYY - DD/MMM/YYYY`
- User IDs: `uIds[]=UUID` (from team.json)
- Response: `data[].logByUserId + spentTime`
- Group by UUID → sum hours → compare threshold

### Daily Standup Scraper
- Step 1: GET Print URL `/op_pm/HtmlDocument/Print/{parent_id}`
  - Returns 1.6MB static HTML with ALL daily meetings
  - No JS needed (unlike Detail page)
- Step 2: Find date string `"DD-MMM-YYYY"` in HTML
- Step 3: Extract `<table` after date → parse rows
- Format: Member | Hôm qua | Hôm nay | Blockers | Adhoc
- Empty row = not filled

---

## Team Configuration (team.json)

```json
[{
  "name": "Kiều Hoàng Anh",
  "email": "...",
  "position": "Team Lead",
  "uid": "8e9af5c2-db99-4ef0-9e24-bfbaa0087f57",
  "display_name": "Hoang Anh"
}]
```

- `uid`: UUID in op_pm system (for logwork matching)
- `display_name`: name as shown in op_pm
- `name`: full Vietnamese name (shown in reports)

---

## Google Chat Integration

### Outgoing (Bot → Chat)
- `GOOGLE_CHAT_WEBHOOK_URL`: group space webhook
- `GOOGLE_CHAT_PM_WEBHOOK_URL`: PM private space webhook
- Library: requests POST to webhook URL

### Incoming (Chat → Bot)
- App type: GSuite Add-on (not pure Chat App)
- Event format: `event["chat"]["messagePayload"]["message"]["text"]`
- Response: `{}` (empty) - reply sent via outgoing webhook instead
- Tunnel: Cloudflare quick tunnel (URL changes on restart)

### PM Commands
PM types in DM with bot (natural language or commands):
```
họp sprint review ngày 26/5 lúc 2h chiều phòng A3  ← AI parses
/set_review 26/05 14:00 Phòng A3 https://meet.google.com/xxx
/set_planning 27/05 09:00 Phòng B2
/sprint
/help
```

Or via browser URL:
```
https://{tunnel-url}/set_review?date=26/05&time=14:00&room=Phong+A3
```

---

## AI Integration (Gemini + Claude)

- Primary: Gemini 2.0 Flash (free, 15 req/min)
- Fallback: Claude Haiku (paid, auto-switch on Gemini failure)

### Feature 1: Natural Language Schedule Parsing
```
Input: "họp review cuối sprint ngày 30/5, 2h chiều, phòng A3"
Output: {"date": "30/05", "time": "14:00", "room": "Phòng A3", "event_type": "review"}
```

### Feature 2: Daily Standup AI Summary
- Reads submitted daily entries
- Detects: blockers, risks, task conflicts, slow progress
- Only sends to group if something noteworthy
- Triggered after 10:00 daily check

---

## Sprint Management

### Events
PM sets schedule via DM → bot saves to `data/current_sprint.json`:
- Sprint Review: date, time, room, meeting_link
- Sprint Planning: date, time, room, meeting_link

### Sprint Review Prep Reminders
Sent at 16:00 on milestone days: 7 days, 3 days, 1 day, day-of

### Message format (Sprint Review prep):
```
@all
🚀 CHUẨN BỊ SPRINT REVIEW - Sprint 19

Mọi người review task sprint vừa rồi nhé:
1️⃣ Kiểm tra trạng thái US, bổ sung evident
2️⃣ Review lại daily, logwork
3️⃣ Chuẩn bị demo

⏰ Thời gian họp: 26/05/2026 14:00
🏠 Phòng họp: Phòng A3
```

---

## Linux Services (systemd)

```bash
# Install all services
sudo bash /opt/AI_SPRINT_ASSIST/systemd/install.sh

# Manage
systemctl status sprint-bot sprint-webhook sprint-tunnel
systemctl restart sprint-bot      # After .env changes
systemctl restart sprint-webhook   # After .env changes
systemctl restart sprint-tunnel    # After tunnel URL changes

# Logs
journalctl -u sprint-bot -f
journalctl -u sprint-webhook -f
tail -f /var/log/sprint-bot/app.log
tail -f /var/log/sprint-bot/webhook.log
tail -f /var/log/sprint-bot/tunnel.log
```

---

## Key Configuration (.env)

```env
# Google Chat
GOOGLE_CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/.../messages?key=...
GOOGLE_CHAT_PM_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/.../messages?key=...

# Internal system
INTERNAL_BASE_URL=https://10.36.36.63:8618/op_pm
INTERNAL_USERNAME=email@onepay.vn
INTERNAL_PASSWORD=...
INTERNAL_LOGIN_FIELD_USERNAME=Username
INTERNAL_LOGIN_FIELD_PASSWORD=Password
INTERNAL_WORKLOG_URL=https://10.36.36.63:8618/op_pm/Worklog?fav=28728b78-...
INTERNAL_DAILY_PARENT_URL=https://10.36.36.63:8618/op_pm/HtmlDocument/Detail/578820bf-...

# Thresholds
LOGWORK_MIN_HOURS=7.5
SATURDAY_MIN_HOURS=4.0
SATURDAY_OFF_WEEKS=2,3

# Sprint
CURRENT_SPRINT_NAME=Sprint 20
CURRENT_SPRINT_START=2026-05-25
SPRINT_DURATION_WEEKS=2

# AI
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5

# Bot server
BOT_SERVER_PORT=5000
BOT_PUBLIC_URL=https://your-tunnel.trycloudflare.com
```

---

## File Structure

```
AI_SPRINT_ASSIST/
├── main.py                     # Entry point
├── .env                        # Config (NOT in git)
├── .env.example                # Config template
├── team.json                   # Team members + UIDs
├── requirements.txt
│
├── config/config.py            # Centralized config
│
├── src/
│   ├── ai/
│   │   ├── __init__.py         # AIClient with Gemini→Claude fallback
│   │   ├── gemini.py           # Gemini API
│   │   └── claude.py           # Claude API
│   ├── bot/
│   │   ├── google_chat.py      # Send to group/PM webhook
│   │   └── webhook_server.py   # Receive from Google Chat (Flask)
│   ├── reminders/
│   │   └── messages.py         # All message templates (Vietnamese)
│   ├── scheduler/
│   │   └── tasks.py            # APScheduler jobs
│   ├── scrapers/
│   │   ├── base_scraper.py     # OIDC login + HTTP session
│   │   ├── logwork_scraper.py  # DataTables POST API
│   │   └── daily_scraper.py    # Print URL + HTML parsing
│   ├── sprint/
│   │   └── manager.py          # Sprint events, persistence
│   └── utils/
│       └── schedule_utils.py   # Saturday workday logic
│
├── tests/                      # 80 unit tests
├── systemd/                    # Linux service files
│   ├── sprint-bot.service
│   ├── sprint-webhook.service
│   ├── sprint-tunnel.service
│   ├── install.sh
│   └── uninstall.sh
└── docker/                     # Docker setup
    ├── Dockerfile
    └── docker-compose.yml
```

---

## Known Limitations & TODOs

1. **Cloudflare tunnel URL changes** on restart → must update Google Chat App URL manually.
   Solution: Set up named Cloudflare tunnel with account login.

2. **Daily scraper**: reads from Print URL which loads all meetings (slow ~1.6MB).
   Optimization: cache the HTML and only re-fetch daily.

3. **op_pm session**: expires after ~8h, auto re-login implemented.

4. **Sprint dates**: must be manually updated in `.env` at sprint start.
   TODO: auto-advance sprint from manager.

5. **Playwright**: installed but no longer needed (replaced by Print URL approach).
   Can be removed from requirements.txt.
