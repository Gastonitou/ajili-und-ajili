#!/usr/bin/env python3
"""
Ajili & Ajili — Business Cost Scanner App
One command: python start.py
"""

import os, sys, json, sqlite3, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from io import BytesIO
from functools import partial

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import pdfplumber
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

# ─── CONFIG ───
BASE = Path(__file__).parent
STATIC = BASE / "static"
PAGES = BASE / "pages"
DATA = BASE / "data"
UPLOADS = BASE / "uploads"
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
DB_PATH = DATA / "ajili.db"
GMAIL_USER = os.environ.get("GMAIL_USER", "ghassenlaajili6@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "ddzhexgbmcaebccy")
NOTIFY_EMAIL = "ghassenlaajili6@gmail.com"

# ─── APP ───
app = FastAPI(title="Ajili & Ajili", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# ─── HELPERS ───
def render(name):
    p = PAGES / name
    return HTMLResponse(p.read_text(encoding="utf-8") if p.exists() else "<h1>404</h1>")

def db():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

init_sql = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT,
    phone TEXT, company TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_name TEXT, client_email TEXT,
    filename TEXT, result TEXT, total_savings REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);"""

def init():
    c = db()
    c.executescript(init_sql)
    c.commit(); c.close()

def notify(subject, body):
    try:
        m = MIMEMultipart()
        m["From"] = f"Ajili & Ajili <{GMAIL_USER}>"
        m["To"] = NOTIFY_EMAIL
        m["Subject"] = f"[Ajili] {subject}"
        m.attach(MIMEText(body, "plain", "utf-8"))
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls(); s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(m); s.quit()
    except Exception as e:
        print(f"Email error: {e}")

def extract(file_bytes, name):
    try:
        if name.lower().endswith(".pdf"):
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        else:
            img = Image.open(BytesIO(file_bytes))
            if pytesseract:
                return pytesseract.image_to_string(img, lang="deu+eng")
            return "[OCR not available]"
    except Exception as e:
        return f"[Error: {e}]"

def analyze(text):
    cats, kw = [], {"Strom":["strom","kwh","energie","rwe","eon","grundversorgung"],"Versicherung":["versicherung","haftpflicht","praemie"],"Telefon/Internet":["telefon","internet","dsl","mobilfunk","telekom"],"Software":["software","lizenz","microsoft","adobe"],"Gas":["gas","erdgas","heizung"]}
    tl = text.lower()
    for cat, kws in kw.items():
        if any(k in tl for k in kws): cats.append(cat)
    if not cats: cats = ["Sonstiges"]
    s = "Hoch" if len(cats) >= 3 else ("Mittel" if len(cats) >= 2 else "Niedrig")
    recs = [f"Prüfen Sie Ihren {cats[0]}-Vertrag"]
    if "Strom" in cats: recs.append("Strom-Grundversorgung wechseln → bis 30% günstiger")
    if "Versicherung" in cats: recs.append("Versicherungen vergleichen")
    return {"categories": cats, "savings": s, "recommendations": recs}

# ─── ROUTES: PAGES ───
PAGE_MAP = {
    "/": "index.html",
    "/leistungen": "leistungen.html",
    "/scanner": "scanner.html",
    "/kontakt": "kontakt.html",
    "/en": "index_en.html",
    "/en/services": "services_en.html",
    "/en/scanner": "scanner_en.html",
    "/en/contact": "contact_en.html",
}

for route, file in PAGE_MAP.items():
    async def _handler(_r=None, _file=file):
        return render(_file)
    _handler.__name__ = f"page_{route.replace('/', '_') or 'root'}"
    app.add_api_route(route, _handler, methods=["GET"])

# ─── ROUTES: ADMIN ───
@app.get("/admin", response_class=HTMLResponse)
async def admin():
    c = db()
    contacts = [dict(x) for x in c.execute("SELECT * FROM contacts ORDER BY id DESC LIMIT 20").fetchall()]
    analyses = [dict(x) for x in c.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT 10").fetchall()]
    c.close()

    html = (PAGES / "admin.html").read_text(encoding="utf-8")
    items = "".join(f'<div class="item"><strong>{x["name"]}</strong> · {x["email"]}<p>{x["message"][:80]}</p><small>{x["created_at"]}</small></div>' for x in contacts) or "<p>Keine Anfragen</p>"
    items2 = "".join(f'<div class="item"><strong>{x["filename"]}</strong><p>€{x["total_savings"]}</p><small>{x["created_at"]}</small></div>' for x in analyses) or "<p>Keine Analysen</p>"
    return HTMLResponse(html.replace("{{ contacts|safe }}", items).replace("{{ analyses|safe }}", items2))

# ─── ROUTES: API ───
@app.post("/api/kontakt")
async def api_kontakt(name: str = Form(...), email: str = Form(...),
                       phone: str = Form(""), company: str = Form(""), message: str = Form(...)):
    c = db()
    c.execute("INSERT INTO contacts (name,email,phone,company,message) VALUES (?,?,?,?,?)",
              (name, email, phone, company, message))
    c.commit(); c.close()
    notify(f"Neue Anfrage von {name}", f"Name: {name}\nEmail: {email}\nFirma: {company}\n\n{message}")
    return JSONResponse({"status": "ok", "message": "Vielen Dank! Wir melden uns in 24h."})

@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...),
                       client_name: str = Form(""), client_email: str = Form("")):
    content = await file.read()
    (UPLOADS / file.filename).write_bytes(content)
    text = extract(content, file.filename)
    result = analyze(text)
    c = db()
    c.execute("INSERT INTO analyses (client_name,client_email,filename,result,total_savings) VALUES (?,?,?,?,?)",
              (client_name, client_email, file.filename, json.dumps(result), result.get("saving_amount", 0)))
    c.commit(); c.close()
    return JSONResponse({"status": "ok", "result": result, "preview": text[:300]})

# ─── START ───
if __name__ == "__main__":
    import uvicorn
    init()
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*50}")
    print(f"  🚀 Ajili & Ajili — Business Cost Scanner")
    print(f"  🌐 http://localhost:{port}")
    print(f"  🇩🇪 DE: http://localhost:{port}/")
    print(f"  🇬🇧 EN: http://localhost:{port}/en")
    print(f"  📊 Admin: http://localhost:{port}/admin")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
