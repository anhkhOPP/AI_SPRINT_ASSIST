#!/bin/bash
# Gỡ cài đặt AI Sprint Assistant Services

echo "🗑️  Gỡ cài đặt AI Sprint Assistant Services..."

systemctl stop sprint-bot sprint-webhook sprint-tunnel 2>/dev/null
systemctl disable sprint-bot sprint-webhook sprint-tunnel 2>/dev/null
rm -f /etc/systemd/system/sprint-bot.service
rm -f /etc/systemd/system/sprint-webhook.service
rm -f /etc/systemd/system/sprint-tunnel.service
rm -f /etc/rsyslog.d/sprint-bot.conf
rm -f /etc/logrotate.d/sprint-bot
systemctl daemon-reload

echo "✅ Đã gỡ cài đặt xong!"
