import math
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st

# =============================
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
MAX_LEAGUES_DEFAULT = 20

# AllSportsAPI
ALLSPORTS_BASE = "https://apiv2.allsportsapi.com/football/"

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

/* ===== Barcelona header ===== */
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
</style>
""",
    unsafe_allow_html=True,
)

# =============================
# Secrets / Provider
# =============================
def _get_secret(name: str, default: Optional[str] = None) -> str:
    v = st.secrets.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing secret: {name}")
    return str(v)

def provider_mode() -> str:
    return str(st.secrets.get("FOOTBALL_API_MODE", "allsports")).lower().strip()

# =============================
# AllSportsAPI low-level
# =============================
def allsports_get(met: str, params: Dict[str, str], timeout: int = 15) -> Dict:
    """
    AllSportsAPI V2:
      GET https://apiv2.allsportsapi.com/football/?met=...&APIkey=...&...
    """
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
# Normalização (AllSports -> estrutura parecida com teu código original)
# =============================
def _as_int(x) -> Optional[int]:
    try:
        if x is None: return None
        return int(str(x))
    except Exception:
        return None

def _parse_allsports_dt_local(ev: Dict) -> Optional[datetime]:
    """
    AllSports devolve event_date 'YYYY-MM-DD' e event_time 'HH:MM' (quando timezone é passado).
    """
    try:
        d = ev.get("event_date")
        t = ev.get("event_time") or "00:00"
        dt = datetime.fromisoformat(f"{d} {t}")
        return LOCAL_TZ.localize(dt)
    except Exception:
        return None

def _normalize_fixture_allsports(ev: Dict) -> Optional[Dict]:
    """
    Converte evento AllSports em estrutura compatível com o resto do app.
    """
    try:
        fx_id = _as_int(ev.get("event_key") or ev.get("match_id") or ev.get("event_id"))
        league_id = _as_int(ev.get("league_key"))
        home_id = _as_int(ev.get("home_team_key"))
        away_id = _as_int(ev.get("away_team_key"))
        if not (fx_id and league_id and home_id and away_id):
            return None

        dt_local = _parse_allsports_dt_local(ev)
        # ISO fake para manter parse_fixture_time_local simples
        iso = dt_local.astimezone(pytz.UTC).isoformat() if dt_local else None

        # status: finished/live/etc
        status_txt = (ev.get("event_status") or "").lower()
        # tentativas comuns: "Finished", "Postponed", "Not Started"
        # vamos mapear de forma simples
        if "finish" in status_txt:
            short = "FT"
        elif "not" in status_txt and "start" in status_txt:
            short = "NS"
        else:
            short = ev.get("event_status") or "NS"

        return {
            "fixture": {
                "id": fx_id,
                "date": (iso or ""),
                "status": {"short": short},
            },
            "league": {"id": league_id, "name": ev.get("league_name") or "Liga"},
            "teams": {
                "home": {"id": home_id, "name": ev.get("event_home_team") or "Home"},
                "away": {"id": away_id, "name": ev.get("event_away_team") or "Away"},
            },
            "goals": {
                "home": _as_int(ev.get("event_home_final_result")) if ev.get("event_home_final_result") else None,
                "away": _as_int(ev.get("event_away_final_result")) if ev.get("event_away_final_result") else None,
            },
            "_raw": ev,
        }
    except Exception:
        return None

# =============================
# Data access (AllSports)
# =============================
@st.cache_data(ttl=60 * 10)
def get_fixtures_by_date(date_yyyy_mm_dd: str) -> List[Dict]:
    """
    Puxa jogos do dia usando AllSportsAPI met=Fixtures&from=...&to=...&timezone=Africa/Maputo
    """
    if provider_mode() != "allsports":
        return []

    data = allsports_get("Fixtures", {
        "from": date_yyyy_mm_dd,
        "to": date_yyyy_mm_dd,
        "timezone": "Africa/Maputo",
    })
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
    """
    AllSports não tem 'last=N' igual API-FOOTBALL; fazemos por janela (últimos 120 dias)
    e filtramos os terminados.
    """
    if provider_mode() != "allsports":
        return []

    today = datetime.now(LOCAL_TZ).date()
    start = today - timedelta(days=120)

    data = allsports_get("Fixtures", {
        "teamId": str(team_id),
        "from": start.strftime("%Y-%m-%d"),
        "to": today.strftime("%Y-%m-%d"),
        "timezone": "Africa/Maputo",
    })
    if str(data.get("success")) != "1":
        return []

    res = data.get("result") or []
    norm = []
    for ev in res:
        fx = _normalize_fixture_allsports(ev)
        if not fx:
            continue
        # filtra FT
        st_short = (fx.get("fixture", {}).get("status", {}) or {}).get("short", "")
        if status == "FT" and st_short != "FT":
            continue
        norm.append(fx)

    # ordenar por data desc
    def _dt_key(x):
        dt = parse_fixture_time_local(x)
        return dt.timestamp() if dt else 0.0

    norm.sort(key=_dt_key, reverse=True)
    return norm[:last]

@st.cache_data(ttl=60 * 10)
def get_odds_for_fixture(fixture_id: int, bookmaker: int = 0) -> Dict:
    """
    AllSports Odds retorna um dicionário result: {matchId: [ {odd_1, odd_x, odd_2, odd_1x, odd_x2, odd_12, o+1.5, o+2.5, bts_yes, ...}, ... ] }
    """
    if provider_mode() != "allsports":
        return {}

    data = allsports_get("Odds", {"matchId": str(fixture_id)})
    if str(data.get("success")) != "1":
        return {}

    result = data.get("result") or {}
    # result pode vir como dict com chave matchId string
    row_list = result.get(str(fixture_id)) if isinstance(result, dict) else None
    if not row_list:
        return {}
    # usa o primeiro bookmaker disponível
    return row_list[0] if isinstance(row_list, list) and row_list else {}

# =============================
# Time parsing (mantido)
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
# Poisson Model (mantido)
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
# Odds mapping (AllSports)
# =============================
def odds_allsports_market(odds_row: Dict, market: str) -> Optional[float]:
    """
    Converte teus mercados para chaves do AllSports:
      1X2: odd_1 / odd_x / odd_2
      DC: odd_1x / odd_x2 / odd_12
      Over: o+1.5 / o+2.5
      BTTS: bts_yes
    """
    if not odds_row:
        return None

    try:
        def f(key: str) -> Optional[float]:
            v = odds_row.get(key)
            if v is None or v == "":
                return None
            return float(v)

        if market == "odd_1": return f("odd_1")
        if market == "odd_x": return f("odd_x")
        if market == "odd_2": return f("odd_2")

        if market == "odd_1x": return f("odd_1x")
        if market == "odd_x2": return f("odd_x2")
        if market == "odd_12": return f("odd_12")

        if market == "o+1.5": return f("o+1.5")
        if market == "o+2.5": return f("o+2.5")

        if market == "bts_yes": return f("bts_yes")
        return None
    except Exception:
        return None

# =============================
# Fixture filtering to MAX 20 leagues (mantido)
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
# Picks builder (mantido, trocando apenas odds)
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

    show_progress = bool(st.session_state.get("_show_progress", False))
    pbar = st.progress(0) if show_progress else None
    ptxt = st.empty() if show_progress else None
    total = max(1, len(fixtures))

    for idx, fx in enumerate(fixtures, start=1):
        if show_progress and pbar is not None and ptxt is not None:
            pbar.progress(min(100, int(idx * 100 / total)))
            ptxt.markdown(f"<div class='ptext'>A analisar {idx}/{total} jogos...</div>", unsafe_allow_html=True)

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
            home_form = compute_team_form(home_id, home_last)
            away_form = compute_team_form(away_id, away_last)
            lam_h, lam_a, ev = estimate_lambdas(home_form, away_form, home_adv=home_adv)

            odds_row = get_odds_for_fixture(fixture_id, bookmaker=bookmaker)

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
                    "fixture_id": fixture_id,
                })
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

                for dc_name, p_dc, odd_dc in [("1X", p_1x, odd_1x), ("X2", p_x2, odd_x2), ("12", p_12, odd_12)]:
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

    if show_progress and pbar is not None and ptxt is not None:
        pbar.progress(100)
        ptxt.markdown("<div class='ptext'>Concluído.</div>", unsafe_allow_html=True)

    picks = sorted(
        picks,
        key=lambda x: (
            -999 if x.get("edge") is None else -x["edge"],
            -x.get("prob", 0.0),
        ),
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
<div class="card">
  <div><span class="badge">{p['time']}</span> <b>{p['league']}</b></div>
  <div style="margin-top:6px;"><b>{p['match']}</b></div>
  <div style="margin-top:6px;">
    Pick: <b>{p['pick']}</b><br/>
    Prob(modelo): <b>{p['prob']:.3f}</b> | Odd mercado: <b>{p['odd']:.2f}</b> | Odd justa: <b>{p['fair']:.2f}</b> | Edge: <b>{edge_txt}</b><br/>
    Evidência: <b>{p['ev']}</b> | λ: {p['lam'][0]:.2f}-{p['lam'][1]:.2f}
  </div>
  <div class="muted" style="margin-top:6px;">
    Nota: DC+Over usa odd proxy quando a odd combinada não existe no feed.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

# =============================
# MAIN
# =============================
def main():
    now_local = datetime.now(LOCAL_TZ)

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
    <a class="barca-wa" href="https://wa.me/258867926665" target="_blank" rel="noopener noreferrer">WhatsApp</a>
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

        min_odd = st.number_input("Odd mínima (normais)", value=1.30, min_value=1.01, step=0.01)
        zebra_min_odd = st.number_input("Odd mínima (zebras)", value=4.00, min_value=2.00, step=0.10)

        debug = st.checkbox("Mostrar diagnóstico (debug)", value=False)

    # Fixtures hoje (futuros)
    date_to_use = now_local.date()
    date_str = date_to_use.strftime("%Y-%m-%d")
    fixtures_raw = get_fixtures_by_date(date_str)
    fixtures = [fx for fx in fixtures_raw if is_future_fixture(fx, now_local)]

    # Amanhã se: hoje tinha fixtures brutos, mas nenhum futuro
    if auto_tomorrow_if_empty and (len(fixtures_raw) > 0) and (len(fixtures) == 0):
        date_to_use = (now_local + timedelta(days=1)).date()
        date_str = date_to_use.strftime("%Y-%m-%d")
        fixtures_raw = get_fixtures_by_date(date_str)
        fixtures = [fx for fx in fixtures_raw if parse_fixture_time_local(fx) is not None]

    if debug:
        with st.expander("Diagnóstico (fixtures/tempo)"):
            st.write("Provider:", provider_mode())
            st.write("Data usada:", date_str)
            st.write("Agora (local):", now_local.isoformat())
            st.write("Fixtures brutos:", len(fixtures_raw))
            st.write("Fixtures após filtro:", len(fixtures))
            if len(fixtures_raw) == 0:
                st.warning("A API devolveu 0 fixtures para esta data. Verifique plano/cobertura/limite.")
            else:
                s = parse_fixture_time_local(fixtures_raw[0])
                st.write("Exemplo 1º fixture (hora local):", s.isoformat() if s else None)
                st.write("Exemplo league:", fixtures_raw[0].get("league", {}).get("name"))

    if not fixtures:
        st.error("Nenhum jogo encontrado (ou odds indisponíveis).")
        return

    fixtures = limit_to_top_leagues(fixtures, max_leagues=max_leagues)

    st.markdown(
        f"🗓️ Data analisada: <span class='badge'>{date_to_use.strftime('%d/%m/%Y')}</span>",
        unsafe_allow_html=True,
    )
    st.caption(f"Jogos carregados (após limite de ligas): {len(fixtures)} | Máx. ligas: {max_leagues}")

    tabs = st.tabs(["🏆 1X2", "⚽ BTTS", "📈 Over 1.5", "📈 Over 2.5", "👥 DC+O1.5", "👥 DC+O2.5", "🟣 Zebras"])
    markets = ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5", "Zebras"]

    for tab, market in zip(tabs, markets):
        with tab:
            st.subheader(f"Mercado: {market}")

            col1, col2 = st.columns([1, 2])
            with col1:
                if st.button(f"🚀 Gerar Top {max_picks}", key=f"btn_{market}"):
                    st.session_state["_show_progress"] = True
                    try:
                        picks = build_picks_for_market(
                            fixtures=fixtures,
                            market=market,
                            last_n_form=last_n_form,
                            home_adv=home_adv,
                            one_per_league=one_per_league,
                            min_odd=min_odd,
                            zebra_min_odd=zebra_min_odd,
                            max_picks=max_picks,
                            bookmaker=0,
                        )
                        st.session_state[f"picks_{market}"] = picks
                    finally:
                        st.session_state["_show_progress"] = False

            with col2:
                st.write(
                    "Critérios: odds mínimas + ranking por edge (odd mercado vs odd justa do modelo). "
                    "Se não aparecerem picks, pode ser falta de odds para esse jogo/mercado no AllSports."
                )

            render_picks(st.session_state.get(f"picks_{market}", []))

if __name__ == "__main__":
    main()
