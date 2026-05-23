#!/bin/bash
# ============================================================
# Cài đặt AI Sprint Assistant như Linux Services
# Chạy: sudo bash /opt/AI_SPRINT_ASSIST/systemd/install.sh
# ============================================================

set -e

APP_DIR="/opt/AI_SPRINT_ASSIST"
LOG_DIR="/var/log/sprint-bot"
SYSTEMD_DIR="/etc/systemd/system"

echo "🤖 Cài đặt AI Sprint Assistant Services..."
echo "============================================"

# Kiểm tra chạy với quyền root
if [ "$(id -u)" != "0" ]; then
    echo "❌ Cần chạy với quyền root: sudo bash install.sh"
    exit 1
fi

# Tạo thư mục log
echo "📁 Tạo thư mục log: $LOG_DIR"
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Copy service files
echo "📋 Copy service files..."
cp "$APP_DIR/systemd/sprint-bot.service"     "$SYSTEMD_DIR/"
cp "$APP_DIR/systemd/sprint-webhook.service" "$SYSTEMD_DIR/"
cp "$APP_DIR/systemd/sprint-tunnel.service"  "$SYSTEMD_DIR/"

# Cài rsyslog config
echo "📋 Cài rsyslog config..."
cp "$APP_DIR/systemd/sprint-bot-log.conf" /etc/rsyslog.d/sprint-bot.conf
systemctl restart rsyslog 2>/dev/null || true

# Cài logrotate config
echo "📋 Cài logrotate config..."
cp "$APP_DIR/systemd/sprint-bot-logrotate.conf" /etc/logrotate.d/sprint-bot

# Reload systemd
echo "🔄 Reload systemd..."
systemctl daemon-reload

# Enable services (tự khởi động khi reboot)
echo "✅ Enable services..."
systemctl enable sprint-bot.service
systemctl enable sprint-webhook.service
systemctl enable sprint-tunnel.service

# Start services
echo "🚀 Khởi động services..."
systemctl start sprint-bot.service
sleep 2
systemctl start sprint-webhook.service
sleep 2
systemctl start sprint-tunnel.service

echo ""
echo "============================================"
echo "✅ Cài đặt hoàn tất!"
echo ""
echo "📊 Kiểm tra trạng thái:"
echo "  systemctl status sprint-bot"
echo "  systemctl status sprint-webhook"
echo "  systemctl status sprint-tunnel"
echo ""
echo "📋 Xem log:"
echo "  journalctl -u sprint-bot -f"
echo "  journalctl -u sprint-webhook -f"
echo "  tail -f /var/log/sprint-bot/app.log"
echo "  tail -f /var/log/sprint-bot/webhook.log"
echo "  tail -f /var/log/sprint-bot/tunnel.log"
echo ""
echo "🔧 Lệnh quản lý:"
echo "  systemctl restart sprint-bot      # Restart bot"
echo "  systemctl restart sprint-webhook  # Restart webhook"
echo "  systemctl stop sprint-tunnel      # Dừng tunnel"
echo "============================================"
