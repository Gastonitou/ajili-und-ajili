"""
Ajili & Ajili — Fullstack Business Website
FastAPI + SQLite + Email Integration
"""

import os, json, sqlite3, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from io import BytesIO
from datetime import datetime

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import pdfplumber
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

# --- Config ---
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "ajili.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(BASE_DIR / "data").mkdir(exist_ok=True)

GMAIL_USER = os.environ.get("GMAIL_USER", "ghassenlaajili6@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "ddzhexgbmcaebccy")
NOTIFY_EMAIL = "ghassenlaajili6@gmail.com"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# --- App ---
app = FastAPI(title="Ajili & Ajili", version="1.0.0")

# Serve static files (CSS, JS, Images)
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# --- Helper: read HTML ---
def html(name: str) -> str:
    path = BASE_DIR / "pages" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<h1>404</h1>"

# --- Database ---
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT NOT NULL,
            phone TEXT, company TEXT, message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT, client_email TEXT,
            filename TEXT, result TEXT,
            total_savings REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

init_db()

# --- Email ---
def send_notification(subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = f"Ajili & Ajili <{GMAIL_USER}>"
        msg["To"] = NOTIFY_EMAIL
        msg["Subject"] = f"[Ajili] {subject}"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)
        s.quit()
    except Exception as e:
        print(f"Email error: {e}")

# --- Scanner ---
def extract_text(file_bytes: bytes, filename: str) -> str:
    try:
        if filename.lower().endswith(".pdf"):
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        else:
            img = Image.open(BytesIO(file_bytes))
            if pytesseract:
                return pytesseract.image_to_string(img, lang="deu+eng")
            return "[Bild erkannt - OCR nicht installiert]"
    except Exception as e:
        return f"[Fehler: {e}]"

def analyze(text: str) -> dict:
    cats = []
    kw_map = {
        "Strom": ["strom", "kwh", "energie", "rwe", "eon", "grundversorgung"],
        "Gas": ["gas", "erdgas", "heizung"],
        "Versicherung": ["versicherung", "haftpflicht", "prämie", "beitrag"],
        "Telefon/Internet": ["telefon", "internet", "dsl", "mobilfunk", "telekom"],
        "Software": ["software", "lizenz", "microsoft", "adobe"]
    }
    tl = text.lower()
    for cat, kws in kw_map.items():
        if any(k in tl for k in kws):
            cats.append(cat)
    if not cats:
        cats = ["Sonstiges"]

    savings = "Hoch" if len(cats) >= 3 else ("Mittel" if len(cats) >= 2 else "Niedrig")
    recs = [
        f"Prüfen Sie Ihren {cats[0]}-Vertrag" if cats else "Kosten manuell prüfen",
        "Strom-Grundversorgung wechseln → bis 30% günstiger" if "Strom" in cats else "",
        "Versicherungen vergleichen" if "Versicherung" in cats else ""
    ]

    # Try AI analysis
    ai = {}
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            r = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"Analysiere diese Rechnung und finde Sparpotenzial. JSON mit type, provider, amount, saving_amount, saving_note, recommendation: {text[:3000]}"}],
                response_format={"type": "json_object"}
            )
            ai = json.loads(r.choices[0].message.content)
        except:
            pass

    return {**{"categories": cats, "savings": savings, "recommendations": [r for r in recs if r]}, **ai}

# --- Routes: Pages ---
@app.get("/", response_class=HTMLResponse)
async def home(): return html("index.html")

@app.get("/leistungen", response_class=HTMLResponse)
async def leistungen(): return html("leistungen.html")

@app.get("/scanner", response_class=HTMLResponse)
async def scanner(): return html("scanner.html")

@app.get("/kontakt", response_class=HTMLResponse)
async def kontakt(): return html("kontakt.html")

@app.get("/admin", response_class=HTMLResponse)
async def admin():
    conn = get_db()
    contacts = conn.execute("SELECT * FROM contacts ORDER BY id DESC LIMIT 20").fetchall()
    analyses = conn.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()

    html_content = html("admin.html")
    html_content = html_content.replace("{{ contacts|safe }}",
        "".join(f'<div class="item"><strong>{c["name"]}</strong> {c["email"]}<p>{c["message"][:100]}</p><small>{c["created_at"]}</small></div>'
                for c in [dict(c) for c in contacts]) or "<p>Keine Anfragen</p>")
    html_content = html_content.replace("{{ analyses|safe }}",
        "".join(f'<div class="item"><strong>{a["filename"]}</strong><p>Einsparung: €{a["total_savings"]}</p><small>{a["created_at"]}</small></div>'
                for a in [dict(a) for a in analyses]) or "<p>Keine Analysen</p>")
    return html_content

# --- API ---
@app.post("/api/kontakt")
async def api_kontakt(name: str = Form(...), email: str = Form(...),
                       phone: str = Form(""), company: str = Form(""),
                       message: str = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO contacts (name,email,phone,company,message) VALUES (?,?,?,?,?)",
                 (name, email, phone, company, message))
    conn.commit()
    conn.close()
    send_notification(f"Neue Anfrage von {name}",
                      f"Name: {name}\nEmail: {email}\nFirma: {company}\n\n{message}")
    return JSONResponse({"status": "ok", "message": "Vielen Dank! Wir melden uns in 24h."})

@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...),
                       client_name: str = Form(""), client_email: str = Form("")):
    content = await file.read()
    with open(UPLOAD_DIR / file.filename, "wb") as f:
        f.write(content)
    text = extract_text(content, file.filename)
    result = analyze(text)

    conn = get_db()
    conn.execute("INSERT INTO analyses (client_name,client_email,filename,result,total_savings) VALUES (?,?,?,?,?)",
                 (client_name, client_email, file.filename, json.dumps(result),
                  result.get("saving_amount", 0)))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "ok", "result": result, "preview": text[:300]})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
