import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st

# =============================
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
API_BASE = "https://v3.football.api-sports.io"

st.set_page_config(page_title="Elite Scanner 4.0", layout="wide")

st.markdown(
    """
<style>
.main { background-color: #0e1117; }
.card { background-color: #1a1c24; padding: 14px; border-radius: 12px;
        border-left: 7px solid #00ff00; color: white; margin-bottom: 10px; }
.muted { color: #aab; font-size: 0.90rem; }
.badge { background-color: #00ff00; color: black; padding: 4px 10px; border-radius: 14px;
         font-weight: 700; display:inline-block; }
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
    """
    Odds endpoint: /odds?fixture=ID
    - bookmaker: padrão 8 (muitas vezes é Bet365 na API-Sports, mas isso pode variar)
    Retorna lista de odds (response).
    """
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
# Simple Poisson Model
# =============================
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def prob_over_total(lam_home: float, lam_away: float, line: float, max_goals: int = 10) -> float:
    threshold = math.floor(line)  # 2.5 -> <=2 is under
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


def compute_team_form(team_id: int, fixtures_ft: List[Dict]) -> Tuple[int, float, float, float, float]:
    """
    Retorna:
    n, gf_per_game, ga_per_game, gf_home_per_game (ou -1), ga_home_per_game (ou -1),
    e idem away (simplificado abaixo)
    """
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
        return 0, 0.0, 0.0, -1.0, -1.0

    gf_pg = gf / n
    ga_pg = ga / n
    gf_home_pg = (gf_home / n_home) if n_home > 0 else -1.0
    ga_home_pg = (ga_home / n_home) if n_home > 0 else -1.0
    gf_away_pg = (gf_away / n_away) if n_away > 0 else -1.0
    ga_away_pg = (ga_away / n_away) if n_away > 0 else -1.0

    # devolvemos home/away via tupla estendida (usaremos em estimate)
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
    w = clamp(n_eff / 10.0, 0.25, 1.0)  # smoothing mínimo
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
# Odds parsing (API response varia, então buscamos por nomes)
# =============================
def _extract_market_odds(odds_response: List[Dict], market_name_keywords: List[str], selection_keywords: List[str]) -> Optional[float]:
    """
    Procura odds em odds_response de forma robusta:
    - market_name_keywords: palavras que devem aparecer no nome do mercado
    - selection_keywords: palavras que devem aparecer no nome da seleção (bet)
    """
    try:
        if not odds_response:
            return None

        # API-Football: response -> list items -> bookmakers -> bets -> values
        item = odds_response[0]  # normalmente 1 item por fixture
        bookmakers = item.get("bookmakers", [])
        for bk in bookmakers:
            bets = bk.get("bets", [])
            for b in bets:
                name = (b.get("name") or "").lower()
                if all(k.lower() in name for k in market_name_keywords):
                    for v in b.get("values", []):
                        val_name = (v.get("value") or "").lower()
                        if all(sk.lower() in val_name for sk in selection_keywords):
                            odd = v.get("odd")
                            if odd is None:
                                continue
                            return float(odd)
        return None
    except Exception:
        return None


def get_market_odds(fixture_id: int, market: str) -> Dict[str, Optional[float]]:
    """
    Retorna odds relevantes para o mercado solicitado.
    """
    resp = get_odds_for_fixture(fixture_id)
    out: Dict[str, Optional[float]] = {}

    if market == "1X2":
        out["Home"] = _extract_market_odds(resp, ["match winner"], ["home"])
        out["Draw"] = _extract_market_odds(resp, ["match winner"], ["draw"])
        out["Away"] = _extract_market_odds(resp, ["match winner"], ["away"])

    elif market == "BTTS":
        out["Yes"] = _extract_market_odds(resp, ["both teams score"], ["yes"])
        out["No"] = _extract_market_odds(resp, ["both teams score"], ["no"])

    elif market == "Over 1.5":
        out["Over 1.5"] = _extract_market_odds(resp, ["goals over/under"], ["over 1.5"])
        out["Under 1.5"] = _extract_market_odds(resp, ["goals over/under"], ["under 1.5"])

    elif market == "Over 2.5":
        out["Over 2.5"] = _extract_market_odds(resp, ["goals over/under"], ["over 2.5"])
        out["Under 2.5"] = _extract_market_odds(resp, ["goals over/under"], ["under 2.5"])

    elif market == "DC+Over1.5":
        # Muitas casas têm "Double Chance" e "Over/Under" separados; combinar odds exatas depende do book.
        # Aqui retornamos só DC odds (1X, 12, X2). Over ficará do market Over 1.5.
        out["1X"] = _extract_market_odds(resp, ["double chance"], ["home/draw"]) or _extract_market_odds(resp, ["double chance"], ["1x"])
        out["12"] = _extract_market_odds(resp, ["double chance"], ["home/away"]) or _extract_market_odds(resp, ["double chance"], ["12"])
        out["X2"] = _extract_market_odds(resp, ["double chance"], ["draw/away"]) or _extract_market_odds(resp, ["double chance"], ["x2"])

    elif market == "DC+Over2.5":
        out["1X"] = _extract_market_odds(resp, ["double chance"], ["home/draw"]) or _extract_market_odds(resp, ["double chance"], ["1x"])
        out["12"] = _extract_market_odds(resp, ["double chance"], ["home/away"]) or _extract_market_odds(resp, ["double chance"], ["12"])
        out["X2"] = _extract_market_odds(resp, ["double chance"], ["draw/away"]) or _extract_market_odds(resp, ["double chance"], ["x2"])

    return out


# =============================
# Pick generation
# =============================
def build_pick_cards(
    fixtures: List[Dict],
    last_n_form: int,
    home_adv: float,
    one_per_league: bool,
    min_odd: float,
    zebra_min_odd: float,
    max_picks: int,
) -> Dict[str, List[Dict]]:
    """
    Retorna picks por categoria (abas):
    - 1X2
    - BTTS
    - Over 1.5
    - Over 2.5
    - DC+Over1.5
    - DC+Over2.5
    - Zebras
    """
    results = {k: [] for k in ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5", "Zebras"]}

    used_leagues = {k: set() for k in results.keys()}

    for fx in fixtures:
        try:
            fixture_id = int(fx["fixture"]["id"])
            league_id = int(fx["league"]["id"])
            league_name = fx["league"]["name"]
            home = fx["teams"]["home"]
            away = fx["teams"]["away"]
            home_id, away_id = int(home["id"]), int(away["id"])

            # Forma e lambdas
            home_last = get_last_team_fixtures(home_id, last=last_n_form, status="FT")
            away_last = get_last_team_fixtures(away_id, last=last_n_form, status="FT")
            home_form = compute_team_form(home_id, home_last)
            away_form = compute_team_form(away_id, away_last)
            lam_h, lam_a, ev = estimate_lambdas(home_form, away_form, home_adv=home_adv)

            # Odds (buscamos quando necessário)
            # Para performance: odds endpoint é caro; aqui chamamos 1x e extraímos vários mercados.
            odds_resp = get_odds_for_fixture(fixture_id)

            dt_local = parse_fixture_time_local(fx)
            time_str = dt_local.strftime("%H:%M") if dt_local else "??:??"

            def add(category: str, pick: Dict):
                if one_per_league and league_id in used_leagues[category]:
                    return
                results[category].append(pick)
                used_leagues[category].add(league_id)

            # -------------- OVER 1.5 / 2.5 --------------
            p_o15 = prob_over_total(lam_h, lam_a, 1.5)
            p_o25 = prob_over_total(lam_h, lam_a, 2.5)
            odd_o15 = _extract_market_odds(odds_resp, ["goals over/under"], ["over 1.5"])
            odd_o25 = _extract_market_odds(odds_resp, ["goals over/under"], ["over 2.5"])

            if odd_o15 and odd_o15 >= min_odd:
                fo = fair_odds(p_o15) or 0.0
                edge = (odd_o15 / fo) - 1.0 if fo > 0 else None
                add("Over 1.5", {
                    "league_id": league_id, "league": league_name, "time": time_str,
                    "match": f"{home['name']} vs {away['name']}",
                    "pick": "Over 1.5",
                    "prob": p_o15, "odd": odd_o15, "fair": fo, "edge": edge,
                    "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                })

            if odd_o25 and odd_o25 >= min_odd:
                fo = fair_odds(p_o25) or 0.0
                edge = (odd_o25 / fo) - 1.0 if fo > 0 else None
                add("Over 2.5", {
                    "league_id": league_id, "league": league_name, "time": time_str,
                    "match": f"{home['name']} vs {away['name']}",
                    "pick": "Over 2.5",
                    "prob": p_o25, "odd": odd_o25, "fair": fo, "edge": edge,
                    "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                })

            # -------------- BTTS --------------
            p_btts = prob_btts(lam_h, lam_a)
            odd_btts_yes = _extract_market_odds(odds_resp, ["both teams score"], ["yes"])
            if odd_btts_yes and odd_btts_yes >= min_odd:
                fo = fair_odds(p_btts) or 0.0
                edge = (odd_btts_yes / fo) - 1.0 if fo > 0 else None
                add("BTTS", {
                    "league_id": league_id, "league": league_name, "time": time_str,
                    "match": f"{home['name']} vs {away['name']}",
                    "pick": "BTTS (Yes)",
                    "prob": p_btts, "odd": odd_btts_yes, "fair": fo, "edge": edge,
                    "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                })

            # -------------- 1X2 --------------
            pH, pD, pA = prob_1x2(lam_h, lam_a)
            odd_home = _extract_market_odds(odds_resp, ["match winner"], ["home"])
            odd_draw = _extract_market_odds(odds_resp, ["match winner"], ["draw"])
            odd_away = _extract_market_odds(odds_resp, ["match winner"], ["away"])

            # Escolhe a melhor opção do 1X2 por edge (se houver odds)
            candidates = []
            if odd_home and odd_home >= min_odd:
                candidates.append(("Home", pH, odd_home))
            if odd_draw and odd_draw >= min_odd:
                candidates.append(("Draw", pD, odd_draw))
            if odd_away and odd_away >= min_odd:
                candidates.append(("Away", pA, odd_away))

            best = None
            best_edge = -999
            for name, p, odd in candidates:
                fo = fair_odds(p) or 0.0
                if fo <= 0:
                    continue
                edge = (odd / fo) - 1.0
                if edge > best_edge:
                    best_edge = edge
                    best = (name, p, odd, fo, edge)

            if best:
                name, p, odd, fo, edge = best
                add("1X2", {
                    "league_id": league_id, "league": league_name, "time": time_str,
                    "match": f"{home['name']} vs {away['name']}",
                    "pick": f"1X2: {name}",
                    "prob": p, "odd": odd, "fair": fo, "edge": edge,
                    "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                })

            # -------------- Dupla Chance + Over (aproximação) --------------
            # Como odds combinadas raramente vêm prontas, fazemos aproximação:
            # P(1X & Over) ~ P(1X) * P(Over) (não é independente na prática)
            # Aqui mostramos prob e exige que existam odds de DC e Over.
            odd_1x = _extract_market_odds(odds_resp, ["double chance"], ["home/draw"]) or _extract_market_odds(odds_resp, ["double chance"], ["1x"])
            odd_x2 = _extract_market_odds(odds_resp, ["double chance"], ["draw/away"]) or _extract_market_odds(odds_resp, ["double chance"], ["x2"])
            odd_12 = _extract_market_odds(odds_resp, ["double chance"], ["home/away"]) or _extract_market_odds(odds_resp, ["double chance"], ["12"])

            p_1x = pH + pD
            p_x2 = pA + pD
            p_12 = pH + pA

            # Over 1.5
            if odd_o15 and odd_o15 >= min_odd:
                for dc_name, p_dc, odd_dc in [("1X", p_1x, odd_1x), ("X2", p_x2, odd_x2), ("12", p_12, odd_12)]:
                    if not odd_dc or odd_dc < min_odd:
                        continue
                    p_combo = clamp(p_dc * p_o15, 0.0, 1.0)
                    # Odds combinadas reais não são multiplicação; aqui só filtramos se existirem odds do DC e do Over.
                    # Para decisão final profissional, você precisa de odds combinadas do bookmaker (se disponíveis).
                    fo = fair_odds(p_combo) or 0.0
                    # Usamos odd "proxy" (odd_dc * odd_o15) para ranking, mas sinalizamos que é proxy
                    odd_proxy = odd_dc * odd_o15
                    if odd_proxy >= min_odd:
                        edge = (odd_proxy / fo) - 1.0 if fo > 0 else None
                        add("DC+Over1.5", {
                            "league_id": league_id, "league": league_name, "time": time_str,
                            "match": f"{home['name']} vs {away['name']}",
                            "pick": f"{dc_name} + Over 1.5 (odd proxy)",
                            "prob": p_combo, "odd": odd_proxy, "fair": fo, "edge": edge,
                            "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                        })

            # Over 2.5
            if odd_o25 and odd_o25 >= min_odd:
                for dc_name, p_dc, odd_dc in [("1X", p_1x, odd_1x), ("X2", p_x2, odd_x2), ("12", p_12, odd_12)]:
                    if not odd_dc or odd_dc < min_odd:
                        continue
                    p_combo = clamp(p_dc * p_o25, 0.0, 1.0)
                    fo = fair_odds(p_combo) or 0.0
                    odd_proxy = odd_dc * odd_o25
                    if odd_proxy >= min_odd:
                        edge = (odd_proxy / fo) - 1.0 if fo > 0 else None
                        add("DC+Over2.5", {
                            "league_id": league_id, "league": league_name, "time": time_str,
                            "match": f"{home['name']} vs {away['name']}",
                            "pick": f"{dc_name} + Over 2.5 (odd proxy)",
                            "prob": p_combo, "odd": odd_proxy, "fair": fo, "edge": edge,
                            "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                        })

            # -------------- Zebras (odds >= 4.0) --------------
            # Zebra: pick é um dos lados do 1X2 com odd >= zebra_min_odd e prob não totalmente absurda.
            zebra_candidates = []
            if odd_home and odd_home >= zebra_min_odd:
                zebra_candidates.append(("Home", pH, odd_home))
            if odd_away and odd_away >= zebra_min_odd:
                zebra_candidates.append(("Away", pA, odd_away))
            # draw zebra muitas vezes é 3-4; você pediu zebra >=4 então draw entra se >=4
            if odd_draw and odd_draw >= zebra_min_odd:
                zebra_candidates.append(("Draw", pD, odd_draw))

            # escolhe zebra por edge
            zb_best = None
            zb_edge = -999
            for name, p, odd in zebra_candidates:
                fo = fair_odds(p) or 0.0
                if fo <= 0:
                    continue
                edge = (odd / fo) - 1.0
                if edge > zb_edge:
                    zb_edge = edge
                    zb_best = (name, p, odd, fo, edge)

            if zb_best:
                name, p, odd, fo, edge = zb_best
                add("Zebras", {
                    "league_id": league_id, "league": league_name, "time": time_str,
                    "match": f"{home['name']} vs {away['name']}",
                    "pick": f"Zebra: {name}",
                    "prob": p, "odd": odd, "fair": fo, "edge": edge,
                    "ev": ev, "lam": (lam_h, lam_a), "fixture_id": fixture_id
                })

        except Exception:
            continue

    # Ordena cada categoria por edge (maior primeiro), depois prob
    for k in results.keys():
        results[k] = sorted(
            results[k],
            key=lambda x: (
                -999 if x.get("edge") is None else -x["edge"],
                -x.get("prob", 0.0),
            ),
        )[:max_picks]

    return results


def render_picks(picks: List[Dict], min_odd: float, zebra_min_odd: float):
    if not picks:
        st.info("Sem picks que passem nos filtros (odds mínimas / dados insuficientes / odds não disponíveis).")
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
    Nota: Dupla Chance + Over usa odd proxy (multiplicação) quando a odd combinada não está disponível no bookmaker.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )


def main():
    now_local = datetime.now(LOCAL_TZ)

    st.title("🛡️ Elite Scanner 4.0 — Top 10 por Mercado (Odds + Prob)")
    st.write(f"📍 Inhassoro/Maputo | 🕒 {now_local.strftime('%H:%M:%S')}")

    with st.sidebar:
        st.subheader("Controles simples")
        auto_tomorrow_if_empty = st.checkbox("Se hoje não tiver jogos futuros, usar amanhã", value=True)
        max_picks = st.slider("Top picks por aba", 5, 20, 10, 1)
        one_per_league = st.checkbox("1 pick por liga principal", value=True)
        last_n_form = st.slider("Forma (últimos jogos FT)", 4, 20, 10, 1)
        home_adv = st.slider("Vantagem de casa", 1.00, 1.20, 1.08, 0.01)
        min_odd = st.number_input("Odd mínima (normais)", value=1.30, min_value=1.01, step=0.01)
        zebra_min_odd = st.number_input("Odd mínima (zebras)", value=4.00, min_value=2.00, step=0.10)

        st.caption("Se odds não aparecerem, sua API/plano pode não incluir odds ou o bookmaker escolhido não tem linhas para esse jogo.")

    date_today = now_local.date()
    date_to_use = date_today

    fixtures = get_fixtures_by_date(date_to_use.strftime("%Y-%m-%d"))
    fixtures = [fx for fx in fixtures if is_future_fixture(fx, now_local)]

    if not fixtures and auto_tomorrow_if_empty:
        date_to_use = (now_local + timedelta(days=1)).date()
        fixtures = get_fixtures_by_date(date_to_use.strftime("%Y-%m-%d"))
        # amanhã: não filtra por "futuro" relativo a agora (mas pode manter)
        fixtures = [fx for fx in fixtures if parse_fixture_time_local(fx) is not None]

    if not fixtures:
        st.error("Nenhum jogo encontrado para as próximas 24h com os filtros atuais.")
        return

    st.markdown(
        f"🗓️ Data analisada: <span class='badge'>{date_to_use.strftime('%d/%m/%Y')}</span>",
        unsafe_allow_html=True,
    )

    if st.button("🚀 GERAR TOP 10 AUTOMÁTICO"):
        # Gera picks
        results = build_pick_cards(
            fixtures=fixtures,
            last_n_form=last_n_form,
            home_adv=home_adv,
            one_per_league=one_per_league,
            min_odd=min_odd,
            zebra_min_odd=zebra_min_odd,
            max_picks=max_picks,
        )

        tabs = st.tabs(["🏆 1X2", "⚽ BTTS", "📈 Over 1.5", "📈 Over 2.5", "👥 DC+O1.5", "👥 DC+O2.5", "🟣 Zebras"])
        with tabs[0]:
            render_picks(results["1X2"], min_odd, zebra_min_odd)
        with tabs[1]:
            render_picks(results["BTTS"], min_odd, zebra_min_odd)
        with tabs[2]:
            render_picks(results["Over 1.5"], min_odd, zebra_min_odd)
        with tabs[3]:
            render_picks(results["Over 2.5"], min_odd, zebra_min_odd)
        with tabs[4]:
            render_picks(results["DC+Over1.5"], min_odd, zebra_min_odd)
        with tabs[5]:
            render_picks(results["DC+Over2.5"], min_odd, zebra_min_odd)
        with tabs[6]:
            render_picks(results["Zebras"], min_odd, zebra_min_odd)


if __name__ == "__main__":
    main()
