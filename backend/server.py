from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid, logging, bcrypt, jwt, requests, random, string
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("evenza")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
SEED_VERSION = 3
MIN_SEEDED_EVENTS = 26
MIN_FEE = 49

app = FastAPI(title="EVENZA API")
api = APIRouter(prefix="/api")

# ----------------------------- Reference Data -----------------------------
CATEGORIES: Dict[str, List[str]] = {
    "Academic": ["Mathematics", "Science", "Social Science", "General Knowledge", "Quiz", "Olympiads", "Spell Bee", "STEM Challenges", "Interdisciplinary Challenges"],
    "Communication": ["Debate", "Public Speaking", "Elocution", "Extempore", "Storytelling", "Model United Nations", "Youth Parliament"],
    "Writing & Literature": ["Creative Writing", "Essay Writing", "Story Writing", "Poetry", "Reading", "Language & Literature", "Journalism & Media"],
    "Technology": ["Coding & Programming", "Robotics", "Artificial Intelligence", "AI Hackathons", "App Development", "Web Development", "Game Jams", "Esports", "Innovation & Invention"],
    "Entrepreneurship & Business": ["Entrepreneurship", "Business & Finance", "Business Plan", "Startup Pitch", "Marketing", "Market Day"],
    "Arts": ["Drawing & Sketching", "Painting", "Photography", "Graphic Design", "Digital Art", "Craft & DIY", "Anime / Manga / Digital Illustration"],
    "Performing Arts": ["Dance", "Music", "Singing", "Instrumental Music", "Theatre & Drama", "Stand-up Comedy", "Fashion & Styling"],
    "Creative Media": ["Film & Video Making", "Short Film", "Podcasting", "Video Editing"],
    "Sports": ["Football", "Cricket", "Basketball", "Volleyball", "Badminton", "Athletics", "Swimming", "Table Tennis", "Kabaddi", "Chess & Board Games", "Pickleball", "Padel", "Rifle Shooting"],
    "Lifestyle & Impact": ["Culinary & Cooking", "Environmental & Sustainability", "Community & Social Impact", "Cultural & Heritage", "Talent & Variety", "Mental Math & Memory"],
}
LOCATIONS = ["Mumbai", "Navi Mumbai", "Thane", "Pune", "Nagpur", "Nashik", "Chhatrapati Sambhajinagar",
             "Kolhapur", "Solapur", "Amravati", "Satara", "Sangli", "Ratnagiri", "Raigad", "Jalgaon", "Ahilyanagar"]
AGE_GROUPS = ["5-8", "8-11", "11-15", "15-18", "18-24"]

def age_to_group(age: int) -> str:
    if age <= 8: return "5-8"
    if age <= 11: return "8-11"
    if age <= 15: return "11-15"
    if age <= 18: return "15-18"
    return "18-24"

# ----------------------------- Models -----------------------------
class RegisterBody(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "participant"
    age: Optional[int] = None
    student_class: Optional[str] = None
    location: Optional[str] = "Mumbai"
    interests: List[str] = []
    organisation: Optional[str] = None
    referral_code: Optional[str] = None

class LoginBody(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    student_class: Optional[str] = None
    location: Optional[str] = None
    interests: Optional[List[str]] = None
    organisation: Optional[str] = None
    bio: Optional[str] = None

class EventBody(BaseModel):
    name: str
    organiser: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    description: str = ""
    age_group: str = "15-18"
    eligibility: str = "Open to all"
    location: str = "Mumbai"
    mode: str = "Physical"
    date: str = ""
    time: str = ""
    deadline: str = ""
    fee: float = MIN_FEE
    rules: str = ""
    contact: str = ""
    capacity: int = 100
    prize: str = ""
    image: str = ""
    status: str = "published"
    meeting_link: Optional[str] = None
    meeting_password: Optional[str] = None

class TaxConfig(BaseModel):
    platform_fee_type: str = "percentage"    # percentage | fixed
    platform_fee_value: float = 5             # 5% of base
    convenience_fee_type: str = "fixed"       # fixed | percentage
    convenience_fee_value: float = 20         # ₹20 flat
    gst_rate: float = 0.18                     # 18% (real service GST slab)
    gst_on: str = "fees"                       # fees (platform+convenience) | total
    intra_state: bool = True                   # Maharashtra -> CGST+SGST
    effective_date: str = "2026-01-01"

class ChatBody(BaseModel):
    message: str
    history: List[Dict[str, str]] = []

# ----------------------------- Helpers -----------------------------
def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def verify_pw(p, h):
    try: return bcrypt.checkpw(p.encode(), h.encode())
    except Exception: return False
def make_token(uid): return jwt.encode({"sub": uid, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALG)
def gen_referral(): return "EVZA" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
def now_iso(): return datetime.now(timezone.utc).isoformat()
def clean(doc):
    if doc:
        doc.pop("_id", None); doc.pop("password_hash", None)
    return doc

async def resolve_token(token):
    if not token: return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        u = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
        if u: return u
    except Exception:
        pass
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if sess:
        exp = sess.get("expires_at")
        if isinstance(exp, str): exp = datetime.fromisoformat(exp)
        if exp and exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp < datetime.now(timezone.utc): return None
        return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    return None

async def get_current_user(request: Request):
    token = request.cookies.get("access_token") or request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "): token = auth[7:]
    user = await resolve_token(token)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    return user

async def optional_user(request: Request):
    try: return await get_current_user(request)
    except HTTPException: return None

async def notify(uid, title, body, kind="info"):
    await db.notifications.insert_one({"id": str(uuid.uuid4()), "user_id": uid, "title": title, "body": body, "kind": kind, "read": False, "created_at": now_iso()})

# ----------------------------- Tax / Payment engine -----------------------------
async def get_tax_config():
    cfg = await db.config.find_one({"key": "tax"}, {"_id": 0})
    if not cfg:
        cfg = {"key": "tax", **TaxConfig().model_dump()}
        await db.config.insert_one(dict(cfg))
    return cfg

def r2(x): return round(x + 1e-9, 2)

async def compute_breakdown(base_fee):
    cfg = await get_tax_config()
    base = r2(float(base_fee))
    platform = r2(float(cfg["platform_fee_value"])) if cfg["platform_fee_type"] == "fixed" else r2(base * float(cfg["platform_fee_value"]) / 100.0)
    conv = r2(float(cfg["convenience_fee_value"])) if cfg.get("convenience_fee_type", "fixed") == "fixed" else r2(base * float(cfg.get("convenience_fee_value", 0)) / 100.0)
    taxable = r2(platform + conv) if cfg["gst_on"] == "fees" else r2(base + platform + conv)
    gst_total = r2(taxable * float(cfg["gst_rate"]))
    intra = bool(cfg["intra_state"])
    cgst = r2(gst_total / 2) if intra else 0.0
    sgst = r2(gst_total - cgst) if intra else 0.0
    igst = 0.0 if intra else gst_total
    total = r2(base + platform + conv + cgst + sgst + igst)
    return {"base_fee": base, "platform_charge": platform, "convenience_fee": conv, "taxable_component": taxable,
            "gst_rate_pct": round(float(cfg["gst_rate"]) * 100, 2), "gst_total": r2(cgst + sgst + igst),
            "cgst": cgst, "sgst": sgst, "igst": igst, "intra_state": intra, "total": total, "currency": "INR"}

# ----------------------------- Auth endpoints -----------------------------
@api.get("/")
async def root(): return {"message": "EVENZA API", "status": "ok"}

@api.post("/auth/register")
async def register(body: RegisterBody, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = f"user_{uuid.uuid4().hex[:12]}"
    ag = age_to_group(body.age) if body.age else None
    user = {"user_id": uid, "email": email, "password_hash": hash_pw(body.password), "name": body.name,
            "role": body.role if body.role in ("participant", "organiser") else "participant",
            "age": body.age, "age_group": ag, "student_class": body.student_class, "location": body.location or "Mumbai",
            "interests": body.interests or [], "organisation": body.organisation, "bio": "",
            "referral_code": gen_referral(), "referred_by": None, "picture": None, "created_at": now_iso()}
    if body.referral_code:
        ref = await db.users.find_one({"referral_code": body.referral_code.strip().upper()}, {"_id": 0})
        if ref and ref["user_id"] != uid:
            user["referred_by"] = ref["referral_code"]
            await db.referrals.insert_one({"id": str(uuid.uuid4()), "referrer_id": ref["user_id"], "referrer_code": ref["referral_code"],
                                           "referred_user_id": uid, "referred_name": body.name, "status": "registered", "created_at": now_iso()})
            await notify(ref["user_id"], "New referral 🎉", f"{body.name} joined EVENZA using your code.", "referral")
    await db.users.insert_one(dict(user))
    await notify(uid, "Welcome to EVENZA 👋", "Where opportunities find you. Start discovering competitions built for you.", "info")
    token = make_token(uid)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return {"token": token, "user": clean(dict(user))}

@api.post("/auth/login")
async def login(body: LoginBody, response: Response):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not user.get("password_hash") or not verify_pw(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = make_token(user["user_id"])
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return {"token": token, "user": clean(dict(user))}

@api.post("/auth/session")
async def google_session(request: Request, response: Response):
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id: raise HTTPException(status_code=400, detail="Missing session_id")
    r = requests.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": session_id}, timeout=15)
    if r.status_code != 200: raise HTTPException(status_code=401, detail="Invalid session")
    data = r.json()
    email = data["email"].lower()
    role = body.get("role", "participant")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        user = {"user_id": uid, "email": email, "password_hash": None, "name": data.get("name", email),
                "role": role if role in ("participant", "organiser") else "participant", "age": None, "age_group": None,
                "student_class": None, "location": "Mumbai", "interests": [], "organisation": None, "bio": "",
                "referral_code": gen_referral(), "referred_by": None, "picture": data.get("picture"), "created_at": now_iso()}
        await db.users.insert_one(dict(user))
        await notify(uid, "Welcome to EVENZA 👋", "Where opportunities find you.", "info")
    st = data["session_token"]
    await db.user_sessions.insert_one({"user_id": user["user_id"], "session_token": st,
                                       "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(), "created_at": now_iso()})
    response.set_cookie("session_token", st, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return {"token": st, "user": clean(dict(user))}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)): return clean(dict(user))

@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token: await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("access_token", path="/"); response.delete_cookie("session_token", path="/")
    return {"ok": True}

@api.put("/auth/profile")
async def update_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd.get("age"): upd["age_group"] = age_to_group(upd["age"])
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return clean(dict(await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})))

# ----------------------------- Config -----------------------------
@api.get("/config/categories")
async def get_categories(): return CATEGORIES

@api.get("/config/locations")
async def get_locations(): return LOCATIONS

@api.get("/config/age-groups")
async def get_age_groups(): return AGE_GROUPS

@api.get("/config/tax")
async def tax_get():
    cfg = await get_tax_config(); cfg.pop("key", None); return cfg

@api.put("/config/tax")
async def tax_put(body: TaxConfig, user: dict = Depends(get_current_user)):
    if user["role"] not in ("organiser", "admin"): raise HTTPException(status_code=403, detail="Not allowed")
    await db.config.update_one({"key": "tax"}, {"$set": {"key": "tax", **body.model_dump()}}, upsert=True)
    return {"ok": True, **body.model_dump()}

# ----------------------------- Events -----------------------------
@api.get("/events")
async def list_events(category: Optional[str] = None, subcategory: Optional[str] = None, age_group: Optional[str] = None,
                      location: Optional[str] = None, mode: Optional[str] = None, max_fee: Optional[float] = None,
                      eligibility: Optional[str] = None, q: Optional[str] = None):
    query: Dict[str, Any] = {"status": {"$ne": "draft"}}
    if category and category != "All": query["category"] = category
    if subcategory: query["subcategory"] = subcategory
    if age_group and age_group != "All": query["age_group"] = age_group
    if location and location not in ("All", "All Maharashtra"): query["location"] = location
    if mode and mode not in ("All", "All Modes"): query["mode"] = mode
    if eligibility: query["eligibility"] = {"$regex": eligibility, "$options": "i"}
    if max_fee is not None: query["fee"] = {"$lte": max_fee}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"organiser": {"$regex": q, "$options": "i"}},
                        {"category": {"$regex": q, "$options": "i"}}, {"subcategory": {"$regex": q, "$options": "i"}},
                        {"description": {"$regex": q, "$options": "i"}}]
    events = await db.events.find(query, {"_id": 0, "meeting_link": 0, "meeting_password": 0}).to_list(1000)
    events.sort(key=lambda e: e.get("date", ""))
    return events

@api.get("/events/mine")
async def my_events(user: dict = Depends(get_current_user)):
    events = await db.events.find({"organiser_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    for e in events:
        e["registration_count"] = await db.registrations.count_documents({"event_id": e["id"], "status": {"$ne": "cancelled"}})
    return events

@api.get("/events/{eid}")
async def get_event(eid: str):
    e = await db.events.find_one({"id": eid}, {"_id": 0, "meeting_link": 0, "meeting_password": 0})
    if not e: raise HTTPException(status_code=404, detail="Event not found")
    e["registration_count"] = await db.registrations.count_documents({"event_id": eid, "status": {"$ne": "cancelled"}})
    return e

@api.post("/events")
async def create_event(body: EventBody, user: dict = Depends(get_current_user)):
    if user["role"] not in ("organiser", "admin"): raise HTTPException(status_code=403, detail="Only organisers can create events")
    if float(body.fee) < MIN_FEE: raise HTTPException(status_code=400, detail=f"Minimum registration fee is ₹{MIN_FEE}")
    e = body.model_dump()
    e["id"] = str(uuid.uuid4()); e["organiser_id"] = user["user_id"]
    e["organiser"] = body.organiser or user.get("organisation") or user.get("name")
    if e["mode"] == "Virtual" and not e.get("meeting_link"):
        e["meeting_link"] = f"https://meet.evenza.in/{uuid.uuid4().hex[:10]}"
        e["meeting_password"] = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    e["created_at"] = now_iso()
    await db.events.insert_one(dict(e)); e.pop("_id", None)
    return e

@api.put("/events/{eid}")
async def update_event(eid: str, body: EventBody, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": eid})
    if not e: raise HTTPException(status_code=404, detail="Event not found")
    if e.get("organiser_id") != user["user_id"] and user["role"] != "admin": raise HTTPException(status_code=403, detail="Not your event")
    if float(body.fee) < MIN_FEE: raise HTTPException(status_code=400, detail=f"Minimum registration fee is ₹{MIN_FEE}")
    upd = body.model_dump(); upd["organiser"] = body.organiser or e.get("organiser")
    if upd["mode"] == "Virtual" and not upd.get("meeting_link"):
        upd["meeting_link"] = e.get("meeting_link") or f"https://meet.evenza.in/{uuid.uuid4().hex[:10]}"
        upd["meeting_password"] = e.get("meeting_password") or "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    await db.events.update_one({"id": eid}, {"$set": upd})
    for r in await db.registrations.find({"event_id": eid, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000):
        await notify(r["user_id"], "Event updated", f"'{upd['name']}' details were updated by the organiser.", "update")
    return await db.events.find_one({"id": eid}, {"_id": 0})

@api.delete("/events/{eid}")
async def cancel_event(eid: str, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": eid})
    if not e: raise HTTPException(status_code=404, detail="Event not found")
    if e.get("organiser_id") != user["user_id"] and user["role"] != "admin": raise HTTPException(status_code=403, detail="Not your event")
    count = await db.registrations.count_documents({"event_id": eid, "status": {"$ne": "cancelled"}})
    if count > 0:
        await db.events.update_one({"id": eid}, {"$set": {"status": "cancelled"}})
        await db.registrations.update_many({"event_id": eid}, {"$set": {"status": "event_cancelled"}})
        for r in await db.registrations.find({"event_id": eid}, {"_id": 0}).to_list(1000):
            await notify(r["user_id"], "Event cancelled", f"'{e['name']}' has been cancelled by the organiser.", "cancel")
        return {"ok": True, "action": "cancelled", "preserved_registrations": count}
    await db.events.delete_one({"id": eid})
    return {"ok": True, "action": "deleted"}

@api.get("/events/{eid}/registrations")
async def event_registrations(eid: str, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": eid})
    if not e or (e.get("organiser_id") != user["user_id"] and user["role"] != "admin"): raise HTTPException(status_code=403, detail="Not allowed")
    return await db.registrations.find({"event_id": eid}, {"_id": 0}).to_list(1000)

@api.post("/events/{eid}/registrations/{rid}/remind")
async def send_reminder(eid: str, rid: str, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": eid})
    if not e or (e.get("organiser_id") != user["user_id"] and user["role"] != "admin"): raise HTTPException(status_code=403, detail="Not allowed")
    reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
    if not reg: raise HTTPException(status_code=404, detail="Registration not found")
    await notify(reg["user_id"], "Reminder from organiser ⏰", f"Reminder: '{e['name']}' is coming up on {e.get('date','')}.", "reminder")
    await db.registrations.update_one({"id": rid}, {"$set": {"reminder_sent": True, "reminder_at": now_iso()}})
    return {"ok": True}

@api.post("/events/{eid}/registrations/{rid}/award")
async def set_award(eid: str, rid: str, request: Request, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": eid})
    if not e or (e.get("organiser_id") != user["user_id"] and user["role"] != "admin"): raise HTTPException(status_code=403, detail="Not allowed")
    body = await request.json()
    award = body.get("award", "")
    reg = await db.registrations.find_one({"id": rid}, {"_id": 0})
    if not reg: raise HTTPException(status_code=404, detail="Registration not found")
    await db.registrations.update_one({"id": rid}, {"$set": {"award": award, "result_declared": True}})
    await notify(reg["user_id"], "Result declared 🏆", f"Your result for '{e['name']}': {award or 'Participation'}. Certificate is ready!", "success")
    return {"ok": True}

# ----------------------------- Save / Registrations -----------------------------
@api.post("/events/{eid}/save")
async def toggle_save(eid: str, user: dict = Depends(get_current_user)):
    if await db.saved.find_one({"user_id": user["user_id"], "event_id": eid}):
        await db.saved.delete_one({"user_id": user["user_id"], "event_id": eid}); return {"saved": False}
    await db.saved.insert_one({"user_id": user["user_id"], "event_id": eid, "created_at": now_iso()}); return {"saved": True}

@api.get("/me/saved")
async def my_saved(user: dict = Depends(get_current_user)):
    ids = [s["event_id"] for s in await db.saved.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)]
    return await db.events.find({"id": {"$in": ids}}, {"_id": 0, "meeting_link": 0, "meeting_password": 0}).to_list(1000)

@api.post("/payments/quote")
async def payment_quote(request: Request):
    body = await request.json()
    e = await db.events.find_one({"id": body.get("event_id")}, {"_id": 0})
    if not e: raise HTTPException(status_code=404, detail="Event not found")
    bd = await compute_breakdown(e.get("fee", 0)); bd["event_name"] = e["name"]; return bd

@api.post("/registrations")
async def create_registration(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    eid = body.get("event_id")
    e = await db.events.find_one({"id": eid}, {"_id": 0})
    if not e: raise HTTPException(status_code=404, detail="Event not found")
    if await db.registrations.find_one({"event_id": eid, "user_id": user["user_id"], "status": {"$ne": "cancelled"}}):
        raise HTTPException(status_code=400, detail="Already registered for this event")
    bd = await compute_breakdown(e.get("fee", 0))
    payment_mode = body.get("payment_mode", "UPI")
    rid = str(uuid.uuid4()); txn_id = "TXN" + uuid.uuid4().hex[:10].upper()
    reg = {"id": rid, "event_id": eid, "event_name": e["name"], "user_id": user["user_id"], "participant_name": user["name"],
           "participant_email": user["email"], "age_group": user.get("age_group"), "status": "confirmed",
           "payment_mode": payment_mode, "reminder_sent": False, "award": None, "result_declared": False,
           "mode": e.get("mode"), "created_at": now_iso()}
    if e.get("mode") == "Virtual":
        reg["meeting_link"] = e.get("meeting_link") or f"https://meet.evenza.in/{uuid.uuid4().hex[:10]}"
        reg["meeting_password"] = e.get("meeting_password") or "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    await db.registrations.insert_one(dict(reg))
    txn = {"id": txn_id, "registration_id": rid, "event_id": eid, "user_id": user["user_id"],
           "event_registration_amount": bd["base_fee"], "platform_charge": bd["platform_charge"], "convenience_fee": bd["convenience_fee"],
           "gst_total": bd["gst_total"], "cgst": bd["cgst"], "sgst": bd["sgst"], "igst": bd["igst"], "total_paid": bd["total"],
           "payment_mode": payment_mode, "payment_status": "paid", "refund_amount": 0, "refund_status": "none",
           "provider": "razorpay_mock", "created_at": now_iso()}
    await db.transactions.insert_one(dict(txn))
    await notify(user["user_id"], "Registration successful ✅", f"You're registered for '{e['name']}'. Paid ₹{bd['total']:.2f}.", "success")
    if user.get("referred_by"):
        await db.referrals.update_one({"referred_user_id": user["user_id"]}, {"$set": {"status": "active", "last_registration": e["name"], "updated_at": now_iso()}})
    reg.pop("_id", None); txn.pop("_id", None)
    return {"registration": reg, "transaction": txn, "breakdown": bd}

@api.get("/me/registrations")
async def my_registrations(user: dict = Depends(get_current_user)):
    regs = await db.registrations.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    out = []
    for r in regs:
        ev = await db.events.find_one({"id": r["event_id"]}, {"_id": 0, "meeting_link": 0, "meeting_password": 0})
        txn = await db.transactions.find_one({"registration_id": r["id"]}, {"_id": 0})
        out.append({**r, "event": ev, "transaction": txn})
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out

@api.get("/me/achievements")
async def my_achievements(user: dict = Depends(get_current_user)):
    regs = await db.registrations.find({"user_id": user["user_id"], "status": {"$in": ["confirmed", "attended"]}}, {"_id": 0}).to_list(1000)
    today = datetime.now(timezone.utc).date().isoformat()
    achievements = []; skills = set()
    for r in regs:
        ev = await db.events.find_one({"id": r["event_id"]}, {"_id": 0})
        if ev:
            skills.add(ev.get("category"))
            past = (ev.get("date") or "") < today or r.get("result_declared")
            achievements.append({"registration_id": r["id"], "event_name": ev["name"], "category": ev.get("category"),
                                 "date": ev.get("date"), "certificate": True, "award": r.get("award"),
                                 "status": r.get("award") or ("Participated" if past else "Registered")})
    return {"participated": len([a for a in achievements if a["status"] == "Participated" or a["award"]]),
            "total": len(achievements), "skills": sorted([s for s in skills if s]), "achievements": achievements}

@api.get("/me/certificate/{rid}")
async def get_certificate(rid: str, user: dict = Depends(get_current_user)):
    reg = await db.registrations.find_one({"id": rid, "user_id": user["user_id"]}, {"_id": 0})
    if not reg: raise HTTPException(status_code=404, detail="Registration not found")
    ev = await db.events.find_one({"id": reg["event_id"]}, {"_id": 0})
    award = reg.get("award")
    return {"certificate_id": "EVZ-CERT-" + reg["id"][:8].upper(), "participant_name": reg["participant_name"],
            "event_name": reg["event_name"], "category": ev.get("category") if ev else "", "organiser": ev.get("organiser") if ev else "",
            "date": ev.get("date") if ev else "", "location": ev.get("location") if ev else "",
            "award": award, "title": award if award else "Certificate of Participation",
            "is_winner": bool(award)}

@api.get("/me/portfolio")
async def my_portfolio(user: dict = Depends(get_current_user)):
    regs = await db.registrations.find({"user_id": user["user_id"], "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000)
    cats = defaultdict(int); awards = []; items = []
    for r in regs:
        ev = await db.events.find_one({"id": r["event_id"]}, {"_id": 0})
        if not ev: continue
        cats[ev.get("category")] += 1
        if r.get("award"): awards.append({"event": ev["name"], "award": r["award"]})
        items.append({"event": ev["name"], "category": ev.get("category"), "date": ev.get("date"), "award": r.get("award"), "mode": ev.get("mode")})
    return {"name": user["name"], "email": user["email"], "location": user.get("location"), "age_group": user.get("age_group"),
            "student_class": user.get("student_class"), "bio": user.get("bio", ""), "interests": user.get("interests", []),
            "total_participations": len(items), "awards_count": len(awards), "skills": sorted(cats.keys()),
            "category_counts": dict(cats), "awards": awards, "items": sorted(items, key=lambda x: x.get("date", ""), reverse=True)}

@api.get("/me/analytics")
async def my_analytics(user: dict = Depends(get_current_user)):
    regs = await db.registrations.find({"user_id": user["user_id"], "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000)
    cats = defaultdict(int); monthly = defaultdict(int); points = 0; wins = 0
    for r in regs:
        ev = await db.events.find_one({"id": r["event_id"]}, {"_id": 0})
        if ev: cats[ev.get("category")] += 1
        m = (r.get("created_at") or "")[:7]
        if m: monthly[m] += 1
        points += 100
        if r.get("award"): points += 150; wins += 1
    months = sorted(monthly.keys())[-6:]
    return {"points": points, "participations": len(regs), "wins": wins,
            "category_distribution": [{"name": k, "value": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])],
            "monthly": [{"month": m, "count": monthly[m]} for m in months]}

# ----------------------------- Recommendations -----------------------------
@api.get("/me/recommended")
async def recommended(user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    events = await db.events.find({"status": "published", "date": {"$gte": today}}, {"_id": 0, "meeting_link": 0, "meeting_password": 0}).to_list(1000)
    interests = set(i.lower() for i in (user.get("interests") or []))
    loc, ag = user.get("location"), user.get("age_group")
    def score(e):
        s = 0; text = f"{e.get('category','')} {e.get('subcategory','')} {e.get('name','')}".lower()
        for it in interests:
            if it in text: s += 5
        if ag and e.get("age_group") == ag: s += 3
        if loc and e.get("location") == loc: s += 2
        return s
    events.sort(key=lambda e: (score(e), e.get("date", "")), reverse=True)
    return events[:9]

# ----------------------------- Referrals -----------------------------
@api.get("/me/referrals")
async def my_referrals(user: dict = Depends(get_current_user)):
    refs = await db.referrals.find({"referrer_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    return {"referral_code": user.get("referral_code"), "total_referrals": len(refs),
            "successful": len([r for r in refs if r.get("status") == "active"]),
            "history": sorted(refs, key=lambda r: r.get("created_at", ""), reverse=True)}

# ----------------------------- Notifications -----------------------------
@api.get("/notifications")
async def get_notifications(user: dict = Depends(get_current_user)):
    items = await db.notifications.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(300)
    items.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return {"unread": len([n for n in items if not n.get("read")]), "items": items}

@api.post("/notifications/read-all")
async def read_all(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"]}, {"$set": {"read": True}}); return {"ok": True}

@api.post("/notifications/{nid}/read")
async def read_one(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["user_id"]}, {"$set": {"read": True}}); return {"ok": True}

# ----------------------------- Organiser overview + analytics -----------------------------
@api.get("/organiser/overview")
async def organiser_overview(user: dict = Depends(get_current_user)):
    if user["role"] not in ("organiser", "admin"): raise HTTPException(status_code=403, detail="Not allowed")
    events = await db.events.find({"organiser_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    eids = [e["id"] for e in events]
    total_regs = await db.registrations.count_documents({"event_id": {"$in": eids}, "status": {"$ne": "cancelled"}})
    txns = await db.transactions.find({"event_id": {"$in": eids}}, {"_id": 0}).to_list(5000)
    revenue = r2(sum(t.get("event_registration_amount", 0) for t in txns))
    today = datetime.now(timezone.utc).date().isoformat()
    published = [e for e in events if e.get("status") == "published"]
    return {"published": len(published), "drafts": len([e for e in events if e.get("status") == "draft"]),
            "cancelled": len([e for e in events if e.get("status") == "cancelled"]), "total_registrations": total_regs,
            "upcoming": len([e for e in published if (e.get("date") or "") >= today]), "collected_for_events": revenue}

@api.get("/organiser/analytics")
async def organiser_analytics(user: dict = Depends(get_current_user)):
    if user["role"] not in ("organiser", "admin"): raise HTTPException(status_code=403, detail="Not allowed")
    events = await db.events.find({"organiser_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    ev_by_id = {e["id"]: e for e in events}
    eids = list(ev_by_id.keys())
    regs = await db.registrations.find({"event_id": {"$in": eids}}, {"_id": 0}).to_list(5000)
    txns = await db.transactions.find({"event_id": {"$in": eids}}, {"_id": 0}).to_list(5000)
    monthly = defaultdict(int); per_event = defaultdict(int); cats = defaultdict(int); revenue = defaultdict(float)
    for r in regs:
        if r.get("status") == "cancelled": continue
        m = (r.get("created_at") or "")[:7]
        if m: monthly[m] += 1
        ev = ev_by_id.get(r["event_id"])
        if ev:
            per_event[ev["name"]] += 1
            cats[ev.get("category")] += 1
    for t in txns:
        ev = ev_by_id.get(t["event_id"])
        if ev: revenue[ev["name"]] += t.get("event_registration_amount", 0)
    months = sorted(monthly.keys())[-6:]
    top_events = sorted(per_event.items(), key=lambda x: -x[1])[:6]
    return {"monthly_registrations": [{"month": m, "count": monthly[m]} for m in months],
            "registrations_by_event": [{"name": k, "count": v} for k, v in top_events],
            "category_distribution": [{"name": k, "value": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])],
            "revenue_by_event": [{"name": k, "revenue": r2(v)} for k, v in sorted(revenue.items(), key=lambda x: -x[1])[:6]]}

# ----------------------------- AI Discovery Assistant -----------------------------
@api.post("/ai/chat")
async def ai_chat(body: ChatBody, request: Request):
    user = await optional_user(request)
    today = datetime.now(timezone.utc).date().isoformat()
    events = await db.events.find({"status": "published", "date": {"$gte": today}}, {"_id": 0}).to_list(300)
    catalogue = "\n".join(f"- {e['name']} | {e['category']}/{e.get('subcategory','')} | {e['mode']} | {e['location']} | age {e['age_group']} | ₹{e['fee']} | {e.get('date','')} | eligibility: {e.get('eligibility','')}" for e in events[:90])
    profile = ""
    if user:
        profile = f"User: {user.get('name')}, age_group={user.get('age_group')}, class={user.get('student_class')}, location={user.get('location')}, interests={user.get('interests')}."
    system = ("You are EVENZA AI Guide, a friendly assistant for a K-12 & college opportunity discovery platform in India. "
              "Recommend competitions/events ONLY from the catalogue provided. Consider age, class, interests, location, eligibility, mode (Virtual/Physical), date and fee/budget. "
              "Be concise, energetic and specific. Reference exact event names. Emphasise MUNs, quizzes and sports when relevant. "
              f"{profile}\n\nCURRENT CATALOGUE (upcoming):\n{catalogue}")
    reply = ""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"evenza-{user['user_id'] if user else uuid.uuid4().hex}", system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        convo = "".join(f"{m.get('role')}: {m.get('content')}\n" for m in body.history[-6:])
        reply = await chat.send_message(UserMessage(text=(convo + f"user: {body.message}") if convo else body.message))
    except Exception as ex:
        logger.error(f"AI error: {ex}")
        q = body.message.lower()
        matched = [e for e in events if any(w in f"{e['name']} {e['category']} {e.get('subcategory','')} {e['location']} {e['mode']}".lower() for w in q.split() if len(w) > 3)]
        reply = ("Here are some opportunities that match:\n" + "\n".join(f"• {e['name']} — {e['category']}, {e['location']} ({e['mode']}), ₹{e['fee']}" for e in matched[:5])) if matched else "Try exploring Discover with filters for category, location and mode!"
    return {"reply": reply, "suggestions": ["Find MUNs for my age", "Top quiz competitions this month", "Football & sports tournaments near me", "Virtual competitions under ₹300"]}

# ----------------------------- Seed -----------------------------
IMG = {
    "dandiya": "https://images.unsplash.com/photo-1755077012428-cf36fee31c1c?w=1200&q=80",
    "carnival": "https://images.unsplash.com/photo-1544441452-326ff5a947fd?w=1200&q=80",
    "sports": "https://images.unsplash.com/photo-1532444458054-01a7dd3e9fca?w=1200&q=80",
    "market": "https://images.unsplash.com/photo-1784802009305-e856e373ed24?w=1200&q=80",
    "mun": "https://images.unsplash.com/photo-1607037183811-2a54d746cd35?w=1200&q=80",
    "padel": "https://images.unsplash.com/photo-1542144582-1ba00456b5e3?w=1200&q=80",
    "pickleball": "https://images.unsplash.com/photo-1693142518820-78d7a05f1546?w=1200&q=80",
    "anime": "https://images.unsplash.com/photo-1569154076682-4c0466623ec2?w=1200&q=80",
    "film": "https://images.unsplash.com/photo-1632187981988-40f3cbaeef5e?w=1200&q=80",
    "gamejam": "https://images.unsplash.com/photo-1607799279861-4dd421887fb3?w=1200&q=80",
    "comedy": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1200&q=80",
    "quiz": "https://images.unsplash.com/photo-1573894999291-f440466112cc?w=1200&q=80",
    "debate": "https://images.unsplash.com/photo-1633775218380-30c7ab85a5c5?w=1200&q=80",
    "dance": "https://images.unsplash.com/photo-1652111132299-ff1056c87b35?w=1200&q=80",
    "chess": "https://images.unsplash.com/photo-1529699211952-734e80c4d42b?w=1200&q=80",
    "football": "https://images.unsplash.com/photo-1777473408941-52aa95ae95ed?w=1200&q=80",
    "basketball": "https://images.unsplash.com/photo-1563506644863-444710df1e03?w=1200&q=80",
    "painting": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=1200&q=80",
    "science": "https://images.unsplash.com/photo-1707944745899-104a4b12d945?w=1200&q=80",
    "singing": "https://images.unsplash.com/photo-1527261834078-9b37d35a4a32?w=1200&q=80",
    "esports": "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=1200&q=80",
    "startup": "https://images.unsplash.com/photo-1576085898323-218337e3e43c?w=1200&q=80",
    "robotics": "https://images.unsplash.com/photo-1742767069929-0c663150b164?w=1200&q=80",
    "hackathon": "https://images.unsplash.com/photo-1756273343749-63f7d6ea0cda?w=1200&q=80",
    "rifle": "https://images.unsplash.com/photo-1761144530756-47ecd564f8ef?w=1200&q=80",
    "cricket": "https://images.unsplash.com/photo-1512719994953-eabf50895df7?w=1200&q=80",
    "badminton": "https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=1200&q=80",
    "volleyball": "https://images.unsplash.com/photo-1599509055064-8a742910930a?w=1200&q=80",
    "swimming": "https://images.unsplash.com/photo-1530549387789-4c1017266635?w=1200&q=80",
    "tabletennis": "https://images.unsplash.com/photo-1676827613262-5fba25cee5fd?w=1200&q=80",
    "coding": "https://images.unsplash.com/photo-1587620962725-abab7fe55159?w=1200&q=80",
    "writing": "https://images.unsplash.com/photo-1679119790850-161688b0417e?w=1200&q=80",
    "spellbee": "https://images.unsplash.com/photo-1453738773917-9c3eff1db985?w=1200&q=80",
    "photography": "https://images.unsplash.com/photo-1495745966610-2a67f2297e5e?w=1200&q=80",
    "graphic": "https://images.unsplash.com/photo-1626785774573-4b799315345d?w=1200&q=80",
    "cooking": "https://images.unsplash.com/photo-1653233797467-1a528819fd4f?w=1200&q=80",
    "environment": "https://images.unsplash.com/photo-1542601906990-b4d3fb778b09?w=1200&q=80",
    "theatre": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=1200&q=80",
    "podcast": "https://images.unsplash.com/photo-1478737270239-2f02b77fc618?w=1200&q=80",
    "fashion": "https://images.unsplash.com/photo-1557777586-f6682739fcf3?w=1200&q=80",
    "math": "https://images.unsplash.com/photo-1635372722656-389f87a941b7?w=1200&q=80",
    "craft": "https://images.unsplash.com/photo-1609446154807-d56805f0e007?w=1200&q=80",
    "community": "https://images.unsplash.com/photo-1628717341663-0007b0ee2597?w=1200&q=80",
    "reading": "https://images.unsplash.com/photo-1544456203-0af5a69f5789?w=1200&q=80",
}

# genre -> (category, subcategory, image key, mostly virtual?)
GENRES = [
    ("Mathematics Championship", "Academic", "Mathematics", "math", False),
    ("Science Fair & Exhibition", "Academic", "Science", "science", False),
    ("Social Science Symposium", "Academic", "Social Science", "reading", True),
    ("General Knowledge Bowl", "Academic", "General Knowledge", "quiz", True),
    ("Inter-School Quiz Championship", "Academic", "Quiz", "quiz", False),
    ("National Science Olympiad", "Academic", "Olympiads", "science", False),
    ("Spell Bee Championship", "Academic", "Spell Bee", "spellbee", False),
    ("STEM Innovation Challenge", "Academic", "STEM Challenges", "robotics", False),
    ("Interdisciplinary Brain Challenge", "Academic", "Interdisciplinary Challenges", "math", True),
    ("Great Debate Championship", "Communication", "Debate", "debate", False),
    ("Public Speaking Summit", "Communication", "Public Speaking", "debate", True),
    ("Elocution Contest", "Communication", "Elocution", "debate", False),
    ("Extempore Face-off", "Communication", "Extempore", "debate", True),
    ("Storytelling Festival", "Communication", "Storytelling", "reading", False),
    ("Maharashtra Youth MUN", "Communication", "Model United Nations", "mun", False),
    ("Global Virtual MUN Conclave", "Communication", "Model United Nations", "mun", True),
    ("Youth Parliament Session", "Communication", "Youth Parliament", "mun", False),
    ("Creative Writing Contest", "Writing & Literature", "Creative Writing", "writing", True),
    ("National Essay Writing Prize", "Writing & Literature", "Essay Writing", "writing", True),
    ("Short Story Writing Contest", "Writing & Literature", "Story Writing", "writing", True),
    ("Poetry Slam", "Writing & Literature", "Poetry", "writing", False),
    ("Readers' League", "Writing & Literature", "Reading", "reading", True),
    ("Young Journalists Award", "Writing & Literature", "Journalism & Media", "podcast", True),
    ("Code Sprint Championship", "Technology", "Coding & Programming", "coding", True),
    ("RoboWars Championship", "Technology", "Robotics", "robotics", False),
    ("AI Challenge: Build for Bharat", "Technology", "Artificial Intelligence", "robotics", True),
    ("48-Hour AI Hackathon", "Technology", "AI Hackathons", "hackathon", True),
    ("App Development Jam", "Technology", "App Development", "coding", True),
    ("Web Dev Showdown", "Technology", "Web Development", "coding", True),
    ("EVENZA Game Jam", "Technology", "Game Jams", "gamejam", True),
    ("Valorant State Esports Cup", "Technology", "Esports", "esports", True),
    ("Young Innovators Expo", "Technology", "Innovation & Invention", "hackathon", False),
    ("Teen Founders Pitch Fest", "Entrepreneurship & Business", "Startup Pitch", "startup", False),
    ("Business Plan Challenge", "Entrepreneurship & Business", "Business Plan", "startup", True),
    ("FinWiz Finance Olympiad", "Entrepreneurship & Business", "Business & Finance", "startup", True),
    ("Young Entrepreneur Summit", "Entrepreneurship & Business", "Entrepreneurship", "market", False),
    ("Marketing Mavericks", "Entrepreneurship & Business", "Marketing", "startup", True),
    ("Sketching & Drawing Contest", "Arts", "Drawing & Sketching", "painting", False),
    ("Canvas & Colors Painting", "Arts", "Painting", "painting", False),
    ("Young Lens Photography", "Arts", "Photography", "photography", False),
    ("Graphic Design Battle", "Arts", "Graphic Design", "graphic", True),
    ("Digital Art Showcase", "Arts", "Digital Art", "graphic", True),
    ("Craft & DIY Carnival", "Arts", "Craft & DIY", "craft", False),
    ("Anime & Manga Illustration", "Arts", "Anime / Manga / Digital Illustration", "anime", True),
    ("Nrityanjali Dance Festival", "Performing Arts", "Dance", "dance", False),
    ("Battle of Bands", "Performing Arts", "Music", "singing", False),
    ("Sur Sangam Singing Contest", "Performing Arts", "Singing", "singing", False),
    ("Instrumental Music Gala", "Performing Arts", "Instrumental Music", "singing", False),
    ("Rangmanch Theatre Fest", "Performing Arts", "Theatre & Drama", "theatre", False),
    ("Stand-up Comedy Open Mic", "Performing Arts", "Stand-up Comedy", "comedy", False),
    ("Fashion & Styling Showcase", "Performing Arts", "Fashion & Styling", "fashion", False),
    ("Short Film Making Challenge", "Creative Media", "Film & Video Making", "film", False),
    ("60-Second Short Film Fest", "Creative Media", "Short Film", "film", True),
    ("Young Podcasters Award", "Creative Media", "Podcasting", "podcast", True),
    ("Football Premier League", "Sports", "Football", "football", False),
    ("City Cricket Cup", "Sports", "Cricket", "cricket", False),
    ("3x3 Basketball Showdown", "Sports", "Basketball", "basketball", False),
    ("Volleyball State League", "Sports", "Volleyball", "volleyball", False),
    ("Badminton Open", "Sports", "Badminton", "badminton", False),
    ("Athletics Track Meet", "Sports", "Athletics", "sports", False),
    ("Inter-School Swimming Gala", "Sports", "Swimming", "swimming", False),
    ("Table Tennis Championship", "Sports", "Table Tennis", "tabletennis", False),
    ("Kabaddi Mega League", "Sports", "Kabaddi", "sports", False),
    ("State Chess Championship", "Sports", "Chess & Board Games", "chess", False),
    ("Pickleball Schools League", "Sports", "Pickleball", "pickleball", False),
    ("Junior Padel Open", "Sports", "Padel", "padel", False),
    ("State Rifle Shooting Championship", "Sports", "Rifle Shooting", "rifle", False),
    ("MasterChef Junior Cook-off", "Lifestyle & Impact", "Culinary & Cooking", "cooking", False),
    ("Green Earth Sustainability Challenge", "Lifestyle & Impact", "Environmental & Sustainability", "environment", False),
    ("Change-makers Social Impact", "Lifestyle & Impact", "Community & Social Impact", "community", False),
    ("Cultural & Heritage Fiesta", "Lifestyle & Impact", "Cultural & Heritage", "dandiya", False),
    ("EVENZA Got Talent", "Lifestyle & Impact", "Talent & Variety", "carnival", False),
    ("Mental Math & Memory Masters", "Lifestyle & Impact", "Mental Math & Memory", "math", True),
]

FEES = [99, 149, 199, 249, 299, 349, 399, 449, 499, 599, 699, 799, 999, 1199, 1499]
ORGS = ["Bright Minds Academy", "Maharashtra Youth League", "Innovate India", "Talent Sparks", "Champions Club",
        "Future Leaders Forum", "Creative Collective", "Sports Authority Club", "TechEd Society", "Arts & Culture Trust"]

def d(days): return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()

async def seed():
    await get_tax_config()
    async def ensure_user(email, name, role, pw, org=None, interests=None, age=None, location="Mumbai", student_class=None, ref=None):
        u = await db.users.find_one({"email": email})
        if u:
            await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_pw(pw), "role": role}})
            return u["user_id"]
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({"user_id": uid, "email": email, "password_hash": hash_pw(pw), "name": name, "role": role,
                                   "age": age, "age_group": age_to_group(age) if age else None, "student_class": student_class,
                                   "location": location, "interests": interests or [], "organisation": org, "bio": "",
                                   "referral_code": ref or gen_referral(), "referred_by": None, "picture": None, "created_at": now_iso()})
        await notify(uid, "Welcome to EVENZA 👋", "Where opportunities find you.", "info")
        return uid

    admin_id = await ensure_user(os.environ.get("ADMIN_EMAIL", "admin@evenza.in"), "Diya (Owner)", "organiser", os.environ.get("ADMIN_PASSWORD", "admin123"), org="Bal Bharati Public School")
    org_id = await ensure_user("organiser@evenza.in", "Bal Bharati Public School", "organiser", "Organiser@123", org="Bal Bharati Public School")
    await ensure_user("diya@evenza.in", "Diya", "participant", "Diya@123", interests=["Robotics", "Model United Nations", "Football", "Quiz", "Esports"], age=15, location="Mumbai", student_class="10", ref="EVENZA123")

    marker = await db.config.find_one({"key": "seed_version"})
    marker_is_current = marker and marker.get("value") == SEED_VERSION
    event_count = await db.events.count_documents({})
    if marker_is_current and event_count >= MIN_SEEDED_EVENTS:
        return
    # Rebuild an incomplete catalogue without discarding user activity.
    await db.events.delete_many({})
    if not marker_is_current:
        await db.registrations.delete_many({})
        await db.transactions.delete_many({})
        await db.saved.delete_many({})

    def add(store, **k):
        k.setdefault("id", str(uuid.uuid4())); k.setdefault("status", "published"); k.setdefault("created_at", now_iso())
        k.setdefault("time", "10:00 AM"); k.setdefault("contact", "events@evenza.in | +91 98765 43210")
        k.setdefault("capacity", 200); k.setdefault("rules", "Standard EVENZA rules apply. Carry your ID. Judges' decision is final.")
        if k.get("mode") == "Virtual":
            k.setdefault("meeting_link", f"https://meet.evenza.in/{uuid.uuid4().hex[:10]}")
            k.setdefault("meeting_password", "".join(random.choices(string.ascii_uppercase + string.digits, k=6)))
        store.append(k)

    E = []
    # 4 Bal Bharati events (owned) - all paid
    add(E, name="Bal Bharati Public School — Dandiya Night", organiser="Bal Bharati Public School", organiser_id=org_id,
        category="Lifestyle & Impact", subcategory="Cultural & Heritage", mode="Physical", location="Mumbai", age_group="11-15",
        eligibility="Open to all students", fee=150, date=d(12), deadline=d(9), image=IMG["dandiya"], prize="Best Dressed & Best Dancer",
        description="A dazzling festive Dandiya & Garba night celebrating culture and rhythm. Dress in your traditional best!")
    add(E, name="Bal Bharati Public School — Winter Carnival", organiser="Bal Bharati Public School", organiser_id=org_id,
        category="Lifestyle & Impact", subcategory="Talent & Variety", mode="Physical", location="Mumbai", age_group="8-11",
        eligibility="Open to all students", fee=100, date=d(25), deadline=d(20), image=IMG["carnival"], prize="Carnival passes & goodies",
        description="A magical winter carnival with games, food stalls, rides and live entertainment.")
    add(E, name="Bal Bharati Public School — Inter-House Sports Competition", organiser="Bal Bharati Public School", organiser_id=org_id,
        category="Sports", subcategory="Athletics", mode="Physical", location="Mumbai", age_group="11-15",
        eligibility="Open to all houses", fee=99, date=d(18), deadline=d(14), image=IMG["sports"], prize="House Championship Trophy",
        description="The flagship inter-house athletics meet — track events, relays and team spirit.")
    add(E, name="Bal Bharati Public School — Market Day", organiser="Bal Bharati Public School", organiser_id=org_id,
        category="Entrepreneurship & Business", subcategory="Market Day", mode="Physical", location="Mumbai", age_group="15-18",
        eligibility="Commerce Students", fee=200, date=d(30), deadline=d(24), image=IMG["market"], prize="Best Stall & Highest Profit",
        description="Commerce students set up real stalls, pitch products and run mini-businesses for a day.")

    # generate catalogue from genres
    i = 0
    for label, cat, sub, imgk, virtual_pref in GENRES:
        count = 3 if sub in ("Model United Nations", "Quiz", "Football") else 2
        for j in range(count):
            i += 1
            mode = "Virtual" if (virtual_pref and j == 0) or (virtual_pref and count == 3 and j == 2) else ("Virtual" if (not virtual_pref and j == 1 and i % 3 == 0) else "Physical")
            if virtual_pref and count == 2:
                mode = "Virtual" if j == 0 else "Physical"
            city = LOCATIONS[i % len(LOCATIONS)]
            ag = AGE_GROUPS[i % len(AGE_GROUPS)]
            fee = FEES[i % len(FEES)]
            org = ORGS[i % len(ORGS)]
            day = 5 + (i * 3) % 40
            name = label if count == 1 else f"{label} {2026}" if j == 0 else f"{label} — Season {j+1}"
            add(E, name=name, organiser=org, category=cat, subcategory=sub, mode=mode, location=city, age_group=ag,
                eligibility="Open to all" if sub != "Market Day" else "Commerce Students", fee=fee, date=d(day), deadline=d(max(3, day-4)),
                image=IMG.get(imgk, IMG["quiz"]), prize=f"Trophies, medals & prizes worth ₹{fee*20}",
                description=f"Join the {label} — one of Maharashtra's most exciting {sub} competitions. Compete, learn and win recognition. Open to the {ag} age group.")

    for e in E:
        await db.events.insert_one(dict(e))
    await db.config.update_one({"key": "seed_version"}, {"$set": {"key": "seed_version", "value": SEED_VERSION}}, upsert=True)
    logger.info(f"Seeded {len(E)} events.")

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("referral_code")
    await db.events.create_index("id")
    await db.notifications.create_index("user_id")
    await seed()

@app.on_event("shutdown")
async def shutdown():
    client.close()

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
