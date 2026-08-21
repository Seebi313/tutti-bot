#!/usr/bin/env bash
# Setup-Script für den Tutti.ch Gratis-Bot auf dem Pi
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Tutti.ch Gratis-Bot Setup ==="
echo "Arbeitsverzeichnis: $SCRIPT_DIR"
echo ""

# Virtualenv erstellen und Dependencies installieren
echo "[1/3] Python-Abhängigkeiten installieren..."
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
echo "      OK"

# Config erstellen
echo "[2/3] Konfiguration..."
if [ ! -f config.yml ]; then
    cp config.yml.example config.yml
    echo "      config.yml erstellt — bitte jetzt ausfüllen:"
    echo "      - email.smtp_password (Gmail App-Passwort)"
    echo "      - groq_api_key"
    echo ""
    echo "      Dann testen mit: venv/bin/python main.py --dry-run"
else
    echo "      config.yml existiert bereits"
fi

# Systemd
echo "[3/3] Systemd-Timer installieren?"
read -rp "      (j/N): " yn
if [[ "$yn" =~ ^[jJ]$ ]]; then
    # Service-Datei mit aktuellem Pfad und User anpassen
    sed \
        -e "s|/home/pi/tutti-bot|$SCRIPT_DIR|g" \
        -e "s|User=pi|User=$(whoami)|g" \
        tutti-bot.service > /tmp/tutti-bot.service

    sudo cp /tmp/tutti-bot.service /etc/systemd/system/tutti-bot.service
    sudo cp tutti-bot.timer /etc/systemd/system/tutti-bot.timer
    sudo systemctl daemon-reload
    sudo systemctl enable --now tutti-bot.timer

    echo ""
    echo "      Timer aktiv. Läuft alle 30 Minuten."
    echo "      Status:  sudo systemctl status tutti-bot.timer"
    echo "      Logs:    journalctl -u tutti-bot.service -f"
else
    echo "      Übersprungen. Manuell starten: venv/bin/python main.py"
fi

echo ""
echo "=== Fertig! ==="
echo "Test-Lauf (kein Email): venv/bin/python main.py --dry-run"
echo "Echter Lauf:            venv/bin/python main.py"
