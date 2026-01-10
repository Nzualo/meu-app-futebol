import math
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st

# =============================
# OPTIONAL: clock refresh
# =============================
try:
    from streamlit_autorefresh import st_autorefresh
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
# CONFIG
# =============================
LOCAL_TZ = pytz.timezone("Africa/Maputo")
LOCAL_TZ_NAME = "Africa/Maputo"
API_SPORTS_BASE = "https://v3.football.api-sports.io"

st.set_page_config(page_title="Melhores Palpites do Dia", layout="wide")

# =============================
# Session
# =============================
if "pause_refresh" not in st.session_state:
    st.session_state["pause_refresh"] = False
if "rows_1x2" not in st.session_state:
    st.session_state["rows_1x2"] = []

# =============================
# CSS
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
.smallnote { color:#aab6c5; font-size: 0.85rem; margin-top: 6px; }
</style>
""",
    unsafe_allow_html=True,
)

# =============================
# Secrets helpers
# =============================
def _sec_required(name: str) -> str:
    v = st.secrets.get(name)
    if v is None or str(v).strip() == "":
        raise RuntimeError(f"Missing secret: {name}")
    return str(v).strip()

def _sec_optional(name: str, default: str = "") -> str:
    v = st.secrets.get(name, default)
    return str(v).strip() if v is not None else default

def has_secret(name: str) -> bool:
    v = st.secrets.get(name)
    return v is not None and str(v).strip() != ""

# =============================
# Utils
# =============================
def parse_iso_local(iso: str) -> Optional[datetime]:
    try:
        dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt_utc.astimezone(LOCAL_TZ)
    except Exception:
        return None

def norm_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

# =============================
# API-SPORTS
# =============================
def apisports_headers() -> Dict[str, str]:
    return {"x-apisports-key": _sec_required("APISPORTS_KEY")}

def apisports_get(path: str, params: Dict[str, str], timeout: int = 18) -> Dict:
    r = requests.get(f"{API_SPORTS_BASE}{path}", headers=apisports_headers(), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=60 * 30)
def apisports_leagues_current() -> List[Dict]:
    # Lista ligas atuais para resolver IDs por nome (sem hardcode)
    data = apisports_get("/leagues", {"current": "true"})
    return data.get("response", []) or []

@st.cache_data(ttl=60 * 10)
def apisports_fixtures_by_date(date_yyyy_mm_dd: str) -> Dict:
    # timezone Maputo ajuda a API a retornar datas corretamente
    return apisports_get("/fixtures", {"date": date_yyyy_mm_dd, "timezone": LOCAL_TZ_NAME})

@st.cache_data(ttl=60 * 10)
def apisports_fixtures_window(from_yyyy_mm_dd: str, to_yyyy_mm_dd: str) -> Dict:
    return apisports_get("/fixtures", {"from": from_yyyy_mm_dd, "to": to_yyyy_mm_dd, "timezone": LOCAL_TZ_NAME})

@st.cache_data(ttl=60 * 60)
def apisports_team_last(team_id: int, last: int = 10) -> List[Dict]:
    data = apisports_get("/fixtures", {"team": str(team_id), "last": str(last), "status": "FT", "timezone": LOCAL_TZ_NAME})
    return data.get("response", []) or []

# Odds (API-SPORTS) – opcional, pode vir vazio no plano free
@st.cache_data(ttl=60 * 10)
def apisports_odds_fixture(fixture_id: int) -> List[Dict]:
    data = apisports_get("/odds", {"fixture": str(fixture_id)})
    return data.get("response", []) or []

def apisports_extract_market(odds_resp: List[Dict], market_name: str, selection_value: str) -> Optional[float]:
    if not odds_resp:
        return None
    try:
        item = odds_resp[0]
        for bk in item.get("bookmakers", []):
            for bet in bk.get("bets", []):
                if (bet.get("name") or "").strip().lower() == market_name.strip().lower():
                    for v in bet.get("values", []):
                        if (v.get("value") or "").strip().lower() == selection_value.strip().lower():
                            odd = v.get("odd")
                            return float(odd) if odd is not None else None
    except Exception:
        pass
    return None

# =============================
# Model
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
# IA (optional)
# =============================
def openai_client() -> Optional["OpenAI"]:
    if not HAS_OPENAI:
        return None
    if not has_secret("OPENAI_API_KEY"):
        return None
    return OpenAI(api_key=_sec_required("OPENAI_API_KEY"))

@st.cache_data(ttl=60 * 60)
def ai_explain(home: str, away: str, league: str, pick: str, prob: float, odd: Optional[float], ev: str) -> str:
    c = openai_client()
    if c is None:
        return "IA indisponível (confira requirements: openai, e OPENAI_API_KEY nos secrets)."
    odd_txt = f"{odd:.2f}" if odd is not None else "—"
    prompt = f"""
Explique este palpite em PT (máx 6 linhas), sem prometer ganhos.
Jogo: {home} vs {away}
Liga: {league}
Pick: {pick}
Prob: {prob:.3f}
Odd: {odd_txt}
Evidência: {ev}
Inclua 2 razões quantitativas + 1 risco.
"""
    r = c.chat.completions.create(
        model=_sec_optional("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    return (r.choices[0].message.content or "").strip()

# =============================
# TOP leagues resolver (10 ligas)
# =============================
TOP_LEAGUE_PATTERNS = [
    # Europa
    ("Premier League", ["premier league", "england"]),
    ("La Liga", ["la liga", "spain"]),
    ("Serie A", ["serie a", "italy"]),
    ("Bundesliga", ["bundesliga", "germany"]),
    ("Ligue 1", ["ligue 1", "france"]),
    ("UEFA Champions League", ["uefa champions league"]),
    # Américas
    ("Brasileirão Série A", ["serie a", "brazil"]),
    ("Argentina Primera", ["primera division", "argentina"]),
    ("MLS", ["mls", "usa"]),
    ("Copa Libertadores", ["copa libertadores", "libertadores"]),
]

def resolve_top_league_ids() -> Dict[str, int]:
    """
    Busca /leagues?current=true e tenta achar 1 liga por padrão.
    Retorna: {nome_amigavel: league_id}
    """
    leagues = apisports_leagues_current()
    out: Dict[str, int] = {}

    for friendly, keys in TOP_LEAGUE_PATTERNS:
        want = [k.lower() for k in keys]
        found_id = None

        for item in leagues:
            lg = item.get("league", {}) or {}
            ct = item.get("country", {}) or {}
            name = norm_text(lg.get("name", ""))
            country = norm_text(ct.get("name", ""))
            # string "alvo"
            hay = f"{name} {country}"

            ok = True
            for w in want:
                if w not in hay:
                    ok = False
                    break
            if ok:
                found_id = lg.get("id")
                break

        if found_id:
            out[friendly] = int(found_id)

    return out

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
  <div class="meta"><b>{r['time']}</b> | <b>{r['league']}</b></div>
  <div class="pickline"><b>{r['match']}</b></div>
  <div class="pickline">Pick: <b>{r['pick']}</b></div>
  <div class="kpi">
    <span>Prob: <b>{r['prob']:.3f}</b></span>
    <span>Odd: <b>{odd_txt}</b></span>
    <span>Justa: <b>{fair_txt}</b></span>
    <span>Edge: <b>{edge_txt}</b></span>
    <span>Evid.: <b>{r['ev']}</b></span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        if use_ai:
            with st.expander("IA: análise", expanded=False):
                st.write(ai_explain(r["home"], r["away"], r["league"], r["pick"], r["prob"], r["odd"], r["ev"]))

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

    with st.expander("Diagnóstico de APIs (secrets)", expanded=False):
        st.write({
            "APISPORTS_KEY": has_secret("APISPORTS_KEY"),
            "OPENAI_API_KEY": has_secret("OPENAI_API_KEY"),
            "timezone_used": LOCAL_TZ_NAME,
        })

    with st.sidebar:
        st.subheader("Configuração")
        modo = st.selectbox("Buscar jogos", ["Jogos do dia (Maputo)", "Próximas 24h"], index=0)
        top_picks = st.slider("Top picks", 5, 20, 10, 1)
        last_n = st.slider("Forma (últimos FT)", 4, 20, 10, 1)
        home_adv = st.slider("Vantagem de casa", 1.00, 1.20, 1.08, 0.01)
        min_odd = st.number_input("Odd mínima (se houver)", value=1.30, min_value=1.01, step=0.01)
        use_ai = st.checkbox("IA ligada", value=HAS_OPENAI and has_secret("OPENAI_API_KEY"))

        st.caption("Nota: odds podem vir vazias no plano free; o modelo ainda gera probabilidades.")

    # Resolve TOP 10 ligas (IDs dinâmicos)
    top_map = resolve_top_league_ids()
    if not top_map:
        st.error("Não consegui resolver as ligas TOP via /leagues. Verifique se a API-SPORTS está a responder.")
        return

    # Permitir ao usuário ajustar as ligas (por padrão: 10)
    default_names = list(top_map.keys())[:10]
    selected_names = st.multiselect("TOP ligas/campeonatos (máx 10)", options=list(top_map.keys()), default=default_names)
    selected_names = selected_names[:10]
    selected_ids = {top_map[n] for n in selected_names}

    # Buscar fixtures
    fixtures_raw: List[Dict] = []
    if modo == "Jogos do dia (Maputo)":
        date_str = now_local.strftime("%Y-%m-%d")
        raw = apisports_fixtures_by_date(date_str)
        fixtures_raw = raw.get("response", []) or []
    else:
        from_str = now_local.strftime("%Y-%m-%d")
        to_str = (now_local + timedelta(days=2)).strftime("%Y-%m-%d")
        raw = apisports_fixtures_window(from_str, to_str)
        fixtures_raw = raw.get("response", []) or []

    # filtrar por ligas TOP
    fixtures = []
    for f in fixtures_raw:
        try:
            league_id = int(f["league"]["id"])
        except Exception:
            continue
        if league_id in selected_ids:
            fixtures.append(f)

    # ordenar por hora
    fixtures.sort(key=lambda x: (parse_iso_local(x["fixture"]["date"]) or datetime.max))

    # debug simples
    with st.expander("Debug fixtures", expanded=False):
        st.write({
            "modo": modo,
            "fixtures_raw_total": len(fixtures_raw),
            "fixtures_after_top_leagues": len(fixtures),
            "top_leagues_selected": selected_names,
        })
        if fixtures[:3]:
            ex = []
            for fx in fixtures[:3]:
                dt = parse_iso_local(fx["fixture"]["date"])
                ex.append({
                    "league": fx["league"]["name"],
                    "home": fx["teams"]["home"]["name"],
                    "away": fx["teams"]["away"]["name"],
                    "time_local": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
                    "status": fx.get("fixture", {}).get("status", {}).get("short"),
                })
            st.write(ex)

    if not fixtures:
        st.error("Nenhum jogo encontrado nas TOP ligas selecionadas. Troque para 'Próximas 24h' ou mude a lista de ligas.")
        return

    st.markdown("<div class='smallnote'>Clique em Gerar para criar Top picks 1X2 (1 por jogo, baseado em probabilidades).</div>", unsafe_allow_html=True)

    if st.button("Gerar Top Picks (1X2)", key="gen_1x2"):
        st.session_state["pause_refresh"] = True
        prog = st.progress(0)
        msg = st.empty()

        rows = []
        total = min(len(fixtures), 60)  # limite de custo/tempo

        for i, f in enumerate(fixtures[:total], start=1):
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

            # odds 1x2 via API-SPORTS (pode vir vazio)
            odd_home = odd_draw = odd_away = None
            try:
                oresp = apisports_odds_fixture(int(f["fixture"]["id"]))
                odd_home = apisports_extract_market(oresp, "Match Winner", "Home")
                odd_draw = apisports_extract_market(oresp, "Match Winner", "Draw")
                odd_away = apisports_extract_market(oresp, "Match Winner", "Away")
            except Exception:
                pass

            cands = [
                ("Casa", pH, odd_home),
                ("Empate", pD, odd_draw),
                ("Fora", pA, odd_away),
            ]

            # escolher melhor: se tiver odd respeita odd mínima; senão só prob
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
            })

        msg.write("Concluído.")
        rows = sorted(rows, key=lambda r: (-(r["edge"] if r["edge"] is not None else -999), -r["prob"]))[:top_picks]
        st.session_state["rows_1x2"] = rows

    render_cards(st.session_state["rows_1x2"], use_ai=use_ai)


if __name__ == "__main__":
    main()
