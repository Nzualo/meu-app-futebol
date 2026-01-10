import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st

# Tenta usar autorefresh (melhor para relógio contínuo)
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except Exception:
    HAS_AUTOREFRESH = False

# =============================
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
API_BASE = "https://v3.football.api-sports.io"
MAX_LEAGUES_DEFAULT = 20

st.set_page_config(page_title="Melhores Palpites do Dia", layout="wide")

# =============================
# DESIGN / CSS
# =============================
st.markdown(
    """
<style>
/* Base */
.main { background-color: #0b0f17; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
h1, h2, h3, p, div, span { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }

/* Header */
.hero {
  border-radius: 16px;
  padding: 18px 18px;
  background: linear-gradient(135deg, rgba(0,255,0,0.14), rgba(15,22,35,0.95));
  border: 1px solid rgba(0,255,0,0.22);
  box-shadow: 0 10px 30px rgba(0,0,0,0.30);
  margin-bottom: 16px;
}
.hero-title {
  font-size: 1.35rem;
  font-weight: 800;
  color: #eaffea;
  margin: 0;
}
.hero-sub {
  margin-top: 8px;
  color: #cdd6e0;
  font-size: 0.95rem;
}
.pills { margin-top: 10px; display:flex; gap:8px; flex-wrap: wrap; }
.pill {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.10);
  color: #e9eef7;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 0.85rem;
}
.brand {
  margin-left:auto;
  background: rgba(0,255,0,0.12);
  border: 1px solid rgba(0,255,0,0.22);
  color: #d7ffd7;
}

/* Cards */
.card {
  background-color: #141a27;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 8px 22px rgba(0,0,0,0.28);
  margin-bottom: 10px;
}
.card-left {
  border-left: 6px solid #00ff00;
}
.meta {
  color: #aab6c5;
  font-size: 0.88rem;
}
.pickline {
  margin-top: 8px;
  font-size: 1.02rem;
}
.kpi {
  display:flex;
  gap:10px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.kpi span {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.08);
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 0.88rem;
  color: #e8eef7;
}

/* WhatsApp button */
a.whatsapp {
  display:inline-block;
  text-decoration:none;
  font-weight: 800;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(0,255,0,0.35);
  background: rgba(0,255,0,0.16);
  color: #eaffea;
}
a.whatsapp:hover {
  background: rgba(0,255,0,0.24);
}

/* Tabs spacing */
div[data-baseweb="tab-list"] { gap: 6px; }
</style>
""",
    unsafe_allow_html=True,
)

# =============================
# API Helpers
# =============================
def _get_secret(name: str, default: Optional[str] = None) -> str:
    v = st.secrets.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing secret: {name}")
    return str(v)


def _football_headers() -> Dict[str, str]:
    api_key = _get_secret("FOOTBALL_API_KEY")
    mode = st.secrets.get("FOOTBALL_API_MODE", "apisports").lower().strip()
    if mode == "rapidapi":
        host = st.secrets.get("FOOTBALL_RAPIDAPI_HOST", "v3.football.api-sports.io")
        return {"x-rapidapi-key": api_key, "x-rapidapi-host": host}
    return {"x-apisports-key": api_key}


def api_get(path: str, params: Dict[str, str], timeout: int = 12) -> Dict:
    try:
        r = requests.get(f"{API_BASE}{path}", headers=_football_headers(), params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"response": [], "errors": {"request": str(e)}}


@st.cache_data(ttl=60 * 10)
def get_fixtures_by_date(date_yyyy_mm_dd: str) -> List[Dict]:
    data = api_get("/fixtures", {"date": date_yyyy_mm_dd})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 60 * 2)
def get_last_team_fixtures(team_id: int, last: int = 10, status: str = "FT") -> List[Dict]:
    data = api_get("/fixtures", {"team": str(team_id), "last": str(last), "status": status})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 10)
def get_odds_for_fixture(fixture_id: int, bookmaker: int = 8) -> List[Dict]:
    data = api_get("/odds", {"fixture": str(fixture_id), "bookmaker": str(bookmaker)})
    return data.get("response", []) or []


# =============================
# Time parsing
# =============================
def parse_fixture_time_local(fx: Dict) -> Optional[datetime]:
    try:
        iso = fx["fixture"]["date"]
        dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt_utc.astimezone(LOCAL_TZ)
    except Exception:
        return None


def is_future_fixture(fx: Dict, now_local: datetime) -> bool:
    dt = parse_fixture_time_local(fx)
    return bool(dt and dt > now_local)


# =============================
# Poisson Model
# =============================
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


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
# Odds parsing
# =============================
def _extract_market_odds(odds_response: List[Dict], market_keywords: List[str], selection_keywords: List[str]) -> Optional[float]:
    try:
        if not odds_response:
            return None
        item = odds_response[0]
        for bk in item.get("bookmakers", []):
            for bet in bk.get("bets", []):
                bet_name = (bet.get("name") or "").lower()
                if all(k.lower() in bet_name for k in market_keywords):
                    for v in bet.get("values", []):
                        vname = (v.get("value") or "").lower()
                        if all(sk.lower() in vname for sk in selection_keywords):
                            odd = v.get("odd")
                            if odd is None:
                                continue
                            return float(odd)
        return None
    except Exception:
        return None


# =============================
# Limit to top leagues
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
# Picks builder (ONE market per run)
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
    bookmaker: int,
) -> List[Dict]:
    picks: List[Dict] = []
    used_leagues = set()

    for fx in fixtures:
        try:
            fixture_id = int(fx["fixture"]["id"])
            league_id = int(fx["league"]["id"])
            league_name = fx["league"]["name"]
            home = fx["teams"]["home"]
            away = fx["teams"]["away"]
            home_id, away_id = int(home["id"]), int(away["id"])

            if one_per_league and league_id in used_leagues:
                continue

            # forma + lambdas
            home_last = get_last_team_fixtures(home_id, last=last_n_form, status="FT")
            away_last = get_last_team_fixtures(away_id, last=last_n_form, status="FT")
            home_form = compute_team_form(home_id, home_last)
            away_form = compute_team_form(away_id, away_last)
            lam_h, lam_a, ev = estimate_lambdas(home_form, away_form, home_adv=home_adv)

            odds_resp = get_odds_for_fixture(fixture_id, bookmaker=bookmaker)

            dt_local = parse_fixture_time_local(fx)
            time_str = dt_local.strftime("%H:%M") if dt_local else "??:??"
            match_name = f"{home['name']} vs {away['name']}"

            def push(pick_name: str, prob: float, odd: float):
                fo = fair_odds(prob) or 0.0
                edge = (odd / fo) - 1.0 if fo > 0 else None
                picks.append({
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
                })
                used_leagues.add(league_id)

            if market == "Over 1.5":
                p = prob_over_total(lam_h, lam_a, 1.5)
                odd = _extract_market_odds(odds_resp, ["goals over/under"], ["over 1.5"])
                if odd and odd >= min_odd:
                    push("Over 1.5", p, odd)

            elif market == "Over 2.5":
                p = prob_over_total(lam_h, lam_a, 2.5)
                odd = _extract_market_odds(odds_resp, ["goals over/under"], ["over 2.5"])
                if odd and odd >= min_odd:
                    push("Over 2.5", p, odd)

            elif market == "BTTS":
                p = prob_btts(lam_h, lam_a)
                odd = _extract_market_odds(odds_resp, ["both teams score"], ["yes"])
                if odd and odd >= min_odd:
                    push("BTTS (Yes)", p, odd)

            elif market == "1X2":
                pH, pD, pA = prob_1x2(lam_h, lam_a)
                odd_home = _extract_market_odds(odds_resp, ["match winner"], ["home"])
                odd_draw = _extract_market_odds(odds_resp, ["match winner"], ["draw"])
                odd_away = _extract_market_odds(odds_resp, ["match winner"], ["away"])

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
                odd_over = _extract_market_odds(odds_resp, ["goals over/under"], [f"over {line}"])
                if not odd_over or odd_over < min_odd:
                    continue

                pH, pD, pA = prob_1x2(lam_h, lam_a)
                p_1x, p_x2, p_12 = pH + pD, pA + pD, pH + pA

                odd_1x = _extract_market_odds(odds_resp, ["double chance"], ["home/draw"]) or _extract_market_odds(odds_resp, ["double chance"], ["1x"])
                odd_x2 = _extract_market_odds(odds_resp, ["double chance"], ["draw/away"]) or _extract_market_odds(odds_resp, ["double chance"], ["x2"])
                odd_12 = _extract_market_odds(odds_resp, ["double chance"], ["home/away"]) or _extract_market_odds(odds_resp, ["double chance"], ["12"])

                for dc_name, p_dc, odd_dc in [("1X", p_1x, odd_1x), ("X2", p_x2, odd_x2), ("12", p_12, odd_12)]:
                    if not odd_dc or odd_dc < min_odd:
                        continue
                    p_combo = clamp(p_dc * p_over, 0.0, 1.0)
                    odd_proxy = odd_dc * odd_over
                    if odd_proxy >= min_odd:
                        push(f"{dc_name} + Over {line} (odd proxy)", p_combo, odd_proxy)

            elif market == "Zebras":
                pH, pD, pA = prob_1x2(lam_h, lam_a)
                odd_home = _extract_market_odds(odds_resp, ["match winner"], ["home"])
                odd_draw = _extract_market_odds(odds_resp, ["match winner"], ["draw"])
                odd_away = _extract_market_odds(odds_resp, ["match winner"], ["away"])

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


def render_picks(picks: List[Dict]):
    if not picks:
        st.info("Sem picks que passem nos filtros (ou odds indisponíveis).")
        return

    for p in picks:
        edge = p.get("edge")
        edge_txt = f"{edge*100:.1f}%" if edge is not None else "n/a"
        st.markdown(
            f"""
<div class="card card-left">
  <div class="meta"><span class="badge">{p['time']}</span> &nbsp; <b>{p['league']}</b></div>
  <div class="pickline"><b>{p['match']}</b></div>
  <div class="pickline">Pick: <b>{p['pick']}</b></div>
  <div class="kpi">
    <span>Prob: <b>{p['prob']:.3f}</b></span>
    <span>Odd: <b>{p['odd']:.2f}</b></span>
    <span>Justa: <b>{p['fair']:.2f}</b></span>
    <span>Edge: <b>{edge_txt}</b></span>
    <span>Evid.: <b>{p['ev']}</b></span>
    <span>λ: <b>{p['lam'][0]:.2f}-{p['lam'][1]:.2f}</b></span>
  </div>
  <div class="muted" style="margin-top:8px;">DC+Over usa odd proxy quando o feed não traz odd combinada.</div>
</div>
""",
            unsafe_allow_html=True,
        )


# =============================
# MAIN
# =============================
def main():
    # Relógio contínuo
    if HAS_AUTOREFRESH:
        st_autorefresh(interval=1000, key="clock")  # 1s
    else:
        # fallback: força rerun ao carregar (menos suave)
        time.sleep(0.01)

    now_local = datetime.now(LOCAL_TZ)

    # HERO HEADER
    whatsapp_number = "258867926665"
    whatsapp_link = f"https://wa.me/{whatsapp_number}"

    st.markdown(
        f"""
<div class="hero">
  <div style="display:flex; align-items:center; gap:10px;">
    <p class="hero-title">Melhores Palpites e Possível Zebras do Dia.</p>
  </div>
  <div class="hero-sub">
    <b>Local:</b> Inhassoro &nbsp; | &nbsp; <b>Hora:</b> {now_local.strftime('%H:%M:%S')}
  </div>
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
        auto_tomorrow_if_empty = st.checkbox("Se hoje não tiver jogos futuros, usar amanhã", value=True)
        max_picks = st.slider("Top picks por aba", 5, 20, 10, 1)
        one_per_league = st.checkbox("1 pick por liga", value=True)
        max_leagues = st.slider("Máx. ligas/campeonatos", 5, 30, MAX_LEAGUES_DEFAULT, 1)

        last_n_form = st.slider("Forma (últimos jogos FT)", 4, 20, 10, 1)
        home_adv = st.slider("Vantagem de casa", 1.00, 1.20, 1.08, 0.01)

        bookmaker = st.number_input("Bookmaker ID (odds)", value=8, min_value=1, step=1)
        min_odd = st.number_input("Odd mínima (normais)", value=1.30, min_value=1.01, step=0.01)
        zebra_min_odd = st.number_input("Odd mínima (zebras)", value=4.00, min_value=2.00, step=0.10)

    # Fixtures hoje (futuros)
    date_to_use = now_local.date()
    fixtures = get_fixtures_by_date(date_to_use.strftime("%Y-%m-%d"))
    fixtures = [fx for fx in fixtures if is_future_fixture(fx, now_local)]

    # Amanhã se vazio
    if not fixtures and auto_tomorrow_if_empty:
        date_to_use = (now_local + timedelta(days=1)).date()
        fixtures = get_fixtures_by_date(date_to_use.strftime("%Y-%m-%d"))
        fixtures = [fx for fx in fixtures if parse_fixture_time_local(fx) is not None]

    if not fixtures:
        st.error("Nenhum jogo encontrado.")
        return

    fixtures = limit_to_top_leagues(fixtures, max_leagues=max_leagues)

    st.caption(f"Data analisada: {date_to_use.strftime('%d/%m/%Y')} | Jogos após limite de ligas: {len(fixtures)}")

    tabs = st.tabs(["🏆 1X2", "⚽ BTTS", "📈 Over 1.5", "📈 Over 2.5", "👥 DC+O1.5", "👥 DC+O2.5", "🟣 Zebras"])
    markets = ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5", "Zebras"]

    for tab, market in zip(tabs, markets):
        with tab:
            st.subheader(f"Mercado: {market}")
            col1, col2 = st.columns([1, 2])

            with col1:
                if st.button(f"Gerar Top {max_picks}", key=f"btn_{market}"):
                    picks = build_picks_for_market(
                        fixtures=fixtures,
                        market=market,
                        last_n_form=last_n_form,
                        home_adv=home_adv,
                        one_per_league=one_per_league,
                        min_odd=min_odd,
                        zebra_min_odd=zebra_min_odd,
                        max_picks=max_picks,
                        bookmaker=bookmaker,
                    )
                    st.session_state[f"picks_{market}"] = picks

            with col2:
                st.write(
                    "Ranking por edge (odd mercado vs odd justa do modelo). "
                    "Se não aparecerem picks, o feed de odds pode não ter linhas para o jogo/mercado."
                )

            render_picks(st.session_state.get(f"picks_{market}", []))


if __name__ == "__main__":
    main()
