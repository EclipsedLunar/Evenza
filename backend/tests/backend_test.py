"""EVENZA backend API tests"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://evenza-events-hub.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

PARTICIPANT = {"email": "diya@evenza.in", "password": "Diya@123"}
ORGANISER = {"email": "organiser@evenza.in", "password": "Organiser@123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"], r.json()["user"]


@pytest.fixture(scope="session")
def participant_auth():
    tok, u = _login(PARTICIPANT)
    return {"headers": {"Authorization": f"Bearer {tok}"}, "user": u}


@pytest.fixture(scope="session")
def organiser_auth():
    tok, u = _login(ORGANISER)
    return {"headers": {"Authorization": f"Bearer {tok}"}, "user": u}


# ---------- Health ----------
def test_health():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Auth ----------
def test_login_participant():
    r = requests.post(f"{API}/auth/login", json=PARTICIPANT, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["user"]["role"] == "participant"
    assert j["user"]["referral_code"] == "EVENZA123"
    assert "password_hash" not in j["user"]


def test_login_organiser():
    r = requests.post(f"{API}/auth/login", json=ORGANISER, timeout=30)
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "organiser"


def test_login_invalid():
    r = requests.post(f"{API}/auth/login", json={"email": "diya@evenza.in", "password": "wrong"}, timeout=30)
    assert r.status_code == 401


def test_me(participant_auth):
    r = requests.get(f"{API}/auth/me", headers=participant_auth["headers"], timeout=15)
    assert r.status_code == 200
    assert r.json()["email"] == "diya@evenza.in"


def test_register_new_and_referral():
    email = f"TEST_ref_{uuid.uuid4().hex[:6]}@evenza.in"
    body = {"name": "TestRef", "email": email, "password": "Test@1234", "role": "participant",
            "age": 15, "student_class": "10", "location": "Mumbai",
            "interests": ["Robotics"], "referral_code": "EVENZA123"}
    r = requests.post(f"{API}/auth/register", json=body, timeout=30)
    assert r.status_code == 200
    u = r.json()["user"]
    assert u["age_group"] == "14-16"
    assert u["referred_by"] == "EVENZA123"

    # Diya should see referral
    tok, _ = _login(PARTICIPANT)
    r2 = requests.get(f"{API}/me/referrals", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r2.status_code == 200
    refs = r2.json()
    assert refs["total_referrals"] >= 1
    assert any(x.get("referred_name") == "TestRef" for x in refs["history"])


# ---------- Config ----------
def test_config_endpoints():
    for path in ["categories", "locations", "age-groups", "tax"]:
        r = requests.get(f"{API}/config/{path}", timeout=15)
        assert r.status_code == 200


# ---------- Events / filters ----------
def test_events_list_and_bal_bharati():
    r = requests.get(f"{API}/events", timeout=30)
    assert r.status_code == 200
    events = r.json()
    assert len(events) >= 26, f"expected >=26 got {len(events)}"
    required = ["Dandiya Night", "Winter Carnival", "Inter-House Sports Competition", "Market Day"]
    for name in required:
        assert any(name in e["name"] for e in events), f"missing {name}"
    md = next(e for e in events if "Market Day" in e["name"])
    assert md["eligibility"] == "Commerce Students"
    assert md["fee"] == 200


def test_event_filters():
    r = requests.get(f"{API}/events", params={"mode": "Virtual"}, timeout=15)
    assert r.status_code == 200
    assert all(e["mode"] == "Virtual" for e in r.json())

    r = requests.get(f"{API}/events", params={"free_only": True}, timeout=15)
    assert all(e["fee"] == 0 for e in r.json())

    r = requests.get(f"{API}/events", params={"category": "Sports"}, timeout=15)
    assert all(e["category"] == "Sports" for e in r.json())

    r = requests.get(f"{API}/events", params={"q": "robotics"}, timeout=15)
    assert r.status_code == 200 and len(r.json()) >= 1

    r = requests.get(f"{API}/events", params={"max_fee": 100}, timeout=15)
    assert all(e["fee"] <= 100 for e in r.json())


# ---------- Payment quote math ----------
def test_payment_quote_market_day():
    events = requests.get(f"{API}/events", timeout=15).json()
    md = next(e for e in events if "Market Day" in e["name"])
    r = requests.post(f"{API}/payments/quote", json={"event_id": md["id"]}, timeout=15)
    assert r.status_code == 200
    bd = r.json()
    # sum equals total
    s = round(bd["base_fee"] + bd["platform_charge"] + bd["cgst"] + bd["sgst"] + bd["igst"], 2)
    assert abs(s - bd["total"]) < 0.02, f"sum {s} != total {bd['total']}"
    # market day expected 218.88 (200 + 16 + 1.44 + 1.44)
    assert bd["base_fee"] == 200
    assert abs(bd["total"] - 218.88) < 0.05


def test_payment_quote_free():
    events = requests.get(f"{API}/events", timeout=15).json()
    free = next(e for e in events if e["fee"] == 0)
    r = requests.post(f"{API}/payments/quote", json={"event_id": free["id"]}, timeout=15)
    bd = r.json()
    assert bd["total"] == 0


# ---------- Save + registration ----------
def test_save_and_registrations(participant_auth):
    h = participant_auth["headers"]
    events = requests.get(f"{API}/events", timeout=15).json()
    ev = next(e for e in events if "Dandiya" in e["name"])

    # toggle save on
    r = requests.post(f"{API}/events/{ev['id']}/save", headers=h, timeout=15)
    assert r.status_code == 200
    saved_list = requests.get(f"{API}/me/saved", headers=h, timeout=15).json()
    assert any(e["id"] == ev["id"] for e in saved_list)
    # toggle off (cleanup)
    requests.post(f"{API}/events/{ev['id']}/save", headers=h, timeout=15)


def test_free_event_registration(participant_auth):
    h = participant_auth["headers"]
    events = requests.get(f"{API}/events", timeout=15).json()
    # pick a free event participant not registered for
    my = requests.get(f"{API}/me/registrations", headers=h, timeout=15).json()
    registered_ids = {r["event_id"] for r in my if r["status"] != "cancelled"}
    free = next(e for e in events if e["fee"] == 0 and e["id"] not in registered_ids)
    r = requests.post(f"{API}/registrations", headers=h, json={"event_id": free["id"], "payment_mode": "UPI"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["transaction"]["total_paid"] == 0
    assert j["registration"]["status"] == "confirmed"
    # dup should fail
    r2 = requests.post(f"{API}/registrations", headers=h, json={"event_id": free["id"]}, timeout=15)
    assert r2.status_code == 400


def test_notifications(participant_auth):
    h = participant_auth["headers"]
    r = requests.get(f"{API}/notifications", headers=h, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "unread" in data and "items" in data
    r2 = requests.post(f"{API}/notifications/read-all", headers=h, timeout=15)
    assert r2.status_code == 200
    r3 = requests.get(f"{API}/notifications", headers=h, timeout=15)
    assert r3.json()["unread"] == 0


# ---------- Organiser ----------
def test_organiser_overview_and_events(organiser_auth):
    h = organiser_auth["headers"]
    r = requests.get(f"{API}/organiser/overview", headers=h, timeout=15)
    assert r.status_code == 200
    r2 = requests.get(f"{API}/events/mine", headers=h, timeout=15)
    assert r2.status_code == 200
    names = [e["name"] for e in r2.json()]
    for req in ["Dandiya", "Winter Carnival", "Inter-House Sports", "Market Day"]:
        assert any(req in n for n in names), f"missing {req}"


def test_organiser_create_edit_delete(organiser_auth):
    h = organiser_auth["headers"]
    body = {"name": f"TEST_Event_{uuid.uuid4().hex[:6]}", "category": "Academic", "subcategory": "Quiz",
            "description": "Test event", "age_group": "14-16", "eligibility": "Open", "location": "Mumbai",
            "mode": "Physical", "date": "2026-06-15", "deadline": "2026-06-10", "fee": 100,
            "capacity": 50, "image": ""}
    r = requests.post(f"{API}/events", headers=h, json=body, timeout=15)
    assert r.status_code == 200
    eid = r.json()["id"]

    # edit
    body["name"] = body["name"] + "_Edited"
    body["fee"] = 150
    r2 = requests.put(f"{API}/events/{eid}", headers=h, json=body, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["fee"] == 150
    # ensure no duplicate
    r3 = requests.get(f"{API}/events/mine", headers=h, timeout=15).json()
    assert sum(1 for e in r3 if e["id"] == eid) == 1

    # delete (no registrations)
    r4 = requests.delete(f"{API}/events/{eid}", headers=h, timeout=15)
    assert r4.status_code == 200
    assert r4.json()["action"] == "deleted"


def test_organiser_cancel_preserves_registrations(participant_auth, organiser_auth):
    hp = participant_auth["headers"]
    ho = organiser_auth["headers"]
    body = {"name": f"TEST_Cancel_{uuid.uuid4().hex[:6]}", "category": "Academic", "subcategory": "Quiz",
            "description": "x", "age_group": "14-16", "eligibility": "Open", "location": "Mumbai",
            "mode": "Physical", "date": "2026-06-15", "deadline": "2026-06-10", "fee": 0, "capacity": 50}
    r = requests.post(f"{API}/events", headers=ho, json=body, timeout=15)
    eid = r.json()["id"]
    # register participant
    rr = requests.post(f"{API}/registrations", headers=hp, json={"event_id": eid}, timeout=15)
    assert rr.status_code == 200
    # cancel
    rc = requests.delete(f"{API}/events/{eid}", headers=ho, timeout=15)
    assert rc.status_code == 200
    assert rc.json()["action"] == "cancelled"
    # participant registration preserved with status event_cancelled
    mine = requests.get(f"{API}/me/registrations", headers=hp, timeout=15).json()
    reg = next(r for r in mine if r["event_id"] == eid)
    assert reg["status"] == "event_cancelled"


def test_organiser_remind(participant_auth, organiser_auth):
    hp = participant_auth["headers"]
    ho = organiser_auth["headers"]
    # create event + register
    body = {"name": f"TEST_Remind_{uuid.uuid4().hex[:6]}", "category": "Academic", "subcategory": "Quiz",
            "description": "x", "age_group": "14-16", "eligibility": "Open", "location": "Mumbai",
            "mode": "Physical", "date": "2026-06-15", "deadline": "2026-06-10", "fee": 0, "capacity": 50}
    r = requests.post(f"{API}/events", headers=ho, json=body, timeout=15)
    eid = r.json()["id"]
    rr = requests.post(f"{API}/registrations", headers=hp, json={"event_id": eid}, timeout=15)
    rid = rr.json()["registration"]["id"]
    # get regs as organiser
    regs = requests.get(f"{API}/events/{eid}/registrations", headers=ho, timeout=15)
    assert regs.status_code == 200 and len(regs.json()) >= 1
    # send reminder
    rem = requests.post(f"{API}/events/{eid}/registrations/{rid}/remind", headers=ho, timeout=15)
    assert rem.status_code == 200


def test_tax_config_put(organiser_auth):
    h = organiser_auth["headers"]
    r = requests.get(f"{API}/config/tax", timeout=15)
    cfg = r.json()
    cfg.pop("key", None)
    r2 = requests.put(f"{API}/config/tax", headers=h, json=cfg, timeout=15)
    assert r2.status_code == 200


# ---------- Recommended / Achievements ----------
def test_recommended_achievements(participant_auth):
    h = participant_auth["headers"]
    r = requests.get(f"{API}/me/recommended", headers=h, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r2 = requests.get(f"{API}/me/achievements", headers=h, timeout=15)
    assert r2.status_code == 200
    assert "achievements" in r2.json()


# ---------- AI chat ----------
def test_ai_chat():
    r = requests.post(f"{API}/ai/chat", json={"message": "Show robotics events", "history": []}, timeout=60)
    assert r.status_code == 200
    j = r.json()
    assert "reply" in j and len(j["reply"]) > 0
    assert isinstance(j["suggestions"], list) and len(j["suggestions"]) > 0
