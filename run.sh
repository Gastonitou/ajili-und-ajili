#!/bin/bash
# Ajili & Ajili App — Ein Befehl, alles läuft.
# Python 3 erforderlich.

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "🚀 Ajili & Ajili — App wird gestartet..."

# Venv erstellen falls nicht vorhanden
if [ ! -d "venv" ]; then
    echo "📦 Erstelle Python-Umgebung..."
    python3 -m venv venv
    source venv/bin/activate
    pip install fastapi uvicorn python-multipart pdfplumber pillow openai python-dotenv 2>&1 | tail -1
else
    source venv/bin/activate
fi

# Tesseract prüfen
if ! command -v tesseract &> /dev/null; then
    echo "⚠️  Tesseract (OCR) nicht gefunden."
    echo "   Installieren mit: sudo apt install tesseract-ocr tesseract-ocr-deu"
fi

# Server starten
echo ""
echo "  🌐 http://localhost:8000"
echo "  🇩🇪 DE: http://localhost:8000/"
echo "  🇬🇧 EN: http://localhost:8000/en"
echo "  📊 Admin: http://localhost:8000/admin"
echo ""

python start.py
