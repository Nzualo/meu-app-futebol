# elite_scanner_refatorado.py
# Streamlit app: dados (API-Football) + modelo Poisson simples + (opcional) explicação por IA
#
# PRINCIPAIS MELHORIAS APLICADAS
# - Segurança: chaves em st.secrets (NUNCA hardcode)
# - Headers corretos (API-Sports direto vs RapidAPI)
# - Timeouts + raise_for_status + mensagens de erro úteis
# - Cache agressivo (fixtures, últimos jogos, H2H, análises IA)
# - UX: usuário escolhe data, ligas, jogos e mercados; custo controlado
# - Modelo: estimativa de probabilidade (Poisson) para Over/Under e BTTS + fair odds
# - IA: apenas como "explicador" do output do modelo + limitações (não inventa confiança)
#
# PRÉ-REQUISITOS (Streamlit secrets)
# .streamlit/secrets.toml:
# OPENAI_API_KEY="..."
# FOOTBALL_API_KEY="..."   # sua chave do API-Football / API-Sports OU RapidAPI
# FOOTBALL_API_MODE="apisports"  # "apisports" (direto) OU "rapidapi"
#
# Observação: endpoints assumem API-Football v3: https://v3.football.api-sports.io
# Se sua conta usar RapidAPI, o header é x-rapidapi-key e o host pode variar.
# Ajuste FOOTBALL_API_MODE conforme seu caso.

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import requests
import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # permite rodar sem openai instalado

# -----------------------------
# 1) Configurações
# -----------------------------
LOCAL_TZ = pytz.timezone("Africa/Maputo")
API_BASE = "https://v3.football.api-sports.io"

st.set_page_config(page_title="Elite Intelligence Scanner", layout="wide")

st.markdown(
    """
<style>
.main { background-color: #0e1117; }
.card-elite { background-color: #1a1c24; padding: 15px; border-radius: 12px;
              border-left: 8px solid #00ff00; color: white; margin-bottom: 15px; }
.badge { background-color: #00ff00; color: black; padding: 4px 10px; border-radius: 14px;
         font-weight: 700; display:inline-block; }
.small { color: #aab; font-size: 0.90rem; }
hr { border-color: #222; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 2) Utilidades de API
# -----------------------------
def _get_secret(name: str, default: Optional[str] = None) -> str:
    v = st.secrets.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing secret: {name}")
    return str(v)


def _football_headers() -> Dict[str, str]:
    api_key = _get_secret("FOOTBALL_API_KEY")
    mode = st.secrets.get("FOOTBALL_API_MODE", "apisports").lower().strip()
    if mode == "rapidapi":
        # se você usa RapidAPI, geralmente precisa também do host.
        # Caso tenha, defina FOOTBALL_RAPIDAPI_HOST em secrets.
        host = st.secrets.get("FOOTBALL_RAPIDAPI_HOST", "v3.football.api-sports.io")
        return {"x-rapidapi-key": api_key, "x-rapidapi-host": host}
    # modo padrão: API-Sports direto
    return {"x-apisports-key": api_key}


def api_get(path: str, params: Dict[str, str], timeout: int = 12) -> Dict:
    url = f"{API_BASE}{path}"
    try:
        r = requests.get(url, headers=_football_headers(), params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        # API-Football costuma devolver {"errors":..., "response":[...]}
        return data
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao chamar API-Football: {e}")
        return {"response": [], "errors": {"request": str(e)}}
    except Exception as e:
        st.error(f"Erro inesperado ao processar resposta: {e}")
        return {"response": [], "errors": {"parse": str(e)}}


@st.cache_data(ttl=60 * 10)
def get_fixtures_by_date(date_yyyy_mm_dd: str) -> List[Dict]:
    data = api_get("/fixtures", {"date": date_yyyy_mm_dd})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 60 * 12)
def get_h2h_last(id_home: int, id_away: int, last: int = 10) -> List[Dict]:
    data = api_get("/fixtures/headtohead", {"h2h": f"{id_home}-{id_away}", "last": str(last)})
    return data.get("response", []) or []


@st.cache_data(ttl=60 * 60 * 2)
def get_last_team_fixtures(team_id: int, last: int = 10, status: str = "FT") -> List[Dict]:
    # Últimos jogos concluídos do time (forma recente)
    data = api_get("/fixtures", {"team": str(team_id), "last": str(last), "status": status})
    return data.get("response", []) or []


# -----------------------------
# 3) Modelo Poisson simples
# -----------------------------
def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def prob_over_total(lam_home: float, lam_away: float, line: float, max_goals: int = 10) -> float:
    # P(total goals > line)
    # line pode ser 1.5, 2.5 etc.
    threshold = math.floor(line)  # ex: 2.5 -> floor=2 => total<=2 é "under"
    p_under_or_equal = 0.0
    for gh in range(0, max_goals + 1):
        ph = poisson_pmf(gh, lam_home)
        for ga in range(0, max_goals + 1):
            total = gh + ga
            pa = poisson_pmf(ga, lam_away)
            if total <= threshold:
                p_under_or_equal += ph * pa
    return max(0.0, min(1.0, 1.0 - p_under_or_equal))


def prob_btts(lam_home: float, lam_away: float, max_goals: int = 10) -> float:
    # P(home>=1 AND away>=1) = 1 - P(home=0) - P(away=0) + P(home=0, away=0)
    p_home0 = poisson_pmf(0, lam_home)
    p_away0 = poisson_pmf(0, lam_away)
    p_00 = p_home0 * p_away0
    p = 1.0 - p_home0 - p_away0 + p_00
    return max(0.0, min(1.0, p))


def prob_1x2(lam_home: float, lam_away: float, max_goals: int = 10) -> Tuple[float, float, float]:
    # P(Home win), P(Draw), P(Away win) via soma de matriz Poisson
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    for gh in range(0, max_goals + 1):
        ph = poisson_pmf(gh, lam_home)
        for ga in range(0, max_goals + 1):
            pa = poisson_pmf(ga, lam_away)
            if gh > ga:
                p_home += ph * pa
            elif gh == ga:
                p_draw += ph * pa
            else:
                p_away += ph * pa
    # normaliza (porque truncamos em max_goals)
    s = p_home + p_draw + p_away
    if s > 0:
        p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s
    return p_home, p_draw, p_away


def fair_odds(p: float) -> Optional[float]:
    if p <= 0:
        return None
    return 1.0 / p


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# -----------------------------
# 4) Extração de features (forma recente)
# -----------------------------
@dataclass
class TeamForm:
    games: int
    gf_per_game: float
    ga_per_game: float
    gf_home_per_game: Optional[float] = None
    ga_home_per_game: Optional[float] = None
    gf_away_per_game: Optional[float] = None
    ga_away_per_game: Optional[float] = None


def _extract_team_result(team_id: int, fixture: Dict) -> Optional[Tuple[int, int, bool]]:
    # retorna (goals_for, goals_against, is_home) se for fixture FT e dados disponíveis
    try:
        goals = fixture.get("goals", {})
        teams = fixture.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        if not goals or home.get("id") is None or away.get("id") is None:
            return None

        is_home = (home.get("id") == team_id)
        gf = goals.get("home") if is_home else goals.get("away")
        ga = goals.get("away") if is_home else goals.get("home")
        if gf is None or ga is None:
            return None
        return int(gf), int(ga), bool(is_home)
    except Exception:
        return None


def compute_team_form(team_id: int, last_fixtures: List[Dict]) -> TeamForm:
    gf = ga = 0
    gf_home = ga_home = 0
    gf_away = ga_away = 0
    n = n_home = n_away = 0

    for fx in last_fixtures:
        r = _extract_team_result(team_id, fx)
        if not r:
            continue
        _gf, _ga, is_home = r
        gf += _gf
        ga += _ga
        n += 1
        if is_home:
            gf_home += _gf
            ga_home += _ga
            n_home += 1
        else:
            gf_away += _gf
            ga_away += _ga
            n_away += 1

    if n == 0:
        return TeamForm(games=0, gf_per_game=0.0, ga_per_game=0.0)

    tf = TeamForm(
        games=n,
        gf_per_game=gf / n,
        ga_per_game=ga / n,
    )
    if n_home > 0:
        tf.gf_home_per_game = gf_home / n_home
        tf.ga_home_per_game = ga_home / n_home
    if n_away > 0:
        tf.gf_away_per_game = gf_away / n_away
        tf.ga_away_per_game = ga_away / n_away
    return tf


def estimate_lambdas(
    home_form: TeamForm,
    away_form: TeamForm,
    home_adv: float = 1.08,
    smoothing: float = 0.25,
) -> Tuple[float, float, str]:
    """
    Estima lambda_home e lambda_away a partir de forma recente.
    - home_adv: vantagem de casa multiplicativa (ajustável)
    - smoothing: puxa lambdas para 1.25 quando dados são fracos (reduz extremos)
    Retorna também um "nível de evidência" baseado em games disponíveis.
    """
    base = 1.25  # média genérica de gols por time/jogo (fallback neutro)

    # usa splits home/away quando disponíveis
    home_attack = home_form.gf_home_per_game if home_form.gf_home_per_game is not None else home_form.gf_per_game
    home_def = home_form.ga_home_per_game if home_form.ga_home_per_game is not None else home_form.ga_per_game

    away_attack = away_form.gf_away_per_game if away_form.gf_away_per_game is not None else away_form.gf_per_game
    away_def = away_form.ga_away_per_game if away_form.ga_away_per_game is not None else away_form.ga_per_game

    # Combina ataque de um com defesa do outro
    lam_home_raw = (home_attack + away_def) / 2.0
    lam_away_raw = (away_attack + home_def) / 2.0

    # Aplica vantagem casa
    lam_home_raw *= home_adv
    lam_away_raw *= (2.0 - home_adv)  # compensação simples

    # Smoothing para reduzir overfit quando poucos jogos
    n_eff = min(home_form.games, away_form.games)
    # peso cresce com mais jogos (cap em 10)
    w = clamp01(n_eff / 10.0)
    # smoothing adicional
    w = max(w, smoothing)
    lam_home = w * lam_home_raw + (1 - w) * base
    lam_away = w * lam_away_raw + (1 - w) * base

    if n_eff >= 8:
        evidence = "ALTA"
    elif n_eff >= 4:
        evidence = "MÉDIA"
    else:
        evidence = "BAIXA"

    # limites razoáveis
    lam_home = float(max(0.2, min(3.5, lam_home)))
    lam_away = float(max(0.2, min(3.5, lam_away)))
    return lam_home, lam_away, evidence


# -----------------------------
# 5) IA como explicador (opcional)
# -----------------------------
def _get_openai_client() -> Optional["OpenAI"]:
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key or OpenAI is None:
        return None
    return OpenAI(api_key=api_key)


@st.cache_data(ttl=60 * 60)
def explain_with_ai(
    home: str,
    away: str,
    market: str,
    lam_home: float,
    lam_away: float,
    probs: Dict[str, float],
    evidence: str,
    notes: str,
) -> str:
    client = _get_openai_client()
    if client is None:
        return "IA desativada (sem OPENAI_API_KEY ou pacote openai indisponível)."

    # Prompt explicitamente anti-alucinação
    prompt = f"""
Você é um analista quantitativo de futebol. Sua função é EXPLICAR resultados de um modelo estatístico simples (Poisson),
sem inventar lesões, escalações, odds ou notícias.

Jogo: {home} vs {away}
Mercado: {market}

Parâmetros do modelo:
- lambda_home={lam_home:.2f}
- lambda_away={lam_away:.2f}
- nível de evidência: {evidence}

Probabilidades calculadas (não invente outras):
{probs}

Notas objetivas:
{notes}

Regras:
- Não use percentuais de "confiança subjetiva". Use apenas as probabilidades fornecidas.
- Se evidência for BAIXA, destaque limitações e recomende cautela.
- Seja técnico e conciso. Forneça: (1) leitura do jogo, (2) pontos a favor/contra do mercado, (3) limitações.
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ IA indisponível: {e}"


# -----------------------------
# 6) UI + Orquestração
# -----------------------------
def parse_fixture_time_local(fixture: Dict) -> Optional[datetime]:
    try:
        iso = fixture["fixture"]["date"]
        dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt_utc.astimezone(LOCAL_TZ)
    except Exception:
        return None


def fixture_label(fx: Dict) -> str:
    h = fx["teams"]["home"]["name"]
    a = fx["teams"]["away"]["name"]
    dt_local = parse_fixture_time_local(fx)
    time_str = dt_local.strftime("%H:%M") if dt_local else "??:??"
    league = fx.get("league", {}).get("name", "Liga")
    return f"{time_str} | {h} vs {a} — {league}"


def is_future_fixture(fx: Dict, now_local: datetime) -> bool:
    dt_local = parse_fixture_time_local(fx)
    return bool(dt_local and dt_local > now_local)


def main():
    now_local = datetime.now(LOCAL_TZ)

    st.title("Elite Intelligence Scanner 3.0 (Quant + IA opcional)")
    st.write(f"📍 Localização: **Inhassoro/Maputo** | 🕒 Hora Atual: **{now_local.strftime('%H:%M:%S')}**")

    with st.sidebar:
        st.subheader("Configuração")
        date_choice = st.date_input("Data dos jogos", value=now_local.date())
        show_only_future = st.checkbox("Apenas jogos futuros (hora local)", value=True)
        max_games = st.slider("Máximo de jogos para listar", 10, 200, 60, step=10)
        last_n_form = st.slider("Forma recente (últimos N jogos FT)", 4, 20, 10, step=1)
        h2h_last = st.slider("H2H (últimos N jogos)", 0, 20, 10, step=1)
        home_adv = st.slider("Vantagem de casa (multiplicador)", 1.00, 1.20, 1.08, step=0.01)
        enable_ai = st.checkbox("Gerar explicação por IA (custo)", value=False)
        st.caption("Dica: habilite IA somente após selecionar poucos jogos.")

    date_str = date_choice.strftime("%Y-%m-%d")

    # Carrega fixtures do dia
    fixtures = get_fixtures_by_date(date_str)

    # Filtra jogos futuros se necessário
    if show_only_future:
        fixtures = [fx for fx in fixtures if is_future_fixture(fx, now_local)]

    # Se vazio e selecionou hoje e filtro futuro, sugere amanhã (sem mudar automaticamente)
    if not fixtures and date_choice == now_local.date() and show_only_future:
        st.warning(
            "Sem jogos futuros para hoje (hora local). "
            "Se desejar, selecione amanhã na barra lateral."
        )

    if not fixtures:
        st.error("Nenhum jogo encontrado para a data/filtro selecionado.")
        return

    # Lista ligas disponíveis
    leagues = sorted({(fx.get("league", {}).get("id"), fx.get("league", {}).get("name")) for fx in fixtures})
    league_name_by_id = {lid: name for lid, name in leagues if lid is not None}
    league_ids = [lid for lid, _ in leagues if lid is not None]

    colA, colB = st.columns([2, 1])
    with colA:
        st.markdown(f"🗓️ Agenda para: <span class='badge'>{date_choice.strftime('%d/%m/%Y')}</span>", unsafe_allow_html=True)
        st.caption("Selecione ligas e jogos abaixo. O cálculo (Poisson) roda localmente; IA é opcional.")

    with colB:
        selected_leagues = st.multiselect(
            "Filtrar por liga",
            options=league_ids,
            default=league_ids[: min(10, len(league_ids))],
            format_func=lambda x: league_name_by_id.get(x, str(x)),
        )

    fixtures_filtered = [
        fx for fx in fixtures
        if (fx.get("league", {}).get("id") in selected_leagues if selected_leagues else True)
    ]

    fixtures_filtered = fixtures_filtered[:max_games]

    # Escolha de jogos
    fx_map = {fixture_label(fx): fx for fx in fixtures_filtered}
    selected_labels = st.multiselect(
        "Escolha os jogos para analisar (recomendado: 1 a 8)",
        options=list(fx_map.keys()),
        default=list(fx_map.keys())[: min(5, len(fx_map))],
    )

    if not selected_labels:
        st.info("Selecione ao menos 1 jogo.")
        return

    # Mercados
    markets = st.multiselect(
        "Mercados",
        options=["Over 1.5", "Over 2.5", "BTTS (Ambas marcam)", "1X2"],
        default=["Over 2.5", "BTTS (Ambas marcam)"],
    )
    if not markets:
        st.info("Selecione ao menos 1 mercado.")
        return

    run = st.button("🚀 Analisar jogos selecionados")
    if not run:
        return

    st.markdown("---")

    # Processa cada jogo
    for label in selected_labels:
        fx = fx_map[label]
        home = fx["teams"]["home"]
        away = fx["teams"]["away"]
        home_id, away_id = int(home["id"]), int(away["id"])

        dt_local = parse_fixture_time_local(fx)
        time_str = dt_local.strftime("%d/%m %H:%M") if dt_local else "Horário indisponível"

        st.subheader(f"{home['name']} vs {away['name']}")
        st.write(f"<span class='small'>🕒 {time_str}</span>", unsafe_allow_html=True)

        # Busca forma recente
        home_last = get_last_team_fixtures(home_id, last=last_n_form, status="FT")
        away_last = get_last_team_fixtures(away_id, last=last_n_form, status="FT")

        home_form = compute_team_form(home_id, home_last)
        away_form = compute_team_form(away_id, away_last)

        # Lambdas
        lam_home, lam_away, evidence = estimate_lambdas(home_form, away_form, home_adv=home_adv)

        # H2H (opcional)
        h2h_text = ""
        if h2h_last > 0:
            h2h = get_h2h_last(home_id, away_id, last=h2h_last)
            if h2h:
                lines = []
                for m in h2h[: min(h2h_last, len(h2h))]:
                    try:
                        d = m["fixture"]["date"][:10]
                        hn = m["teams"]["home"]["name"]
                        an = m["teams"]["away"]["name"]
                        gh = m["goals"]["home"]
                        ga = m["goals"]["away"]
                        lines.append(f"- {d}: {hn} {gh}-{ga} {an}")
                    except Exception:
                        continue
                if lines:
                    h2h_text = "\n".join(lines)

        # Notas objetivas para IA
        notes = (
            f"Forma recente (FT, n={last_n_form} solicitado):\n"
            f"- {home['name']}: jogos={home_form.games}, GF/j={home_form.gf_per_game:.2f}, GA/j={home_form.ga_per_game:.2f}\n"
            f"- {away['name']}: jogos={away_form.games}, GF/j={away_form.gf_per_game:.2f}, GA/j={away_form.ga_per_game:.2f}\n"
        )
        if h2h_text:
            notes += f"\nH2H (últimos {h2h_last}):\n{h2h_text}\n"
        else:
            notes += "\nH2H: não usado ou sem dados.\n"

        # Exibe parâmetros
        st.markdown(
            f"<div class='card-elite'>"
            f"<b>Modelo (Poisson)</b><br/>"
            f"λ casa: <b>{lam_home:.2f}</b> | λ fora: <b>{lam_away:.2f}</b><br/>"
            f"Evidência: <b>{evidence}</b> (baseado no mínimo de jogos recentes disponíveis)<br/>"
            f"<span class='small'>Observação: probabilidades são estimativas estatísticas simples; não incluem lesões/escalações/odds.</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Calcula e mostra mercados
        for market in markets:
            probs: Dict[str, float] = {}
            if market == "Over 1.5":
                p = prob_over_total(lam_home, lam_away, 1.5)
                probs = {"P(Over 1.5)": float(p), "Fair odd": float(fair_odds(p) or 0.0)}
            elif market == "Over 2.5":
                p = prob_over_total(lam_home, lam_away, 2.5)
                probs = {"P(Over 2.5)": float(p), "Fair odd": float(fair_odds(p) or 0.0)}
            elif market == "BTTS (Ambas marcam)":
                p = prob_btts(lam_home, lam_away)
                probs = {"P(BTTS)": float(p), "Fair odd": float(fair_odds(p) or 0.0)}
            elif market == "1X2":
                ph, pd, pa = prob_1x2(lam_home, lam_away)
                probs = {
                    "P(Home)": float(ph),
                    "P(Draw)": float(pd),
                    "P(Away)": float(pa),
                    "Fair odd Home": float(fair_odds(ph) or 0.0),
                    "Fair odd Draw": float(fair_odds(pd) or 0.0),
                    "Fair odd Away": float(fair_odds(pa) or 0.0),
                }

            # render
            with st.expander(f"📌 Mercado: {market}", expanded=False):
                # tabela manual simples (sem pandas para manter leve)
                for k, v in probs.items():
                    if "P(" in k:
                        st.write(f"- **{k}**: `{v:.3f}`")
                    elif "Fair odd" in k:
                        st.write(f"- **{k}**: `{v:.2f}`")

                # IA opcional
                if enable_ai:
                    ai_text = explain_with_ai(
                        home=home["name"],
                        away=away["name"],
                        market=market,
                        lam_home=lam_home,
                        lam_away=lam_away,
                        probs=probs,
                        evidence=evidence,
                        notes=notes,
                    )
                    st.markdown(f"<div class='card-elite'>{ai_text}</div>", unsafe_allow_html=True)
                else:
                    st.caption("IA desativada para este relatório (habilite na barra lateral se desejar).")

        st.markdown("<hr/>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
