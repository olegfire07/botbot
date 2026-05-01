#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

SSH_PORT="${SSH_PORT:-22}"

apt-get update
apt-get install -y ufw fail2ban

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow "$SSH_PORT"/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat >/etc/fail2ban/jail.d/sklad-sshd.conf <<EOF
[sshd]
enabled = true
port = $SSH_PORT
filter = sshd
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF

systemctl enable --now fail2ban
systemctl restart fail2ban

ufw status verbose
for _ in 1 2 3 4 5; do
  if fail2ban-client status sshd; then
    exit 0
  fi
  sleep 1
done

fail2ban-client status
echo "fail2ban is running, but sshd jail did not become ready in time." >&2
exit 1
