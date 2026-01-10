import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st

# =============================
# OPTIONAL: Continuous clock refresh
# =============================
try:
    from streamlit_autorefresh import st_autorefresh  # pip install streamlit-autorefresh
    HAS_AUTOREFRESH = True
except Exception:
    HAS_AUTOREFRESH = False

# =============================
# OPENAI
# =============================
try:
    from openai import OpenAI
    HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False

# =============================
# SESSION STATE
# =============================
if "pause_refresh" not in st.session_state:
    st.session_state["pause_refresh"] = False

# =============================
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
API_SPORTS_BASE = "https://v3.football.api-sports.io"
MAX_LEAGUES_DEFAULT = int(st.secrets.get("MAX_LEAGUES", 20))

st.set_page_config(page_title="Melhores Palpites do Dia", layout="wide")

# =============================
# UI / CSS
# =============================
st.markdown(
    """
<style>
.main { background-color: #0b0f17; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.hero {
  border-radius: 16px; padding: 18px 18px;
  background: linear-gradient(135deg, rgba(0,255,0,0.14), rgba(15,22,35,0.95));
  border: 1px solid rgba(0,255,0,0.22);
  box-shadow: 0 10px 30px rgba(0,0,0,0.30);
  margin-bottom: 16px;
}
.hero-title { font-size: 1.35rem; font-weight: 800; color: #eaffea; margin: 0; }
.hero-sub { margin-top: 8px; color: #cdd6e0; font-size: 0.95rem; }
.pills { margin-top: 10px; display:flex; gap:8px; flex-wrap: wrap; align-items:center; }
.pill {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);
  color: #e9eef7; border-radius: 999px; padding: 6px 10px; font-size: 0.85rem;
}
.brand { background: rgba(0,255,0,0.12); border: 1px solid rgba(0,255,0,0.22); color: #d7ffd7; }
.card {
  background-color: #141a27; padding: 14px; border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 8px 22px rgba(0,0,0,0.28);
  margin-bottom: 10px;
}
.card-left { border-left: 6px solid #00ff00; }
.meta { color: #aab6c5; font-size: 0.88rem; }
.pickline { margin-top: 8px; font-size: 1.02rem; }
.kpi { display:flex; gap:10px; flex-wrap: wrap; margin-top: 10px; }
.kpi span {
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
  padding: 6px 10px; border-radius: 10px; font-size: 0.88rem; color: #e8eef7;
}
a.whatsapp {
  display:inline-block; text-decoration:none; font-weight: 800; padding: 10px 14px;
  border-radius: 12px; border: 1px solid rgba(0,255,0,0.35);
  background: rgba(0,255,0,0.16); color: #eaffea;
}
a.whatsapp:hover { background: rgba(0,255,0,0.24); }
div[data-baseweb="tab-list"] { gap: 6px; }
</style>
""",
    unsafe_allow_html=True,
)

# =============================
# Helpers
# =============================
def _sec(name: str, default: Optional[str] = None) -> str:
    v = st.secrets.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing secret: {name}")
    return str(v)

def norm_team(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(fc|sc|cf|ac|cd|afc|cfc|fk|sk)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_iso_local(iso: str) -> Optional[datetime]:
    try:
        dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt_utc.astimezone(LOCAL_TZ)
    except Exception:
        return None

def match_event(home_a: str, away_a: str, t_a: Optional[datetime],
                home_b: str, away_b: str, t_b: Optional[datetime],
                tol_minutes: int = 120) -> bool:
    if not t_a or not t_b:
        return False
    ha, aa = norm_team(home_a), norm_team(away_a)
    hb, ab = norm_team(home_b), norm_team(away_b)
    same = (ha == hb and aa == ab) or (ha == ab and aa == hb)
    if not same:
        return False
    diff = abs(int((t_a - t_b).total_seconds() / 60))
    return diff <= tol_minutes

# =============================
# API 1: API-SPORTS (api-football.com)
# =============================
def apisports_headers() -> Dict[str, str]:
    return {"x-apisports-key": _sec("APISPORTS_KEY")}

def apisports_get(path: str, params: Dict[str, str], timeout: int = 15) -> Dict:
    r = requests.get(f"{API_SPORTS_BASE}{path}", headers=apisports_headers(), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=60 * 10)
def apisports_fixtures(date_yyyy_mm_dd: str) -> List[Dict]:
    return (apisports_get("/fixtures", {"date": date_yyyy_mm_dd}).get("response") or [])

@st.cache_data(ttl=60 * 60)
def apisports_team_last(team_id: int, last: int = 10) -> List[Dict]:
    return (apisports_get("/fixtures", {"team": str(team_id), "last": str(last), "status": "FT"}).get("response") or [])

@st.cache_data(ttl=60 * 10)
def apisports_odds_fixture(fixture_id: int) -> List[Dict]:
    return (apisports_get("/odds", {"fixture": str(fixture_id)}).get("response") or [])

def apisports_extract_market(odds_resp: List[Dict], market_name: str, selection_value: str) -> Optional[float]:
    if not odds_resp:
        return None
    try:
        item = odds_resp[0]
        for bk in item.get("bookmakers", []):
            for bet in bk.get("bets", []):
                if (bet.get("name") or "").lower() == market_name.lower():
                    for v in bet.get("values", []):
                        if (v.get("value") or "").lower() == selection_value.lower():
                            odd = v.get("odd")
                            return float(odd) if odd is not None else None
    except Exception:
        pass
    return None

# =============================
# API 2: APIFootball (apifootball.com)
# =============================
@st.cache_data(ttl=60 * 10)
def apifootball_events(date_yyyy_mm_dd: str) -> List[Dict]:
    base = _sec("APIFOOTBALL_BASE")
    key = _sec("APIFOOTBALL_KEY")

    # fixtures/events
    r = requests.get(
        f"{base}/",
        params={"action": "get_events", "from": date_yyyy_mm_dd, "to": date_yyyy_mm_dd, "APIkey": key},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    out = []
    if isinstance(data, list):
        for it in data:
            dt = None
            try:
                d = it.get("match_date")
                t = it.get("match_time") or "00:00"
                dt = LOCAL_TZ.localize(datetime.fromisoformat(f"{d} {t}")) if d else None
            except Exception:
                dt = None
            out.append({
                "home": it.get("match_hometeam_name") or "",
                "away": it.get("match_awayteam_name") or "",
                "time_local": dt,
                "league": it.get("league_name") or it.get("country_name") or "Liga",
                "raw": it,
            })
    return out

@st.cache_data(ttl=60 * 10)
def apifootball_odds_day(date_yyyy_mm_dd: str) -> List[Dict]:
    base = _sec("APIFOOTBALL_BASE")
    key = _sec("APIFOOTBALL_KEY")

    # odds (se a sua conta tiver). Se der vazio, ok.
    r = requests.get(
        f"{base}/",
        params={"action": "get_odds", "from": date_yyyy_mm_dd, "to": date_yyyy_mm_dd, "APIkey": key},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    out = []
    if isinstance(data, list):
        for it in data:
            dt = None
            try:
                d = it.get("match_date")
                t = it.get("match_time") or "00:00"
                dt = LOCAL_TZ.localize(datetime.fromisoformat(f"{d} {t}")) if d else None
            except Exception:
                dt = None

            out.append({
                "home": it.get("match_hometeam_name") or it.get("home_team") or "",
                "away": it.get("match_awayteam_name") or it.get("away_team") or "",
                "time_local": dt,
                "raw": it,
            })
    return out

def apifootball_extract_1x2(raw: Dict) -> Dict[str, Optional[float]]:
    it = raw.get("raw", raw)
    for hk, dk, ak in [
        ("odd_1", "odd_x", "odd_2"),
        ("odds_home", "odds_draw", "odds_away"),
        ("home_odds", "draw_odds", "away_odds"),
    ]:
        if it.get(hk) and it.get(dk) and it.get(ak):
            return {"home": float(it[hk]), "draw": float(it[dk]), "away": float(it[ak])}
    return {"home": None, "draw": None, "away": None}

# =============================
# API 3: Third API (ex.: AllSportsAPI) — odds fallback extra
# =============================
@st.cache_data(ttl=60 * 10)
def thirdapi_odds_day(date_yyyy_mm_dd: str) -> List[Dict]:
    base = _sec("THIRD_API_BASE")
    key = _sec("THIRD_API_KEY")

    # Exemplo AllSportsAPI (ajuste se sua 3ª API for outra)
    r = requests.get(
        f"{base}/football/",
        params={"met": "Odds", "APIkey": key, "from": date_yyyy_mm_dd, "to": date_yyyy_mm_dd},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    out = []
    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, list):
        for it in result:
            dt = None
            try:
                d = it.get("event_date") or it.get("match_date")
                t = it.get("event_time") or it.get("match_time") or "00:00"
                dt = LOCAL_TZ.localize(datetime.fromisoformat(f"{d} {t}")) if d else None
            except Exception:
                dt = None

            out.append({
                "home": it.get("event_home_team") or it.get("home_team") or "",
                "away": it.get("event_away_team") or it.get("away_team") or "",
                "time_local": dt,
                "raw": it,
            })
    return out

def thirdapi_extract_1x2(raw: Dict) -> Dict[str, Optional[float]]:
    it = raw.get("raw", raw)
    for hk, dk, ak in [
        ("odd_1", "odd_x", "odd_2"),
        ("home_odds", "draw_odds", "away_odds"),
        ("odds_home", "odds_draw", "odds_away"),
    ]:
        if it.get(hk) and it.get(dk) and it.get(ak):
            return {"home": float(it[hk]), "draw": float(it[dk]), "away": float(it[ak])}
    return {"home": None, "draw": None, "away": None}

# =============================
# Probabilidades
# =============================
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def prob_1x2(lam_h: float, lam_a: float, max_goals: int = 10) -> Tuple[float, float, float]:
    pH = pD = pA = 0.0
    for gh in range(max_goals + 1):
        ph = poisson_pmf(gh, lam_h)
        for ga in range(max_goals + 1):
            pa = poisson_pmf(ga, lam_a)
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
    return None if p <= 0 else 1.0 / p

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def compute_team_form(team_id: int, fixtures_ft: List[Dict]) -> Tuple[int, float, float, float, float, float, float]:
    gf = ga = 0
    n = 0
    gf_home = ga_home = 0
    n_home = 0
    gf_away = ga_away = 0
    n_away = 0

    for fx in fixtures_ft:
        try:
            home_id = fx["teams"]["home"]["id"]
            away_id = fx["teams"]["away"]["id"]
            goals_home = fx["goals"]["home"]
            goals_away = fx["goals"]["away"]
            if goals_home is None or goals_away is None:
                continue

            if team_id == home_id:
                _gf, _ga = int(goals_home), int(goals_away)
                gf_home += _gf
                ga_home += _ga
                n_home += 1
            elif team_id == away_id:
                _gf, _ga = int(goals_away), int(goals_home)
                gf_away += _gf
                ga_away += _ga
                n_away += 1
            else:
                continue

            gf += _gf
            ga += _ga
            n += 1
        except Exception:
            continue

    if n == 0:
        return 0, 0.0, 0.0, -1.0, -1.0, -1.0, -1.0

    gf_pg = gf / n
    ga_pg = ga / n
    gf_home_pg = (gf_home / n_home) if n_home > 0 else -1.0
    ga_home_pg = (ga_home / n_home) if n_home > 0 else -1.0
    gf_away_pg = (gf_away / n_away) if n_away > 0 else -1.0
    ga_away_pg = (ga_away / n_away) if n_away > 0 else -1.0

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
    lam_h = w * lam_home_raw + (1 - w) * base
    lam_a = w * lam_away_raw + (1 - w) * base

    ev = "ALTA" if n_eff >= 8 else ("MÉDIA" if n_eff >= 4 else "BAIXA")
    return clamp(lam_h, 0.2, 3.5), clamp(lam_a, 0.2, 3.5), ev

# =============================
# IA (explicação)
# =============================
def openai_client() -> Optional["OpenAI"]:
    if not HAS_OPENAI:
        return None
    k = st.secrets.get("OPENAI_API_KEY")
    if not k:
        return None
    return OpenAI(api_key=k)

@st.cache_data(ttl=60 * 60)
def ai_explain(home: str, away: str, league: str, pick: str, prob: float, odd: Optional[float], lam_h: float, lam_a: float, ev: str) -> str:
    c = openai_client()
    if c is None:
        return "IA indisponível (verifique openai no requirements e OPENAI_API_KEY nos secrets)."
    odd_txt = f"{odd:.2f}" if odd is not None else "—"
    prompt = f"""
Explique de forma curta e técnica (máx 6 linhas) este palpite. Não prometa ganhos.
Jogo: {home} vs {away}
Liga: {league}
Pick: {pick}
Probabilidade: {prob:.3f}
Odd (se houver): {odd_txt}
λ casa/fora: {lam_h:.2f}/{lam_a:.2f}
Evidência: {ev}
Inclua: 2 razões quantitativas + 1 risco.
"""
    r = c.chat.completions.create(
        model=st.secrets.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    return (r.choices[0].message.content or "").strip()

# =============================
# Odds Orchestrator (3 APIs)
# =============================
def get_1x2_odds_for_fixture(
    fx: Dict,
    apifootball_odds: List[Dict],
    third_odds: List[Dict],
) -> Tuple[Dict[str, Optional[float]], str]:
    """
    Ordem:
    1) API-SPORTS odds (fixture id)
    2) APIFootball odds day (matching)
    3) Third API odds day (matching)
    """
    home = fx["teams"]["home"]["name"]
    away = fx["teams"]["away"]["name"]
    t = parse_iso_local(fx["fixture"]["date"])

    # 1) API-SPORTS
    try:
        oresp = apisports_odds_fixture(int(fx["fixture"]["id"]))
        out = {
            "home": apisports_extract_market(oresp, "Match Winner", "Home"),
            "draw": apisports_extract_market(oresp, "Match Winner", "Draw"),
            "away": apisports_extract_market(oresp, "Match Winner", "Away"),
        }
        if any(out.values()):
            return out, "API-SPORTS"
    except Exception:
        pass

    # 2) APIFootball (matching)
    if t:
        for ev in apifootball_odds:
            if match_event(home, away, t, ev["home"], ev["away"], ev["time_local"]):
                out = apifootball_extract_1x2(ev)
                if any(out.values()):
                    return out, "APIFootball"

    # 3) Third API (matching)
    if t:
        for ev in third_odds:
            if match_event(home, away, t, ev["home"], ev["away"], ev["time_local"]):
                out = thirdapi_extract_1x2(ev)
                if any(out.values()):
                    return out, "ThirdAPI"

    return {"home": None, "draw": None, "away": None}, "—"

# =============================
# Render
# =============================
def render_cards(rows: List[Dict], use_ai: bool):
    if not rows:
        st.info("Sem picks para mostrar.")
        return

    for r in rows:
        odd_txt = f"{r['odd']:.2f}" if r["odd"] is not None else "—"
        fair_txt = f"{r['fair']:.2f}" if r["fair"] is not None else "—"
        edge_txt = f"{r['edge']*100:.1f}%" if r["edge"] is not None else "—"
        st.markdown(
            f"""
<div class="card card-left">
  <div class="meta"><b>{r['time']}</b> | <b>{r['league']}</b> | Odds: <b>{r['odds_source']}</b></div>
  <div class="pickline"><b>{r['match']}</b></div>
  <div class="pickline">Pick: <b>{r['pick']}</b></div>
  <div class="kpi">
    <span>Prob: <b>{r['prob']:.3f}</b></span>
    <span>Odd: <b>{odd_txt}</b></span>
    <span>Justa: <b>{fair_txt}</b></span>
    <span>Edge: <b>{edge_txt}</b></span>
    <span>Evid.: <b>{r['ev']}</b></span>
    <span>λ: <b>{r['lam_h']:.2f}-{r['lam_a']:.2f}</b></span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        if use_ai:
            with st.expander("IA: análise", expanded=False):
                st.write(ai_explain(r["home"], r["away"], r["league"], r["pick"], r["prob"], r["odd"], r["lam_h"], r["lam_a"], r["ev"]))

# =============================
# MAIN
# =============================
def main():
    if HAS_AUTOREFRESH and not st.session_state["pause_refresh"]:
        st_autorefresh(interval=1000, key="clock")
    else:
        time.sleep(0.01)

    now_local = datetime.now(LOCAL_TZ)
    whatsapp_link = "https://wa.me/258867926665"

    st.markdown(
        f"""
<div class="hero">
  <p class="hero-title">Melhores Palpites e Possível Zebras do Dia.</p>
  <div class="hero-sub"><b>Local:</b> Inhassoro &nbsp; | &nbsp; <b>Hora:</b> {now_local.strftime('%H:%M:%S')}</div>
  <div class="pills">
    <span class="pill brand">By Nzualo</span>
    <a class="whatsapp" href="{whatsapp_link}" target="_blank" rel="noopener noreferrer">WhatsApp</a>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.subheader("Configuração")
        auto_tomorrow = st.checkbox("Se hoje não tiver jogos futuros, usar amanhã", value=True)
        max_picks = st.slider("Top picks", 5, 20, 10, 1)
        last_n = st.slider("Forma (últimos FT)", 4, 20, 10, 1)
        home_adv = st.slider("Vantagem de casa", 1.00, 1.20, 1.08, 0.01)
        min_odd = st.number_input("Odd mínima (se houver)", value=1.30, min_value=1.01, step=0.01)
        use_ai = st.checkbox("IA ligada", value=HAS_OPENAI and ("OPENAI_API_KEY" in st.secrets))

        st.caption("Odds: tenta API-SPORTS → APIFootball → ThirdAPI (fallback).")

    # Fixtures API-SPORTS (primário)
    date_use = now_local.date()
    date_str = date_use.strftime("%Y-%m-%d")
    fx = apisports_fixtures(date_str)
    fx = [x for x in fx if parse_iso_local(x["fixture"]["date"]) and parse_iso_local(x["fixture"]["date"]) > now_local]

    if not fx and auto_tomorrow:
        date_use = (now_local + timedelta(days=1)).date()
        date_str = date_use.strftime("%Y-%m-%d")
        fx = apisports_fixtures(date_str)

    if not fx:
        st.error("Nenhum jogo encontrado.")
        return

    # carrega pools de odds (API2 e API3)
    api2_odds = apifootball_odds_day(date_str)
    api3_odds = thirdapi_odds_day(date_str)

    with st.expander("Debug (quantidade de odds por fonte)", expanded=False):
        st.write({"API2(APIFootball) odds events": len(api2_odds), "API3(ThirdAPI) odds events": len(api3_odds)})

    if st.button("Gerar Top 10 (1X2)", key="gen"):
        st.session_state["pause_refresh"] = True
        prog = st.progress(0)
        msg = st.empty()

        rows = []
        total = len(fx)
        for i, f in enumerate(fx, start=1):
            prog.progress(int(i * 100 / total))
            msg.write(f"A analisar {i}/{total} jogos...")

            dt_local = parse_iso_local(f["fixture"]["date"])
            if not dt_local:
                continue

            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            league = f["league"]["name"]

            home_id = int(f["teams"]["home"]["id"])
            away_id = int(f["teams"]["away"]["id"])
            home_last = apisports_team_last(home_id, last=last_n)
            away_last = apisports_team_last(away_id, last=last_n)

            lam_h, lam_a, ev = estimate_lambdas(
                compute_team_form(home_id, home_last),
                compute_team_form(away_id, away_last),
                home_adv=home_adv,
            )

            pH, pD, pA = prob_1x2(lam_h, lam_a)

            odds_1x2, source = get_1x2_odds_for_fixture(f, api2_odds, api3_odds)

            # escolher melhor (com ou sem odd)
            cands = [("Casa", pH, odds_1x2["home"]), ("Empate", pD, odds_1x2["draw"]), ("Fora", pA, odds_1x2["away"])]

            best = None
            best_score = -1.0
            for nm, pr, od in cands:
                if od is not None and od < min_odd:
                    continue
                score = pr if od is None else pr * od
                if score > best_score:
                    best_score = score
                    best = (nm, pr, od)

            if not best:
                continue

            nm, pr, od = best
            fo = fair_odds(pr)
            edge = ((od / fo) - 1.0) if (od is not None and fo) else None

            rows.append({
                "time": dt_local.strftime("%H:%M"),
                "league": league,
                "match": f"{home} vs {away}",
                "home": home,
                "away": away,
                "pick": f"1X2: {nm}",
                "prob": pr,
                "odd": od,
                "fair": fo,
                "edge": edge,
                "ev": ev,
                "lam_h": lam_h,
                "lam_a": lam_a,
                "odds_source": source,
            })

        msg.write("Concluído.")
        rows = sorted(rows, key=lambda r: (-(r["edge"] if r["edge"] is not None else -999), -r["prob"]))[:10]
        st.session_state["rows"] = rows

    render_cards(st.session_state.get("rows", []), use_ai=use_ai)

if __name__ == "__main__":
    main()
