#!/bin/bash
# Kritik dosya izleyici + (mümkünse) auditd unlink kuralları
set -euo pipefail
ROOT=/root/aiProject

cp "$ROOT/ops/aiproject-file-watch.service" /etc/systemd/system/aiproject-file-watch.service
systemctl daemon-reload
systemctl enable --now aiproject-file-watch.service
systemctl --no-pager status aiproject-file-watch.service | head -12

mkdir -p "$ROOT/ops/incidents" /tmp/aiproject_incidents

# auditd — silen process'i (auid/pid/exe) kaydetmek için
if command -v auditctl >/dev/null 2>&1; then
  RULES=/etc/audit/rules.d/aiproject-del.rules
  cat > "$RULES" <<'EOF'
# aiProject kritik kaynak silme / yazma
-w /root/aiProject/web/poly_dashboard.py -p wa -k aiproject_del
-w /root/aiProject/PROJECT.md -p wa -k aiproject_del
-w /root/aiProject/.cursor/rules/cron-and-ops.mdc -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/virtual_book.py -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/crypto_futures_cr6.py -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/crypto_futures_trader.py -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/binance_futures_client.py -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/Algoritmalar/runner.py -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/Algoritmalar/catalog.py -p wa -k aiproject_del
-w /root/aiProject/AgustosKripto/Analizler/runner.py -p wa -k aiproject_del
-w /root/aiProject/temmuzPoly/pm_balance_guard.py -p wa -k aiproject_del
-w /root/aiProject/temmuzPoly/pm_orphan_sync.py -p wa -k aiproject_del
-w /root/aiProject/temmuzPoly/pm_trader_helpers.py -p wa -k aiproject_del
EOF
  augenrules --load 2>/dev/null || auditctl -R "$RULES" 2>/dev/null || true
  echo "audit rules loaded (key=aiproject_del)"
  auditctl -l 2>/dev/null | grep aiproject_del | head -5 || true
else
  echo "WARN: auditctl yok — sadece inotify incident JSON yazılacak"
  echo "      Kurmak için: apt-get install -y auditd && bash $ROOT/ops/install_file_watch.sh"
fi

echo "Log:     tail -f /tmp/aiproject_file_watch.log"
echo "Olaylar: ls $ROOT/ops/incidents/"
