\
import os
import csv
import secrets
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# ---------- Config ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(ROOT_DIR, "app.db")

os.makedirs(os.path.join(ROOT_DIR, "static", "players"), exist_ok=True)
os.makedirs(os.path.join(ROOT_DIR, "static", "drills"), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ---------- Models ----------
class Instructor(Base):
    __tablename__ = "instructors"
    id = Column(Integer, primary_key=True)
    name = Column(String, default="Coach")
    code = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    stars = relationship("Star", back_populates="instructor", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="instructor", cascade="all, delete-orphan")

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    code = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    metrics = relationship("Metric", back_populates="player", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="player", cascade="all, delete-orphan")
    drills = relationship("SharedDrill", back_populates="player", cascade="all, delete-orphan")
    stars = relationship("Star", back_populates="player", cascade="all, delete-orphan")

class Metric(Base):
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    exit_velocity = Column(Float, nullable=True)
    player = relationship("Player", back_populates="metrics")

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    instructor_id = Column(Integer, ForeignKey("instructors.id"))
    text = Column(String, nullable=False)
    shared_with_player = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    player = relationship("Player", back_populates="notes")
    instructor = relationship("Instructor", back_populates="notes")

class Star(Base):
    __tablename__ = "stars"
    id = Column(Integer, primary_key=True)
    instructor_id = Column(Integer, ForeignKey("instructors.id"))
    player_id = Column(Integer, ForeignKey("players.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('instructor_id', 'player_id', name='_instructor_player_star_uc'),)
    instructor = relationship("Instructor", back_populates="stars")
    player = relationship("Player", back_populates="stars")

class SharedDrill(Base):
    __tablename__ = "shared_drills"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    instructor_id = Column(Integer, ForeignKey("instructors.id"))
    filename = Column(String, nullable=False)
    title = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    player = relationship("Player", back_populates="drills")

Base.metadata.create_all(engine)

# ---------- App ----------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev_secret"))
app.mount("/static", StaticFiles(directory=os.path.join(ROOT_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(ROOT_DIR, "templates"))

# ---------- Helpers ----------
def get_user(request: Request):
    return request.session.get("user")

def age_bucket(age: Optional[int]) -> str:
    if age is None:
        return "Unassigned"
    if 7 <= age <= 9: return "7-9"
    if 10 <= age <= 12: return "10-12"
    if 13 <= age <= 15: return "13-15"
    if 16 <= age <= 18: return "16-18"
    if age >= 19: return "18+"
    return "Unassigned"

def ensure_master(db):
    master = os.getenv("INSTRUCTOR_MASTER_CODE", "COACH123")
    if not db.query(Instructor).filter_by(code=master).first():
        db.add(Instructor(name="Head Coach", code=master)); db.commit()

def redir(to: str): return RedirectResponse(to, status_code=303)
def pop_flash(request: Request):
    f = request.session.pop("flash", None)
    return f

templates.env.globals["get_user"] = get_user
templates.env.globals["age_bucket"] = age_bucket
templates.env.globals["now"] = lambda: datetime.utcnow()
templates.env.globals["pop_flash"] = pop_flash

# ---------- Player routes ----------
@app.get("/")
def dashboard(request: Request):
    with SessionLocal() as s:
        u = get_user(request)
        player = None; note = None; points = []
        if u and u.get("type")=="player":
            player = s.query(Player).get(u["id"])
            if player:
                note = s.query(Note).filter_by(player_id=player.id, shared_with_player=True).order_by(Note.created_at.desc()).first()
                ms = s.query(Metric).filter_by(player_id=player.id).order_by(Metric.created_at.asc()).all()
                points = [{"x": m.created_at.strftime("%Y-%m-%d"), "y": m.exit_velocity or 0} for m in ms]
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "player": player, "shared_note": note, "chart_points": points
        })

@app.post("/login_player")
def login_player(request: Request, code: str = Form(...)):
    with SessionLocal() as s:
        p = s.query(Player).filter_by(code=code.strip()).first()
        if not p:
            request.session["flash"] = {"type":"warn","msg":"Invalid player code."}
            return redir("/")
        request.session["user"] = {"type":"player","id": p.id, "name": p.name}
        return redir("/")

# ---------- Instructor routes ----------
@app.get("/instructor")
def instructor(request: Request):
    with SessionLocal() as s:
        ensure_master(s)
        u = get_user(request)
        instructor = None
        if u and u.get("type")=="instructor":
            instructor = s.query(Instructor).get(u["id"])
        players = s.query(Player).order_by(Player.created_at.desc()).all()
        grouped = {"7-9":[], "10-12":[], "13-15":[], "16-18":[], "18+":[], "Unassigned":[]}
        for p in players: grouped[age_bucket(p.age)].append(p)
        starred_ids = set()
        if instructor:
            starred_ids = {st.player_id for st in s.query(Star).filter_by(instructor_id=instructor.id).all()}
        counts = {p.id: s.query(Metric).filter_by(player_id=p.id).count() for p in players}
        drill_files = sorted([f for f in os.listdir(os.path.join(ROOT_DIR, "static", "drills")) if not f.startswith(".")])
        sms_ready = all(os.getenv(k) for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"])
        return templates.TemplateResponse("instructor_players.html", {
            "request": request, "instructor": instructor, "grouped": grouped,
            "starred_ids": starred_ids, "session_counts": counts, "drill_files": drill_files,
            "sms_ready": sms_ready
        })

@app.post("/login_instructor")
def login_instructor(request: Request, code: str = Form(...), name: Optional[str] = Form(None)):
    with SessionLocal() as s:
        code = code.strip()
        ins = s.query(Instructor).filter_by(code=code).first()
        if not ins:
            master = os.getenv("INSTRUCTOR_MASTER_CODE", "COACH123")
            if code == master and name:
                ins = Instructor(name=(name or "Coach").strip(), code=secrets.token_hex(3).upper())
                s.add(ins); s.commit()
                request.session["flash"] = {"type":"ok", "msg": f"Instructor created. Your login code: {ins.code}"}
            else:
                request.session["flash"] = {"type":"warn", "msg": "Invalid instructor code."}
                return redir("/instructor")
        request.session["user"] = {"type":"instructor","id": ins.id, "name": ins.name}
        return redir("/instructor")

@app.post("/logout")
def logout(request: Request):
    request.session.clear(); return redir("/")

# ---------- Actions ----------
@app.post("/players/create")
def create_player(request: Request, name: str = Form(...), age: Optional[int] = Form(None),
                  phone: Optional[str] = Form(None), photo: Optional[UploadFile] = File(None)):
    with SessionLocal() as s:
        u = get_user(request)
        if not u or u.get("type")!="instructor":
            return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
        code = secrets.token_hex(3).upper()
        p = Player(name=name.strip(), age=(int(age) if age else None), phone=(phone or "").strip(), code=code)
        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower() or ".jpg"
            fname = f"p_{secrets.token_hex(8)}{ext}"
            dest = os.path.join(ROOT_DIR, "static", "players", fname)
            with open(dest, "wb") as f: f.write(photo.file.read())
            p.photo_path = f"/static/players/{fname}"
        s.add(p); s.commit()
        request.session["flash"] = {"type":"ok","msg": f"Player created. Login code: {p.code}"}
        return redir("/instructor")

@app.post("/players/bulk_csv")
def bulk_csv(request: Request, file: UploadFile = File(...)):
    with SessionLocal() as s:
        u = get_user(request)
        if not u or u.get("type")!="instructor":
            return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
        created = 0
        content = file.file.read().decode("utf-8").splitlines()
        reader = csv.DictReader(content)
        for row in reader:
            name = (row.get("name") or row.get("Name") or "").strip()
            if not name: continue
            age_raw = (row.get("age") or row.get("Age") or "").strip()
            age = int(age_raw) if age_raw.isdigit() else None
            phone = (row.get("phone") or row.get("Phone") or "").strip()
            code = secrets.token_hex(3).upper()
            s.add(Player(name=name, age=age, phone=phone, code=code)); created += 1
        s.commit()
        request.session["flash"] = {"type":"ok","msg": f"Imported {created} players."}
        return redir("/instructor")

@app.post("/metrics/add")
def add_metric(request: Request, player_id: int = Form(...), exit_velocity: float = Form(...)):
    with SessionLocal() as s:
        u = get_user(request)
        if not u or u.get("type")!="instructor":
            return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
        s.add(Metric(player_id=player_id, exit_velocity=exit_velocity)); s.commit()
        return redir("/instructor")

@app.post("/notes/add")
def add_note(request: Request, player_id: int = Form(...), text: str = Form(...), share_with_player: Optional[bool] = Form(False)):
    with SessionLocal() as s:
        u = get_user(request)
        if not u or u.get("type")!="instructor":
            return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
        s.add(Note(player_id=player_id, instructor_id=u["id"], text=text.strip(), shared_with_player=bool(share_with_player))); s.commit()
        request.session["flash"] = {"type":"ok","msg": "Note saved."}
        return redir("/instructor")

@app.post("/star/toggle")
def toggle_star(request: Request, player_id: int = Form(...)):
    with SessionLocal() as s:
        u = get_user(request)
        if not u or u.get("type")!="instructor":
            return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
        ex = s.query(Star).filter_by(instructor_id=u["id"], player_id=player_id).first()
        active = False
        if ex: s.delete(ex); s.commit()
        else: s.add(Star(instructor_id=u["id"], player_id=player_id)); s.commit(); active=True
        count = s.query(Star).filter_by(instructor_id=u["id"]).count()
        return JSONResponse({"ok":True,"active":active,"count":count})

@app.post("/drills/upload")
def upload_drill(request: Request, file: UploadFile = File(...)):
    u = get_user(request)
    if not u or u.get("type")!="instructor":
        return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
    ext = os.path.splitext(file.filename)[1].lower()
    fname = f"drill_{secrets.token_hex(8)}{ext}"
    dest = os.path.join(ROOT_DIR, "static", "drills", fname)
    with open(dest, "wb") as f: f.write(file.file.read())
    return redir("/instructor")

@app.post("/drills/send")
def send_drill(request: Request, player_id: int = Form(...), filename: str = Form(...), title: Optional[str] = Form(None), text_also: Optional[bool] = Form(False)):
    with SessionLocal() as s:
        u = get_user(request)
        if not u or u.get("type")!="instructor":
            return JSONResponse({"ok":False,"error":"Unauthorized"}, status_code=401)
        s.add(SharedDrill(player_id=player_id, instructor_id=u["id"], filename=filename, title=title)); s.commit()
        if text_also:
            from twilio.rest import Client
            sid, tok, frm = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
            if sid and tok and frm:
                pl = s.query(Player).get(player_id)
                if pl and pl.phone:
                    try:
                        Client(sid, tok).messages.create(body=f"Coach shared a drill: {title or filename}", from_=frm, to=pl.phone)
                    except Exception: pass
        request.session["flash"] = {"type":"ok","msg":"Drill shared with player."}
        return redir("/instructor")

@app.post("/text/send")
def text_player(request: Request, player_id: int = Form(...), body: str = Form(...)):
    from twilio.rest import Client
    sid, tok, frm = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not (sid and tok and frm):
        request.session["flash"] = {"type":"warn","msg":"Twilio not configured."}
        return redir("/instructor")
    with SessionLocal() as s:
        pl = s.query(Player).get(player_id)
        if not pl or not pl.phone:
            request.session["flash"] = {"type":"warn","msg":"Player phone missing."}
            return redir("/instructor")
        try:
            Client(sid, tok).messages.create(body=body, from_=frm, to=pl.phone)
            request.session["flash"] = {"type":"ok","msg":"Text sent."}
        except Exception as e:
            request.session["flash"] = {"type":"warn","msg":f"Text failed: {e}"}
    return redir("/instructor")
