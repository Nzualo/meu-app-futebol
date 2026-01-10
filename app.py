import math
import json
import os
import hashlib
import threading
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st
from openai import OpenAI

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ============================================================
# SECRETS (Streamlit Cloud -> Manage app -> Settings -> Secrets)
# ============================================================
# FOOTBALL_API_MODE = "allsports"
# ALLSPORTS_API_KEY = "SUA_CHAVE_ALLSPORTS"
# OPENAI_API_KEY    = "SUA_CHAVE_OPENAI"   # opcional (IA)
# PREMIUM_CODES = "NZUALO30,NZUALO50,VIP2026"   # opcional (monetização)
# ============================================================

# =============================
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
MAX_LEAGUES_DEFAULT = 20
ALLSPORTS_BASE = "https://apiv2.allsportsapi.com/football/"

TOP_TIPS_MIN_ODD = 1.40
TOP_TIPS_MAX_ODD = 2.00

# FREE limits
FREE_MAX_GENERATES_PER_DAY = 3  # por dia (persistente)
LIMITS_FILE = "free_limits.json"  # persistência leve

st.set_page_config(page_title="Melhores Palpites do Dia", layout="wide")

st.markdown(
    """
<style>
.main { background-color: #0e1117; }
.card { background-color: #1a1c24; padding: 14px; border-radius: 12px;
        border-left: 7px solid #00ff00; color: white; margin-bottom: 10px; }
.muted { color: #aab; font-size: 0.90rem; }
.badge { background-color: #00ff00; color: black; padding: 4px 10px; border-radius: 14px;
         font-weight: 700; display:inline-block; }

.barca-header {
  background: linear-gradient(135deg, #004d98, #a50044);
  border-radius: 16px;
  padding: 16px 18px;
  margin-bottom: 14px;
  border: 1px solid rgba(255,255,255,0.18);
}
.barca-title { display: flex; align-items: center; gap: 14px; }
.barca-title img { width: 52px; height: 52px; }
.barca-title h2 { margin: 0; color: #ffffff; font-size: 1.35rem; font-weight: 900; }
.barca-meta { margin-top: 8px; color: #f1f1f1; font-size: 0.95rem; }
.barca-note { margin-top: 10px; font-size: 0.86rem; color: #ffecec; opacity: 0.95; }
.barca-sign {
  display:inline-block; margin-top: 10px; padding: 6px 12px; border-radius: 18px;
  background: rgba(255,255,255,0.18); font-weight: 900; color: #ffffff;
}
.barca-wa {
  display:inline-block; margin-left: 10px; padding: 6px 14px; border-radius: 18px;
  background: #25D366; color: #000; font-weight: 900; text-decoration: none;
}
.barca-wa:hover { background:#1ebe5d; }

.ptext { color: #cfd8e3; font-size: 0.90rem; margin-top: 6px; }
.ai-box { border-left: 4px solid #ffd166; padding-left: 10px; margin-top: 8px; color: #f3f4f6; }
.small { font-size: 0.88rem; color: #cfd8e3; margin-top: 6px; }

.premium-pill {
  display:inline-block; padding: 5px 10px; border-radius: 16px;
  background: rgba(255,255,255,0.12); color: #fff; font-weight: 900;
}
.free-pill {
  display:inline-block; padding: 5px 10px; border-radius: 16px;
  background: rgba(255,255,255,0.08); color: #fff; font-weight: 900;
}

.kpi {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 10px 12px;
  margin-top: 8px;
}
.kpi b { color:#fff; }
hr { border-color: rgba(255,255,255,0.08); }

.locked {
  opacity: 0.55;
  filter: grayscale(35%);
}
</style>
""",
    unsafe_allow_html=True,
)

# =============================
# Helpers / Secrets / Provider
# =============================
def _get_secret(name: str, default: Optional[str] = None) -> str:
    v = st.secrets.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing secret: {name}")
    return str(v)


def provider_mode() -> str:
    return str(st.secrets.get("FOOTBALL_API_MODE", "allsports")).lower().strip()


def get_premium_codes() -> List[str]:
    raw = str(st.secrets.get("PREMIUM_CODES", "") or "").strip()
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


# =============================
# Feature flags (Premium)
# =============================
def feature_enabled(name: str) -> bool:
    """
    Centraliza o gating de recursos Premium.
    """
    if name in ("AI_EXPLAIN", "AI_RISK", "EXPORT_PDF", "EXPORT_WA", "TOP_TIPS_PRO", "MULTIBET", "HISTORY", "FAVORITES", "PERF_BOOST"):
        return is_premium()
    return True


# =============================
# Monetização: Premium + FREE 3/dia (persistente)
# =============================
@st.cache_resource
def _limits_lock():
    return threading.Lock()


def _today_key_local() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _safe_load_limits() -> Dict:
    if not os.path.exists(LIMITS_FILE):
        return {}
    try:
        with open(LIMITS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _safe_save_limits(data: Dict) -> None:
    try:
        tmp = LIMITS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, LIMITS_FILE)
    except Exception:
        pass


def _fingerprint() -> str:
    ua = ""
    lang = ""
    try:
        headers = getattr(st, "context", None)
        if headers and hasattr(headers, "headers"):
            h = headers.headers
            ua = str(h.get("user-agent", ""))
            lang = str(h.get("accept-language", ""))
    except Exception:
        pass

    seed = (ua + "|" + lang).strip()
    if not seed:
        seed = "sess|" + str(st.session_state.get("_sid_fallback", ""))
        if seed.endswith("|"):
            seed += "x"

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def is_premium() -> bool:
    return bool(st.session_state.get("is_premium", False))


def premium_activate(code: str) -> bool:
    codes = get_premium_codes()
    if not codes:
        return False
    if code.strip() in codes:
        st.session_state["is_premium"] = True
        return True
    return False


def premium_logout():
    st.session_state["is_premium"] = False


def free_used_today() -> int:
    if is_premium():
        return 0
    with _limits_lock():
        data = _safe_load_limits()
        day = _today_key_local()
        fp = _fingerprint()
        return int(data.get(day, {}).get(fp, 0))


def free_remaining_today() -> int:
    if is_premium():
        return 999999
    return max(0, FREE_MAX_GENERATES_PER_DAY - free_used_today())


def free_can_generate() -> bool:
    return is_premium() or (free_used_today() < FREE_MAX_GENERATES_PER_DAY)


def consume_generate_chance() -> None:
    if is_premium():
        return
    with _limits_lock():
        data = _safe_load_limits()
        day = _today_key_local()
        fp = _fingerprint()
        if day not in data:
            data[day] = {}
        cur = int(data[day].get(fp, 0))
        data[day][fp] = cur + 1
        try:
            days_sorted = sorted(data.keys())
            if len(days_sorted) > 10:
                for old in days_sorted[:-10]:
                    data.pop(old, None)
        except Exception:
            pass
        _safe_save_limits(data)


# =============================
# Session history / favorites (Premium)
# =============================
def _ensure_session_lists():
    if "history" not in st.session_state:
        st.session_state["history"] = []  # lista de dicts {ts, tab, picks}
    if "favorites" not in st.session_state:
        st.session_state["favorites"] = []  # lista de picks


def add_to_history(tab_name: str, picks: List[Dict]):
    _ensure_session_lists()
    if not feature_enabled("HISTORY"):
        return
    st.session_state["history"].insert(0, {"ts": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_name, "picks": picks})
    st.session_state["history"] = st.session_state["history"][:20]


def add_to_favorites(pick: Dict):
    _ensure_session_lists()
    if not feature_enabled("FAVORITES"):
        return
    # evita duplicados por fixture + pick
    key = f"{pick.get('fixture_id')}|{pick.get('pick')}"
    existing = {f"{p.get('fixture_id')}|{p.get('pick')}" for p in st.session_state["favorites"]}
    if key not in existing:
        st.session_state["favorites"].insert(0, pick)
        st.session_state["favorites"] = st.session_state["favorites"][:30]


# =============================
# OpenAI
# =============================
@st.cache_resource
def get_openai_client() -> OpenAI:
    key = st.secrets.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Missing secret: OPENAI_API_KEY")
    return OpenAI(api_key=str(key))


def _short(s: str, n: int = 700) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


@st.cache_data(ttl=60 * 60 * 24)
def ai_explain_pick_cached(
    league: str,
    match: str,
    market: str,
    pick_name: str,
    time_str: str,
    prob: float,
    odd: float,
    fair: float,
    edge: Optional[float],
    ev: str,
    lam_h: float,
    lam_a: float,
) -> str:
    client = get_openai_client()
    edge_txt = "n/a" if edge is None else f"{edge*100:.1f}%"

    prompt = f"""
Explique o pick abaixo de forma curta.
Regras: 4–7 linhas, simples, sem inventar dados externos, inclua 1 risco, finalize com confiança em % (<=90).

Jogo: {match}
Liga: {league}
Hora: {time_str}
Mercado: {market}
Pick: {pick_name}

Modelo: Prob={prob:.3f} | Odd={odd:.2f} | Odd justa={fair:.2f} | Edge={edge_txt} | Evidência={ev} | λ={lam_h:.2f}-{lam_a:.2f}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Responda em português e seja conciso e prático."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        return _short(resp.choices[0].message.content or "", 700)
    except Exception:
        return "IA indisponível no momento para este pick."


@st.cache_data(ttl=60 * 60 * 24)
def ai_risk_note_cached(
    league: str,
    match: str,
    market: str,
    pick_name: str,
    time_str: str,
    prob: float,
    odd: float,
    fair: float,
    edge: Optional[float],
    ev: str,
    lam_h: float,
    lam_a: float,
) -> str:
    client = get_openai_client()
    edge_txt = "n/a" if edge is None else f"{edge*100:.1f}%"

    prompt = f"""
Dê um alerta curto sobre quando NÃO apostar neste pick.

Regras:
- 3 a 6 linhas.
- Use APENAS os dados fornecidos.
- Liste 2 a 4 red flags.
- Termine com: "Se ainda apostar: stake baixa."

Pick:
Jogo: {match}
Liga: {league}
Hora: {time_str}
Mercado: {market}
Pick: {pick_name}

Dados do modelo: Prob={prob:.3f} | Odd={odd:.2f} | Odd justa={fair:.2f} | Edge={edge_txt} | Evidência={ev} | λ={lam_h:.2f}-{lam_a:.2f}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Responda em português, direto e prático."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        return _short(resp.choices[0].message.content or "", 700)
    except Exception:
        return "IA indisponível no momento para alertas de risco."


# =============================
# Export Top Tips (PDF + WhatsApp)
# =============================
def top_tips_to_pdf_bytes(
    picks: List[Dict],
    date_str: str,
    location: str = "Inhassoro",
    author: str = "By Nzualo",
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    y = h - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Top Tips do Dia")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Data: {date_str}   |   Local: {location}   |   {author}")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "Nota: Probabilidades estatísticas, sem garantias. Aposte com responsabilidade.")
    y -= 22

    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Hora")
    c.drawString(90, y, "Liga")
    c.drawString(260, y, "Jogo")
    c.drawString(470, y, "Pick (Odd)")
    y -= 12

    c.setLineWidth(0.3)
    c.line(40, y, w - 40, y)
    y -= 14

    c.setFont("Helvetica", 9)

    def _short_local(s: str, n: int) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else s[: n - 3] + "..."

    for p in picks:
        if y < 80:
            c.showPage()
            y = h - 50
            c.setFont("Helvetica", 9)

        time_ = p.get("time", "??:??")
        league = _short_local(p.get("league", ""), 26)
        match = _short_local(p.get("match", ""), 34)
        pick = _short_local(p.get("pick", ""), 26)
        odd = float(p.get("odd") or 0.0)

        c.drawString(40, y, str(time_))
        c.drawString(90, y, str(league))
        c.drawString(260, y, str(match))
        c.drawString(470, y, f"{pick} ({odd:.2f})")
        y -= 14

    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, 50, "WhatsApp: +258867926665")
    c.save()

    buf.seek(0)
    return buf.read()


def top_tips_whatsapp_text(picks: List[Dict], date_str: str) -> str:
    lines = []
    lines.append(f"Top Tips do Dia — {date_str}")
    lines.append("Local: Inhassoro")
    lines.append("")
    for i, p in enumerate(picks, start=1):
        lines.append(
            f"{i}) {p.get('time','??:??')} | {p.get('league','Liga')} | {p.get('match','Jogo')} | {p.get('pick','Pick')} @ {float(p.get('odd') or 0):.2f}"
        )
    lines.append("")
    lines.append("Nota: probabilidades, sem garantias. Aposte com responsabilidade.")
    lines.append("By Nzualo")
    return "\n".join(lines)


# =============================
# AllSportsAPI
# =============================
def allsports_get(met: str, params: Dict[str, str], timeout: int = 15) -> Dict:
    apikey = _get_secret("ALLSPORTS_API_KEY")
    q = {"met": met, "APIkey": apikey}
    q.update(params or {})
    try:
        r = requests.get(ALLSPORTS_BASE, params=q, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {"success": 0, "result": None, "errors": "Non-dict response"}
    except Exception as e:
        return {"success": 0, "result": None, "errors": str(e)}


# =============================
# Normalização
# =============================
def _as_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(str(x))
    except Exception:
        return None


def _parse_allsports_dt_local(ev: Dict) -> Optional[datetime]:
    try:
        d = ev.get("event_date")
        t = ev.get("event_time") or "00:00"
        dt = datetime.fromisoformat(f"{d} {t}")
        return LOCAL_TZ.localize(dt)
    except Exception:
        return None


def _parse_score_pair(s: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    if not s:
        return None, None
    txt = str(s).strip()
    if txt in ("-", "—", "–", ""):
        return None, None
    for sep in [" - ", "-", " : ", ":", "–", "—"]:
        if sep in txt:
            parts = [p.strip() for p in txt.split(sep)]
            if len(parts) >= 2:
                h = _as_int(parts[0])
                a = _as_int(parts[1])
                if h is not None and a is not None:
                    return h, a
    return None, None


def _extract_ft_goals_from_raw(ev: Dict) -> Tuple[Optional[int], Optional[int]]:
    for key in ["event_ft_result", "event_final_result", "event_result", "final_result", "ft_result"]:
        h, a = _parse_score_pair(ev.get(key))
        if h is not None and a is not None:
            return h, a
    return None, None


def _normalize_fixture_allsports(ev: Dict) -> Optional[Dict]:
    try:
        fx_id = _as_int(ev.get("event_key") or ev.get("match_id") or ev.get("event_id"))
        league_id = _as_int(ev.get("league_key"))
        home_id = _as_int(ev.get("home_team_key"))
        away_id = _as_int(ev.get("away_team_key"))
        if not (fx_id and league_id and home_id and away_id):
            return None

        dt_local = _parse_allsports_dt_local(ev)
        iso = dt_local.astimezone(pytz.UTC).isoformat() if dt_local else ""

        status_txt = (ev.get("event_status") or "").lower()
        if "finish" in status_txt:
            short = "FT"
        elif "not" in status_txt and "start" in status_txt:
            short = "NS"
        else:
            short = ev.get("event_status") or "NS"

        gh, ga = _extract_ft_goals_from_raw(ev)

        return {
            "fixture": {"id": fx_id, "date": iso, "status": {"short": short}},
            "league": {"id": league_id, "name": ev.get("league_name") or "Liga"},
            "teams": {
                "home": {"id": home_id, "name": ev.get("event_home_team") or "Home"},
                "away": {"id": away_id, "name": ev.get("event_away_team") or "Away"},
            },
            "goals": {"home": gh, "away": ga},
            "_raw": ev,
        }
    except Exception:
        return None


# =============================
# Data access
# =============================
@st.cache_data(ttl=60 * 10)
def get_fixtures_by_date(date_yyyy_mm_dd: str) -> List[Dict]:
    if provider_mode() != "allsports":
        return []
    data = allsports_get("Fixtures", {"from": date_yyyy_mm_dd, "to": date_yyyy_mm_dd, "timezone": "Africa/Maputo"})
    if str(data.get("success")) != "1":
        return []
    res = data.get("result") or []
    out = []
    for ev in res:
        fx = _normalize_fixture_allsports(ev)
        if fx:
            out.append(fx)
    return out


@st.cache_data(ttl=60 * 60 * 2)
def get_last_team_fixtures(team_id: int, last: int = 10, status: str = "FT") -> List[Dict]:
    if provider_mode() != "allsports":
        return []
    today = datetime.now(LOCAL_TZ).date()
    start = today - timedelta(days=160)

    data = allsports_get(
        "Fixtures",
        {"teamId": str(team_id), "from": start.strftime("%Y-%m-%d"), "to": today.strftime("%Y-%m-%d"), "timezone": "Africa/Maputo"},
    )
    if str(data.get("success")) != "1":
        return []

    res = data.get("result") or []
    norm: List[Dict] = []
    for ev in res:
        fx = _normalize_fixture_allsports(ev)
        if not fx:
            continue
        st_short = (fx.get("fixture", {}).get("status", {}) or {}).get("short", "")
        if status == "FT" and st_short != "FT":
            continue
        if fx.get("goals", {}).get("home") is None or fx.get("goals", {}).get("away") is None:
            continue
        norm.append(fx)

    def _dt_key(x):
        dt = parse_fixture_time_local(x)
        return dt.timestamp() if dt else 0.0

    norm.sort(key=_dt_key, reverse=True)
    return norm[:last]


@st.cache_data(ttl=60 * 10)
def get_odds_for_fixture(fixture_id: int) -> Dict:
    if provider_mode() != "allsports":
        return {}
    data = allsports_get("Odds", {"matchId": str(fixture_id)})
    if str(data.get("success")) != "1":
        return {}
    result = data.get("result") or {}
    row_list = result.get(str(fixture_id)) if isinstance(result, dict) else None
    if not row_list:
        return {}
    return row_list[0] if isinstance(row_list, list) and row_list else {}


# =============================
# Time parsing
# =============================
def parse_fixture_time_local(fx: Dict) -> Optional[datetime]:
    try:
        iso = fx["fixture"]["date"]
        if not iso:
            return None
        dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt_utc.astimezone(LOCAL_TZ)
    except Exception:
        return None


def is_future_fixture(fx: Dict, now_local: datetime) -> bool:
    dt = parse_fixture_time_local(fx)
    return bool(dt and dt > now_local)


# =============================
# Poisson model helpers
# =============================
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def prob_over_total(lam_home: float, lam_away: float, line: float, max_goals: int = 10) -> float:
    threshold = math.floor(line)
    p_le = 0.0
    for gh in range(max_goals + 1):
        ph = poisson_pmf(gh, lam_home)
        for ga in range(max_goals + 1):
            pa = poisson_pmf(ga, lam_away)
            if gh + ga <= threshold:
                p_le += ph * pa
    return max(0.0, min(1.0, 1.0 - p_le))


def prob_btts(lam_home: float, lam_away: float) -> float:
    p_home0 = poisson_pmf(0, lam_home)
    p_away0 = poisson_pmf(0, lam_away)
    return max(0.0, min(1.0, 1.0 - p_home0 - p_away0 + (p_home0 * p_away0)))


def prob_1x2(lam_home: float, lam_away: float, max_goals: int = 10) -> Tuple[float, float, float]:
    pH = pD = pA = 0.0
    for gh in range(max_goals + 1):
        ph = poisson_pmf(gh, lam_home)
        for ga in range(max_goals + 1):
            pa = poisson_pmf(ga, lam_away)
            if gh > ga:
                pH += ph * pa
            elif gh == ga:
                pD += ph * pa
            else:
                pA += ph * pa
    s = pH + pD + pA
    if s > 0:
        pH, pD, pA = pH / s, pD / s, pA / s
    return pH, pD, pA


def fair_odds(p: float) -> Optional[float]:
    if p <= 0:
        return None
    return 1.0 / p


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# =============================
# Forma ponderada
# =============================
def compute_team_form_weighted(team_id: int, fixtures_ft: List[Dict], decay: float = 0.85) -> Tuple[int, float, float, float, float, float, float]:
    w_sum = 0.0
    gf_w = ga_w = 0.0

    w_sum_home = 0.0
    gf_home_w = ga_home_w = 0.0

    w_sum_away = 0.0
    gf_away_w = ga_away_w = 0.0

    n = 0
    for i, fx in enumerate(fixtures_ft):
        try:
            home_id = int(fx["teams"]["home"]["id"])
            away_id = int(fx["teams"]["away"]["id"])
            gh = fx.get("goals", {}).get("home")
            ga = fx.get("goals", {}).get("away")
            if gh is None or ga is None:
                continue

            w = decay**i

            if team_id == home_id:
                _gf, _ga = int(gh), int(ga)
                gf_home_w += w * _gf
                ga_home_w += w * _ga
                w_sum_home += w
            elif team_id == away_id:
                _gf, _ga = int(ga), int(gh)
                gf_away_w += w * _gf
                ga_away_w += w * _ga
                w_sum_away += w
            else:
                continue

            gf_w += w * _gf
            ga_w += w * _ga
            w_sum += w
            n += 1
        except Exception:
            continue

    if n == 0 or w_sum <= 0:
        return 0, 0.0, 0.0, -1.0, -1.0, -1.0, -1.0

    gf_pg = gf_w / w_sum
    ga_pg = ga_w / w_sum

    gf_home_pg = (gf_home_w / w_sum_home) if w_sum_home > 0 else -1.0
    ga_home_pg = (ga_home_w / w_sum_home) if w_sum_home > 0 else -1.0

    gf_away_pg = (gf_away_w / w_sum_away) if w_sum_away > 0 else -1.0
    ga_away_pg = (ga_away_w / w_sum_away) if w_sum_away > 0 else -1.0

    return n, gf_pg, ga_pg, gf_home_pg, ga_home_pg, gf_away_pg, ga_away_pg


def estimate_lambdas(home_form, away_form, home_adv: float = 1.08) -> Tuple[float, float, str]:
    base = 1.25
    nH, gfH, gaH, gfH_home, gaH_home, gfH_away, gaH_away = home_form
    nA, gfA, gaA, gfA_home, gaA_home, gfA_away, gaA_away = away_form

    home_attack = gfH_home if gfH_home >= 0 else gfH
    home_def = gaH_home if gaH_home >= 0 else gaH
    away_attack = gfA_away if gfA_away >= 0 else gfA
    away_def = gaA_away if gaA_away >= 0 else gaA

    lam_home_raw = (home_attack + away_def) / 2.0
    lam_away_raw = (away_attack + home_def) / 2.0

    lam_home_raw *= home_adv
    lam_away_raw *= (2.0 - home_adv)

    n_eff = min(nH, nA)
    w = clamp(n_eff / 10.0, 0.25, 1.0)
    lam_home = w * lam_home_raw + (1 - w) * base
    lam_away = w * lam_away_raw + (1 - w) * base

    if n_eff >= 8:
        ev = "ALTA"
    elif n_eff >= 4:
        ev = "MÉDIA"
    else:
        ev = "BAIXA"

    return clamp(lam_home, 0.2, 3.5), clamp(lam_away, 0.2, 3.5), ev


# =============================
# Odds mapping
# =============================
def odds_allsports_market(odds_row: Dict, key: str) -> Optional[float]:
    if not odds_row:
        return None
    v = odds_row.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


# =============================
# League limiting
# =============================
def limit_to_top_leagues(fixtures: List[Dict], max_leagues: int) -> List[Dict]:
    league_counts: Dict[int, int] = {}
    for fx in fixtures:
        lid = fx.get("league", {}).get("id")
        if lid is None:
            continue
        league_counts[int(lid)] = league_counts.get(int(lid), 0) + 1

    top_ids = [lid for lid, _ in sorted(league_counts.items(), key=lambda x: x[1], reverse=True)[:max_leagues]]
    top_set = set(top_ids)
    return [fx for fx in fixtures if int(fx.get("league", {}).get("id", -1)) in top_set]


# =============================
# Picks per market
# =============================
def build_picks_for_market(
    fixtures: List[Dict],
    market: str,
    last_n_form: int,
    home_adv: float,
    one_per_league: bool,
    min_odd: float,
    zebra_min_odd: float,
    max_picks: int,
    progress_cb=None,
) -> List[Dict]:
    picks: List[Dict] = []
    used_leagues = set()
    total = max(1, len(fixtures))

    for idx, fx in enumerate(fixtures, start=1):
        if progress_cb:
            progress_cb(idx, total)

        try:
            fixture_id = int(fx["fixture"]["id"])
            league_id = int(fx["league"]["id"])
            league_name = fx["league"]["name"]
            home = fx["teams"]["home"]
            away = fx["teams"]["away"]
            home_id, away_id = int(home["id"]), int(away["id"])

            if one_per_league and league_id in used_leagues:
                continue

            home_last = get_last_team_fixtures(home_id, last=last_n_form, status="FT")
            away_last = get_last_team_fixtures(away_id, last=last_n_form, status="FT")

            home_form = compute_team_form_weighted(home_id, home_last, decay=0.85)
            away_form = compute_team_form_weighted(away_id, away_last, decay=0.85)

            lam_h, lam_a, ev = estimate_lambdas(home_form, away_form, home_adv=home_adv)
            odds_row = get_odds_for_fixture(fixture_id)

            dt_local = parse_fixture_time_local(fx)
            time_str = dt_local.strftime("%H:%M") if dt_local else "??:??"
            match_name = f"{home['name']} vs {away['name']}"

            def push(pick_name: str, prob: float, odd: float):
                fo = fair_odds(prob) or 0.0
                edge = (odd / fo) - 1.0 if fo > 0 else None
                picks.append(
                    {
                        "league_id": league_id,
                        "league": league_name,
                        "time": time_str,
                        "match": match_name,
                        "pick": pick_name,
                        "prob": prob,
                        "odd": odd,
                        "fair": fo,
                        "edge": edge,
                        "ev": ev,
                        "lam": (lam_h, lam_a),
                        "fixture_id": fixture_id,
                        "market": market,
                    }
                )
                used_leagues.add(league_id)

            if market == "Over 1.5":
                p = prob_over_total(lam_h, lam_a, 1.5)
                odd = odds_allsports_market(odds_row, "o+1.5")
                if odd and odd >= min_odd:
                    push("Over 1.5", p, odd)

            elif market == "Over 2.5":
                p = prob_over_total(lam_h, lam_a, 2.5)
                odd = odds_allsports_market(odds_row, "o+2.5")
                if odd and odd >= min_odd:
                    push("Over 2.5", p, odd)

            elif market == "BTTS":
                p = prob_btts(lam_h, lam_a)
                odd = odds_allsports_market(odds_row, "bts_yes")
                if odd and odd >= min_odd:
                    push("BTTS (Yes)", p, odd)

            elif market == "1X2":
                pH, pD, pA = prob_1x2(lam_h, lam_a)
                odd_home = odds_allsports_market(odds_row, "odd_1")
                odd_draw = odds_allsports_market(odds_row, "odd_x")
                odd_away = odds_allsports_market(odds_row, "odd_2")

                candidates = []
                if odd_home and odd_home >= min_odd:
                    candidates.append(("Home", pH, odd_home))
                if odd_draw and odd_draw >= min_odd:
                    candidates.append(("Draw", pD, odd_draw))
                if odd_away and odd_away >= min_odd:
                    candidates.append(("Away", pA, odd_away))

                best = None
                best_edge = -999
                for name, p, o in candidates:
                    fo = fair_odds(p) or 0.0
                    if fo <= 0:
                        continue
                    e = (o / fo) - 1.0
                    if e > best_edge:
                        best_edge = e
                        best = (name, p, o)

                if best:
                    name, p, o = best
                    push(f"1X2: {name}", p, o)

            elif market in ("DC+Over1.5", "DC+Over2.5"):
                line = 1.5 if market == "DC+Over1.5" else 2.5
                p_over = prob_over_total(lam_h, lam_a, line)
                odd_over = odds_allsports_market(odds_row, "o+1.5" if line == 1.5 else "o+2.5")
                if not odd_over or odd_over < min_odd:
                    continue

                pH, pD, pA = prob_1x2(lam_h, lam_a)
                p_1x, p_x2, p_12 = pH + pD, pA + pD, pH + pA

                odd_1x = odds_allsports_market(odds_row, "odd_1x")
                odd_x2 = odds_allsports_market(odds_row, "odd_x2")
                odd_12 = odds_allsports_market(odds_row, "odd_12")

                for dc_name, p_dc, odd_dc in [("1X", p_1x, odd_1x), ("X2", p_x2, odd_x2 distributions), ("12", p_12, odd_12)]:
                    if not odd_dc or odd_dc < min_odd:
                        continue
                    p_combo = clamp(p_dc * p_over, 0.0, 1.0)
                    odd_proxy = odd_dc * odd_over
                    if odd_proxy >= min_odd:
                        push(f"{dc_name} + Over {line} (odd proxy)", p_combo, odd_proxy)

            elif market == "Zebras":
                pH, pD, pA = prob_1x2(lam_h, lam_a)
                odd_home = odds_allsports_market(odds_row, "odd_1")
                odd_draw = odds_allsports_market(odds_row, "odd_x")
                odd_away = odds_allsports_market(odds_row, "odd_2")

                zebra_candidates = []
                if odd_home and odd_home >= zebra_min_odd:
                    zebra_candidates.append(("Home", pH, odd_home))
                if odd_away and odd_away >= zebra_min_odd:
                    zebra_candidates.append(("Away", pA, odd_away))
                if odd_draw and odd_draw >= zebra_min_odd:
                    zebra_candidates.append(("Draw", pD, odd_draw))

                best = None
                best_edge = -999
                for name, p, o in zebra_candidates:
                    fo = fair_odds(p) or 0.0
                    if fo <= 0:
                        continue
                    e = (o / fo) - 1.0
                    if e > best_edge:
                        best_edge = e
                        best = (name, p, o)

                if best:
                    name, p, o = best
                    push(f"Zebra: {name}", p, o)

        except Exception:
            continue

    picks = sorted(
        picks,
        key=lambda x: (-999 if x.get("edge") is None else -x["edge"], -x.get("prob", 0.0)),
    )[:max_picks]
    return picks


# =============================
# TOP TIPS (PRO scoring)
# =============================
def build_top_tips(
    fixtures: List[Dict],
    last_n_form: int,
    home_adv: float,
    min_odd: float,
    zebra_min_odd: float,
    top_n: int,
    tips_min_odd: float,
    tips_max_odd: float,
    pro_mode: bool,
) -> List[Dict]:
    markets = ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5"]

    pbar = st.progress(0)
    ptxt = st.empty()
    all_candidates: List[Dict] = []

    for i, m in enumerate(markets, start=1):
        pbar.progress(int((i - 1) * 100 / len(markets)))
        ptxt.markdown(f"<div class='ptext'>A gerar candidatos: {m} ({i}/{len(markets)})...</div>", unsafe_allow_html=True)

        cand = build_picks_for_market(
            fixtures=fixtures,
            market=m,
            last_n_form=last_n_form,
            home_adv=home_adv,
            one_per_league=False,
            min_odd=min_odd,
            zebra_min_odd=zebra_min_odd,
            max_picks=60 if pro_mode else 50,
            progress_cb=None,
        )
        all_candidates.extend(cand)

    pbar.progress(100)
    ptxt.markdown("<div class='ptext'>A filtrar odds e selecionar Top Tips...</div>", unsafe_allow_html=True)

    all_candidates = [
        p for p in all_candidates
        if (p.get("odd") is not None) and (tips_min_odd <= float(p["odd"]) <= tips_max_odd)
    ]

    def ev_w(ev: str) -> float:
        ev = (ev or "").upper().strip()
        if ev == "ALTA":
            return 1.0
        if ev == "MÉDIA":
            return 0.6
        return 0.25

    def score_free(p: Dict) -> float:
        edge = float(p.get("edge") or 0.0)
        prob = float(p.get("prob") or 0.0)
        return (1.8 * edge) + (0.9 * prob) + (0.5 * ev_w(p.get("ev", "BAIXA")))

    def score_pro(p: Dict) -> float:
        # PRO: penaliza odds altas dentro do intervalo, e premia "evidência"
        edge = float(p.get("edge") or 0.0)
        prob = float(p.get("prob") or 0.0)
        odd = float(p.get("odd") or 0.0)
        ev = ev_w(p.get("ev", "BAIXA"))
        # Preferir odds mais baixas (mais seguras) dentro do range
        odd_penalty = clamp((odd - tips_min_odd) / max(0.01, (tips_max_odd - tips_min_odd)), 0.0, 1.0)
        return (2.1 * edge) + (1.1 * prob) + (0.8 * ev) - (0.35 * odd_penalty)

    all_candidates = sorted(all_candidates, key=(score_pro if pro_mode else score_free), reverse=True)

    final: List[Dict] = []
    used_leagues = set()
    used_fixtures = set()
    for c in all_candidates:
        lid = c.get("league_id")
        fid = c.get("fixture_id")
        if lid in used_leagues:
            continue
        if fid in used_fixtures:
            continue
        final.append(c)
        used_leagues.add(lid)
        used_fixtures.add(fid)
        if len(final) >= top_n:
            break

    ptxt.markdown("<div class='ptext'>Concluído.</div>", unsafe_allow_html=True)
    return final


# =============================
# Premium: Multi-bet Builder
# =============================
def build_multibet(
    picks: List[Dict],
    min_legs: int,
    max_legs: int,
    target_min_odds: float,
    target_max_odds: float,
) -> List[Dict]:
    """
    Usa os Top Tips já gerados e propõe combinações 2–4 picks.
    Regra: não repetir mesma fixture.
    """
    if not picks:
        return []

    # ordena por qualidade (edge, prob)
    picks_sorted = sorted(picks, key=lambda x: ((x.get("edge") or -999), (x.get("prob") or 0.0)), reverse=True)

    combos = []
    # geração simples (rápida)
    for legs in range(min_legs, max_legs + 1):
        # pega os melhores N e faz combinações lineares (sem explodir)
        pool = picks_sorted[: min(20, len(picks_sorted))]
        n = len(pool)

        def ok_unique_fixture(combo):
            fids = [c.get("fixture_id") for c in combo]
            return len(fids) == len(set(fids))

        # combinações "greedy": pega base e tenta completar
        for i in range(n):
            combo = [pool[i]]
            for j in range(n):
                if j == i:
                    continue
                if len(combo) >= legs:
                    break
                candidate = pool[j]
                if candidate.get("fixture_id") in {c.get("fixture_id") for c in combo}:
                    continue
                combo.append(candidate)

            if len(combo) != legs:
                continue
            if not ok_unique_fixture(combo):
                continue

            total_odds = 1.0
            avg_prob = 0.0
            for c in combo:
                total_odds *= float(c.get("odd") or 1.0)
                avg_prob += float(c.get("prob") or 0.0)
            avg_prob /= legs

            if target_min_odds <= total_odds <= target_max_odds:
                combos.append(
                    {
                        "legs": legs,
                        "total_odds": total_odds,
                        "avg_prob": avg_prob,
                        "items": combo,
                    }
                )

    combos = sorted(combos, key=lambda x: (x["avg_prob"], -x["total_odds"]), reverse=True)
    return combos[:10]


# =============================
# Render
# =============================
def render_picks(picks: List[Dict], ai_enabled: bool, ai_risk_enabled: bool, ai_max: int, allow_fav: bool):
    if not picks:
        st.info("Sem picks que passem nos filtros (ou odds indisponíveis).")
        return

    ai_count = 0
    for idx, p in enumerate(picks, start=1):
        edge = p.get("edge")
        edge_txt = f"{edge*100:.1f}%" if edge is not None else "n/a"

        st.markdown(
            f"""
<div class="card">
  <div><span class="badge">{p['time']}</span> <b>{p['league']}</b></div>
  <div style="margin-top:6px;"><b>{p['match']}</b></div>
  <div style="margin-top:6px;">
    Pick: <b>{p['pick']}</b><br/>
    Prob(modelo): <b>{p['prob']:.3f}</b> | Odd: <b>{p['odd']:.2f}</b> | Odd justa: <b>{p['fair']:.2f}</b> | Edge: <b>{edge_txt}</b><br/>
    Evidência: <b>{p['ev']}</b> | λ: {p['lam'][0]:.2f}-{p['lam'][1]:.2f}
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        if allow_fav:
            if st.button("⭐ Guardar nos Favoritos", key=f"fav_{p.get('fixture_id')}_{idx}"):
                add_to_favorites(p)
                st.success("Guardado.")

        if ai_enabled:
            if ai_count < ai_max:
                with st.expander("🧠 IA: Por que este pick? (explicação curta)"):
                    with st.spinner("A gerar explicação da IA..."):
                        txt = ai_explain_pick_cached(
                            league=p["league"],
                            match=p["match"],
                            market=p.get("market", ""),
                            pick_name=p["pick"],
                            time_str=p["time"],
                            prob=float(p["prob"]),
                            odd=float(p["odd"]),
                            fair=float(p["fair"]),
                            edge=p.get("edge"),
                            ev=p.get("ev", ""),
                            lam_h=float(p["lam"][0]),
                            lam_a=float(p["lam"][1]),
                        )
                    st.markdown(f"<div class='ai-box'>{txt}</div>", unsafe_allow_html=True)
                ai_count += 1
            else:
                st.markdown("<div class='small'>IA: limite de explicações/alertas desta aba atingido.</div>", unsafe_allow_html=True)

            if ai_risk_enabled:
                if ai_count < ai_max:
                    with st.expander("🛑 IA: Quando NÃO apostar (alerta de risco)"):
                        with st.spinner("A gerar alertas de risco..."):
                            risk = ai_risk_note_cached(
                                league=p["league"],
                                match=p["match"],
                                market=p.get("market", ""),
                                pick_name=p["pick"],
                                time_str=p["time"],
                                prob=float(p["prob"]),
                                odd=float(p["odd"]),
                                fair=float(p["fair"]),
                                edge=p.get("edge"),
                                ev=p.get("ev", ""),
                                lam_h=float(p["lam"][0]),
                                lam_a=float(p["lam"][1]),
                            )
                        st.markdown(f"<div class='ai-box'>{risk}</div>", unsafe_allow_html=True)
                    ai_count += 1
                else:
                    st.markdown("<div class='small'>IA: limite de explicações/alertas desta aba atingido.</div>", unsafe_allow_html=True)


# =============================
# MAIN
# =============================
def main():
    now_local = datetime.now(LOCAL_TZ)

    if "is_premium" not in st.session_state:
        st.session_state["is_premium"] = False
    if "_sid_fallback" not in st.session_state:
        st.session_state["_sid_fallback"] = hashlib.md5(str(datetime.utcnow().timestamp()).encode()).hexdigest()[:10]

    _ensure_session_lists()

    st.markdown(
        f"""
<div class="barca-header">
  <div class="barca-title">
    <img src="https://upload.wikimedia.org/wikipedia/en/4/47/FC_Barcelona_%28crest%29.svg" alt="FC Barcelona">
    <h2>Melhores Palpites e Possível Zebras do Dia</h2>
  </div>

  <div class="barca-meta">
    <b>Local:</b> Inhassoro &nbsp; | &nbsp; <b>Hora:</b> {now_local.strftime('%H:%M:%S')}
  </div>

  <div class="barca-note">
    Nota: São apenas probabilidades estatísticas; não há garantias. Aposte com responsabilidade e por sua conta e risco.
  </div>

  <div>
    <span class="barca-sign">By Nzualo</span>
    <a class="barca-wa" href="https://wa.me/258867926665?text=Quero%20ativar%20o%20Premium%20do%20app%20de%20palpites.%20Como%20fa%C3%A7o%3F"
       target="_blank" rel="noopener noreferrer">WhatsApp</a>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # ---------------- Sidebar
    with st.sidebar:
        st.subheader("Acesso")

        if is_premium():
            st.markdown("<span class='premium-pill'>Modo: PREMIUM</span>", unsafe_allow_html=True)
            if st.button("Sair do Premium"):
                premium_logout()
                st.success("Premium desativado nesta sessão.")
        else:
            st.markdown("<span class='free-pill'>Modo: FREE</span>", unsafe_allow_html=True)

        codes = get_premium_codes()
        if codes:
            code = st.text_input("Código Premium", type="password", placeholder="Ex: NZUALO30")
            if st.button("Ativar Premium"):
                if premium_activate(code or ""):
                    st.success("Premium ativado.")
                else:
                    st.error("Código inválido.")
        else:
            st.info("Premium ainda não configurado (adicione PREMIUM_CODES nos Secrets).")

        st.markdown("---")

        if not is_premium():
            rem = free_remaining_today()
            st.warning(f"FREE: {rem} de {FREE_MAX_GENERATES_PER_DAY} gerações restantes hoje.")
            st.caption("Ao virar o dia (hora de Moçambique), renova automaticamente.")
        else:
            st.success("Premium: gerações ilimitadas + recursos PRO.")

        st.subheader("Configuração")
        auto_tomorrow_if_empty = st.checkbox("Se hoje não tiver jogos futuros, usar amanhã", value=True)
        pool_size = st.slider("Pool de jogos para análise", 50, 150, 100, 10)

        top_tips_n = st.slider("Top Tips (6–10)", 6, 10, 8, 1)
        tips_min_odd = st.number_input("Top Tips - odd mínima", value=float(TOP_TIPS_MIN_ODD), min_value=1.01, step=0.01)
        tips_max_odd = st.number_input("Top Tips - odd máxima", value=float(TOP_TIPS_MAX_ODD), min_value=1.01, step=0.01)

        max_picks = st.slider("Top picks por aba", 5, 20, 10, 1)
        one_per_league = st.checkbox("1 pick por liga", value=True)
        max_leagues = st.slider("Máx. ligas/campeonatos", 5, 30, MAX_LEAGUES_DEFAULT, 1)

        last_n_form = st.slider("Forma (últimos jogos FT)", 4, 20, 10, 1)
        home_adv = st.slider("Vantagem de casa", 1.00, 1.20, 1.08, 0.01)

        min_odd = st.number_input("Odd mínima (normais)", value=1.30, min_value=1.01, step=0.01)
        zebra_min_odd = st.number_input("Odd mínima (zebras)", value=4.00, min_value=2.00, step=0.10)

        st.divider()
        st.subheader("Recursos Premium")

        # Top Tips PRO
        pro_tips = st.checkbox("⭐ Top Tips PRO (ranking melhor)", value=True, disabled=not is_premium())
        if not is_premium():
            st.caption("Top Tips PRO: apenas Premium.")

        # Multi-bet
        multibet_on = st.checkbox("🎯 Multi-bet Builder (2–4 legs)", value=True, disabled=not is_premium())
        if not is_premium():
            st.caption("Multi-bet: apenas Premium.")

        st.divider()
        st.subheader("IA (Premium)")
        ai_enabled = st.checkbox("Ativar IA para explicar picks", value=True, disabled=not is_premium())
        ai_risk_enabled = st.checkbox("IA: Alertas de risco (quando NÃO apostar)", value=True, disabled=not is_premium())

        # Boost de performance Premium (mais IA por aba)
        if is_premium():
            ai_max = st.slider("Máx. explicações/alertas por aba", 2, 16, 8, 1)
        else:
            ai_max = 0

        ai_ok = True
        if (ai_enabled or ai_risk_enabled) and not st.secrets.get("OPENAI_API_KEY"):
            ai_ok = False
            st.warning("IA ativada, mas falta OPENAI_API_KEY nos Secrets.")

        debug = st.checkbox("Mostrar diagnóstico (debug)", value=False)

        st.markdown("---")
        if is_premium():
            st.markdown("<div class='kpi'><b>Premium ativo</b><br/>Top Tips PRO • IA • Export • Multi-bet • Histórico/Favoritos</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='kpi'><b>FREE</b><br/>3 gerações/dia • Sem IA • Sem export • Sem Multi-bet</div>", unsafe_allow_html=True)

    # ---------------- Fixtures
    date_to_use = now_local.date()
    date_str = date_to_use.strftime("%Y-%m-%d")
    fixtures_raw = get_fixtures_by_date(date_str)
    fixtures = [fx for fx in fixtures_raw if is_future_fixture(fx, now_local)]

    if auto_tomorrow_if_empty and (len(fixtures_raw) > 0) and (len(fixtures) == 0):
        date_to_use = (now_local + timedelta(days=1)).date()
        date_str = date_to_use.strftime("%Y-%m-%d")
        fixtures_raw = get_fixtures_by_date(date_str)
        fixtures = [fx for fx in fixtures_raw if parse_fixture_time_local(fx) is not None]

    if not fixtures:
        st.error("Nenhum jogo encontrado (ou odds indisponíveis).")
        return

    fixtures = limit_to_top_leagues(fixtures, max_leagues=max_leagues)
    fixtures = sorted(fixtures, key=lambda fx: parse_fixture_time_local(fx) or datetime.max)
    fixtures = fixtures[:pool_size]

    if debug:
        with st.expander("Diagnóstico (fixtures/tempo)"):
            st.write("Provider:", provider_mode())
            st.write("Data usada:", date_str)
            st.write("Agora (local):", now_local.isoformat())
            st.write("Fixtures brutos:", len(fixtures_raw))
            st.write("Pool final:", len(fixtures))

    st.markdown(f"🗓️ Data analisada: <span class='badge'>{date_to_use.strftime('%d/%m/%Y')}</span>", unsafe_allow_html=True)
    st.caption(f"Pool final: {len(fixtures)} jogos | Máx. ligas: {max_leagues}")

    tabs = st.tabs(["⭐ Top Tips", "🎯 Multi-bet", "📌 Favoritos", "🕘 Histórico", "🏆 1X2", "⚽ BTTS", "📈 Over 1.5", "📈 Over 2.5", "👥 DC+O1.5", "👥 DC+O2.5", "🟣 Zebras"])

    # ---------------- Top Tips
    with tabs[0]:
        st.subheader("⭐ Top Tips do Dia (odds moderadas)")
        st.caption(f"Filtro: odds entre {tips_min_odd:.2f} e {tips_max_odd:.2f}")

        disabled = not free_can_generate()
        if st.button(f"🚀 Gerar Top Tips ({top_tips_n})", key="btn_toptips", disabled=disabled):
            consume_generate_chance()
            tips = build_top_tips(
                fixtures=fixtures,
                last_n_form=last_n_form,
                home_adv=home_adv,
                min_odd=min_odd,
                zebra_min_odd=zebra_min_odd,
                top_n=top_tips_n,
                tips_min_odd=float(tips_min_odd),
                tips_max_odd=float(tips_max_odd),
                pro_mode=(is_premium() and pro_tips),
            )
            st.session_state["toptips"] = tips
            add_to_history("Top Tips", tips)

        if disabled and not is_premium():
            st.warning("Limite FREE diário atingido (3 gerações hoje). Ative Premium para ilimitado.")

        tips_list = st.session_state.get("toptips", [])

        # Export (Premium)
        if tips_list:
            st.markdown("### 📤 Exportar Top Tips")
            if not is_premium():
                st.info("Export é recurso Premium.")
            else:
                colA, colB = st.columns([1, 1])
                with colA:
                    pdf_bytes = top_tips_to_pdf_bytes(
                        picks=tips_list,
                        date_str=date_to_use.strftime("%d/%m/%Y"),
                        location="Inhassoro",
                        author="By Nzualo",
                    )
                    st.download_button(
                        label="📄 Baixar Top Tips em PDF",
                        data=pdf_bytes,
                        file_name=f"top_tips_{date_to_use.strftime('%Y-%m-%d')}.pdf",
                        mime="application/pdf",
                    )
                with colB:
                    wa_text = top_tips_whatsapp_text(tips_list, date_to_use.strftime("%d/%m/%Y"))
                    st.text_area("Texto pronto para WhatsApp (copiar e colar)", value=wa_text, height=190)

        render_picks(
            tips_list,
            ai_enabled=(is_premium() and ai_ok and ai_enabled),
            ai_risk_enabled=(is_premium() and ai_ok and ai_risk_enabled),
            ai_max=ai_max,
            allow_fav=is_premium(),
        )

    # ---------------- Multi-bet (Premium)
    with tabs[1]:
        st.subheader("🎯 Multi-bet Builder (Premium)")
        if not is_premium():
            st.info("Este recurso é Premium. Ative Premium para ver combinações 2–4 picks.")
        else:
            tips_list = st.session_state.get("toptips", [])
            if not tips_list:
                st.warning("Primeiro gere os ⭐ Top Tips, depois volte aqui.")
            else:
                col1, col2, col3 = st.columns(3)
                with col1:
                    min_legs = st.slider("Mín legs", 2, 4, 2, 1)
                with col2:
                    max_legs = st.slider("Máx legs", 2, 4, 3, 1)
                with col3:
                    target_min = st.number_input("Odd total mínima", value=2.20, min_value=1.10, step=0.10)
                    target_max = st.number_input("Odd total máxima", value=6.00, min_value=1.20, step=0.10)

                if st.button("Gerar Multi-bets"):
                    combos = build_multibet(tips_list, min_legs, max_legs, target_min, target_max)
                    st.session_state["multibets"] = combos

                combos = st.session_state.get("multibets", [])
                if not combos:
                    st.caption("Sem combinações ainda. Clique em 'Gerar Multi-bets'.")
                else:
                    for k, c in enumerate(combos, start=1):
                        st.markdown(f"**Combo {k}** — Legs: {c['legs']} | Odd total: **{c['total_odds']:.2f}** | Prob média: **{c['avg_prob']:.3f}**")
                        for it in c["items"]:
                            st.write(f"- {it['time']} | {it['league']} | {it['match']} | {it['pick']} @ {float(it['odd']):.2f}")

    # ---------------- Favoritos (Premium)
    with tabs[2]:
        st.subheader("📌 Favoritos (Premium)")
        if not is_premium():
            st.info("Favoritos é recurso Premium.")
        else:
            favs = st.session_state.get("favorites", [])
            if not favs:
                st.caption("Nenhum favorito ainda. Abra um pick e clique em ⭐ Guardar.")
            else:
                render_picks(favs, ai_enabled=False, ai_risk_enabled=False, ai_max=0, allow_fav=False)

    # ---------------- Histórico (Premium)
    with tabs[3]:
        st.subheader("🕘 Histórico (Premium)")
        if not is_premium():
            st.info("Histórico é recurso Premium.")
        else:
            hist = st.session_state.get("history", [])
            if not hist:
                st.caption("Sem histórico ainda. Gere Top Tips ou mercados para registrar.")
            else:
                for h in hist:
                    with st.expander(f"{h['ts']} — {h['tab']} ({len(h['picks'])} picks)"):
                        render_picks(h["picks"], ai_enabled=False, ai_risk_enabled=False, ai_max=0, allow_fav=False)

    # ---------------- Markets
    markets = ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5", "Zebras"]
    for tab, market in zip(tabs[4:], markets):
        with tab:
            st.subheader(f"Mercado: {market}")
            col1, col2 = st.columns([1, 2])

            with col1:
                disabled = not free_can_generate()
                if st.button(f"🚀 Gerar Top {max_picks}", key=f"btn_{market}", disabled=disabled):
                    consume_generate_chance()

                    pbar = st.progress(0)
                    ptxt = st.empty()

                    def cb(i, tot):
                        pct = int(i * 100 / max(1, tot))
                        pbar.progress(min(100, pct))
                        ptxt.markdown(f"<div class='ptext'>A analisar {i}/{tot} jogos...</div>", unsafe_allow_html=True)

                    picks = build_picks_for_market(
                        fixtures=fixtures,
                        market=market,
                        last_n_form=last_n_form,
                        home_adv=home_adv,
                        one_per_league=one_per_league,
                        min_odd=min_odd,
                        zebra_min_odd=zebra_min_odd,
                        max_picks=max_picks,
                        progress_cb=cb,
                    )
                    st.session_state[f"picks_{market}"] = picks
                    add_to_history(market, picks)

                    pbar.progress(100)
                    ptxt.markdown("<div class='ptext'>Concluído.</div>", unsafe_allow_html=True)

                if disabled and not is_premium():
                    st.warning("Limite FREE diário atingido (3 gerações hoje). Ative Premium para ilimitado.")

            with col2:
                if is_premium():
                    st.write("Premium: gerações ilimitadas + IA + export + multi-bet + histórico.")
                else:
                    st.write(f"Free: restantes hoje: {free_remaining_today()}/{FREE_MAX_GENERATES_PER_DAY}.")

            render_picks(
                st.session_state.get(f"picks_{market}", []),
                ai_enabled=(is_premium() and ai_ok and ai_enabled),
                ai_risk_enabled=(is_premium() and ai_ok and ai_risk_enabled),
                ai_max=ai_max,
                allow_fav=is_premium(),
            )


if __name__ == "__main__":
    main()
