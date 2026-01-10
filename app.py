import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st
from openai import OpenAI

# ============================================================
# SECRETS (Streamlit Cloud -> Manage app -> Settings -> Secrets)
# ============================================================
# FOOTBALL_API_MODE = "allsports"
# ALLSPORTS_API_KEY = "SUA_CHAVE_ALLSPORTS"
# OPENAI_API_KEY    = "SUA_CHAVE_OPENAI"   # (opcional, só se quiser IA)
# ============================================================

# =============================
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
MAX_LEAGUES_DEFAULT = 20
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
# OpenAI (Passo 3)
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
Você é um analista profissional de apostas esportivas. Explique de forma curta, objetiva e útil o pick abaixo.
Regras:
- 4 a 7 linhas no máximo.
- Linguagem simples.
- Não invente dados externos.
- Inclua 1 frase de risco (ex.: “principal risco: ...”).
- Conclua com uma confiança estimada em % (não mais que 90%).

Jogo: {match}
Liga: {league}
Hora: {time_str}
Mercado: {market}
Pick: {pick_name}

Modelo:
- Probabilidade: {prob:.3f}
- Odd mercado: {odd:.2f}
- Odd justa: {fair:.2f}
- Edge: {edge_txt}
- Evidência: {ev}
- Lambdas: λ_home={lam_h:.2f}, λ_away={lam_a:.2f}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Responda sempre em português e seja muito conciso e prático."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        txt = resp.choices[0].message.content or ""
        return _short(txt, 700)
    except Exception:
        return "IA indisponível no momento para este pick."


# =============================
# AllSportsAPI low-level
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
# Normalização (AllSports -> estrutura do app)
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

    for hk, ak in [
        ("event_home_final_result", "event_away_final_result"),
        ("home_final_result", "away_final_result"),
        ("event_home_result", "event_away_result"),
    ]:
        h = _as_int(ev.get(hk))
        a = _as_int(ev.get(ak))
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
# Data access (AllSports)
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
        {
            "teamId": str(team_id),
            "from": start.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "timezone": "Africa/Maputo",
        },
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
# Poisson Model
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
# Forma ponderada por recência
# =============================
def compute_team_form_weighted(
    team_id: int,
    fixtures_ft: List[Dict],
    decay: float = 0.85,
) -> Tuple[int, float, float, float, float, float, float]:
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
# Odds mapping (AllSports)
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
# PASSO 4 — TOP TIPS SCORE (melhor ranking)
# =============================
def _ev_weight(ev: str) -> float:
    ev = (ev or "").upper().strip()
    if ev == "ALTA":
        return 1.0
    if ev == "MÉDIA":
        return 0.6
    return 0.25


def _odd_penalty(odd: float, zebra_threshold: float = 4.0) -> float:
    if odd is None:
        return 0.2
    if odd <= zebra_threshold:
        return 0.0
    return min(0.40, (odd - zebra_threshold) / 20.0)


def top_tip_score(p: Dict, zebra_threshold: float = 4.0) -> float:
    edge = p.get("edge")
    prob = float(p.get("prob") or 0.0)
    odd = float(p.get("odd") or 0.0)
    ev = p.get("ev", "BAIXA")

    edge_val = float(edge) if edge is not None else 0.0
    ev_w = _ev_weight(ev)
    penalty = _odd_penalty(odd, zebra_threshold=zebra_threshold)

    # pesos: edge principal, prob reforça estabilidade, evidência reforça confiança,
    # penaliza odds muito altas para Top Tips não virar só zebras.
    score = (1.8 * edge_val) + (0.9 * prob) + (0.5 * ev_w) - (1.0 * penalty)
    return score


# =============================
# Picks per market (com progress callback)
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

                for dc_name, p_dc, odd_dc in [
                    ("1X", p_1x, odd_1x),
                    ("X2", p_x2, odd_x2),
                    ("12", p_12, odd_12),
                ]:
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
        key=lambda x: (
            -999 if x.get("edge") is None else -x["edge"],
            -x.get("prob", 0.0),
        ),
    )[:max_picks]

    return picks


def render_picks(picks: List[Dict], ai_enabled: bool, ai_max: int):
    if not picks:
        st.info("Sem picks que passem nos filtros (ou odds indisponíveis).")
        return

    ai_count = 0

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
    Prob(modelo): <b>{p['prob']:.3f}</b> | Odd: <b>{p['odd']:.2f}</b> | Odd justa: <b>{p['fair']:.2f}</b> | Edge: <b>{edge_txt}</b><br/>
    Evidência: <b>{p['ev']}</b> | λ: {p['lam'][0]:.2f}-{p['lam'][1]:.2f}
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

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
                st.markdown(
                    "<div class='small'>IA: limite de explicações desta aba atingido (para economizar). Ajuste no sidebar.</div>",
                    unsafe_allow_html=True,
                )


# =============================
# TOP TIPS (6-10 juntos) — PASSO 4 aplicado
# =============================
def build_top_tips(
    fixtures: List[Dict],
    last_n_form: int,
    home_adv: float,
    min_odd: float,
    zebra_min_odd: float,
    top_n: int,
) -> List[Dict]:
    markets = ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5", "Zebras"]

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
            max_picks=30,
            progress_cb=None,
        )
        all_candidates.extend(cand)

    pbar.progress(100)
    ptxt.markdown("<div class='ptext'>A selecionar Top Tips...</div>", unsafe_allow_html=True)

    # PASSO 4: ordena por score (melhor que só edge/prob)
    all_candidates = sorted(
        all_candidates,
        key=lambda p: top_tip_score(p, zebra_threshold=zebra_min_odd),
        reverse=True,
    )

    # 1 pick por liga (diversidade)
    final: List[Dict] = []
    used_leagues = set()
    for c in all_candidates:
        lid = c.get("league_id")
        if lid in used_leagues:
            continue
        final.append(c)
        used_leagues.add(lid)
        if len(final) >= top_n:
            break

    ptxt.markdown("<div class='ptext'>Concluído.</div>", unsafe_allow_html=True)
    return final


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

        # Pool 50–150 (performance)
        pool_size = st.slider("Pool de jogos para análise", 50, 150, 100, 10)

        top_tips_n = st.slider("Top Tips (6–10)", 6, 10, 8, 1)

        max_picks = st.slider("Top picks por aba", 5, 20, 10, 1)
        one_per_league = st.checkbox("1 pick por liga", value=True)
        max_leagues = st.slider("Máx. ligas/campeonatos", 5, 30, MAX_LEAGUES_DEFAULT, 1)

        last_n_form = st.slider("Forma (últimos jogos FT)", 4, 20, 10, 1)
        home_adv = st.slider("Vantagem de casa", 1.00, 1.20, 1.08, 0.01)

        min_odd = st.number_input("Odd mínima (normais)", value=1.30, min_value=1.01, step=0.01)
        zebra_min_odd = st.number_input("Odd mínima (zebras)", value=4.00, min_value=2.00, step=0.10)

        st.divider()
        st.subheader("IA")
        ai_enabled = st.checkbox("Ativar IA para explicar picks", value=True)
        ai_max = st.slider("Máx. explicações por aba", 1, 10, 5, 1)

        ai_ok = True
        if ai_enabled and not st.secrets.get("OPENAI_API_KEY"):
            ai_ok = False
            st.warning("IA ativada, mas falta OPENAI_API_KEY nos Secrets.")

        debug = st.checkbox("Mostrar diagnóstico (debug)", value=False)

    # Fixtures hoje (futuros)
    date_to_use = now_local.date()
    date_str = date_to_use.strftime("%Y-%m-%d")
    fixtures_raw = get_fixtures_by_date(date_str)
    fixtures = [fx for fx in fixtures_raw if is_future_fixture(fx, now_local)]

    # Amanhã só se: hoje tinha jogos mas nenhum futuro
    if auto_tomorrow_if_empty and (len(fixtures_raw) > 0) and (len(fixtures) == 0):
        date_to_use = (now_local + timedelta(days=1)).date()
        date_str = date_to_use.strftime("%Y-%m-%d")
        fixtures_raw = get_fixtures_by_date(date_str)
        fixtures = [fx for fx in fixtures_raw if parse_fixture_time_local(fx) is not None]

    if not fixtures:
        st.error("Nenhum jogo encontrado (ou odds indisponíveis).")
        return

    # Limita ligas
    fixtures = limit_to_top_leagues(fixtures, max_leagues=max_leagues)

    # Ordena por hora e limita pool (50–150)
    fixtures = sorted(fixtures, key=lambda fx: parse_fixture_time_local(fx) or datetime.max)
    fixtures = fixtures[:pool_size]

    if debug:
        with st.expander("Diagnóstico (fixtures/tempo)"):
            st.write("Provider:", provider_mode())
            st.write("Data usada:", date_str)
            st.write("Agora (local):", now_local.isoformat())
            st.write("Fixtures brutos:", len(fixtures_raw))
            st.write("Fixtures futuros (antes do limite de ligas):", len([fx for fx in fixtures_raw if is_future_fixture(fx, now_local)]))
            st.write("Pool final (após limite ligas + corte):", len(fixtures))

    st.markdown(
        f"🗓️ Data analisada: <span class='badge'>{date_to_use.strftime('%d/%m/%Y')}</span>",
        unsafe_allow_html=True,
    )
    st.caption(f"Pool final: {len(fixtures)} jogos | Máx. ligas: {max_leagues}")

    tabs = st.tabs(
        ["⭐ Top Tips", "🏆 1X2", "⚽ BTTS", "📈 Over 1.5", "📈 Over 2.5", "👥 DC+O1.5", "👥 DC+O2.5", "🟣 Zebras"]
    )

    # ===== Top Tips =====
    with tabs[0]:
        st.subheader("⭐ Top Tips do Dia (misturado)")
        if st.button(f"🚀 Gerar Top Tips ({top_tips_n})", key="btn_toptips"):
            tips = build_top_tips(
                fixtures=fixtures,
                last_n_form=last_n_form,
                home_adv=home_adv,
                min_odd=min_odd,
                zebra_min_odd=zebra_min_odd,
                top_n=top_tips_n,
            )
            st.session_state["toptips"] = tips

        render_picks(st.session_state.get("toptips", []), ai_enabled=ai_enabled and ai_ok, ai_max=ai_max)

    # ===== Outras abas =====
    markets = ["1X2", "BTTS", "Over 1.5", "Over 2.5", "DC+Over1.5", "DC+Over2.5", "Zebras"]
    for tab, market in zip(tabs[1:], markets):
        with tab:
            st.subheader(f"Mercado: {market}")
            col1, col2 = st.columns([1, 2])

            with col1:
                if st.button(f"🚀 Gerar Top {max_picks}", key=f"btn_{market}"):
                    pbar = st.progress(0)
                    ptxt = st.empty()

                    def cb(i, tot):
                        pct = int(i * 100 / max(1, tot))
                        pbar.progress(min(100, pct))
                        ptxt.markdown(f"<div class='ptext'>A analisar {i}/{tot} jogos...</div>", unsafe_allow_html=True)

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
                            progress_cb=cb,
                        )
                        st.session_state[f"picks_{market}"] = picks
                        pbar.progress(100)
                        ptxt.markdown("<div class='ptext'>Concluído.</div>", unsafe_allow_html=True)
                    except Exception as e:
                        ptxt.markdown(f"<div class='ptext'>Falha: {e}</div>", unsafe_allow_html=True)

            with col2:
                st.write("Critérios: odds mínimas + ranking por edge. Top Tips usa score avançado (Passo 4).")

            render_picks(st.session_state.get(f"picks_{market}", []), ai_enabled=ai_enabled and ai_ok, ai_max=ai_max)


if __name__ == "__main__":
    main()
