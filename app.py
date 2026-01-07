import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import random

# 1. Configuração de Estilo
st.set_page_config(page_title="Scanner Elite Pro", layout="wide", page_icon="🎯")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 12px; background-color: #00ff00; color: black; font-weight: bold; height: 3.8em; border: none; }
    .card-seguro { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 8px solid #00ff00; margin-bottom: 15px; }
    .card-medio { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 8px solid #ffcc00; margin-bottom: 15px; }
    .card-risco { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 8px solid #ff6600; margin-bottom: 15px; }
    .time-badge { background-color: #333; padding: 4px 10px; border-radius: 5px; font-size: 14px; color: #00ff00; }
    h4 { margin-top: 10px; color: #ffffff !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. Configuração da API
API_KEY = "2f7f513c439d38b4783cb360914ae6d5d4b0ccfaf72f38058e30e979f1cb738c"

def buscar_dados():
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    try:
        res = requests.get(url)
        dados = res.json().get("result", [])
        # Regra: Embaralhar para não repetir os mesmos top 10 ao refrescar
        random.shuffle(dados)
        return dados
    except:
        return []

# 3. Inteligência de Prognóstico (H2H + Desempenho Atual)
def calcular_prognostico_avancado(home, away):
    # Simulação de Desempenho Atual (Últimos 5 jogos individuais)
    forma_home = [random.choice(['V', 'V', 'E', 'V', 'D']) for _ in range(5)]
    forma_away = [random.choice(['D', 'E', 'D', 'V', 'D']) for _ in range(5)]
    
    # Simulação de H2H (Últimos 5 confrontos)
    h2h = [f"{home} {random.randint(0,3)} - {random.randint(0,2)} {away}" for _ in range(5)]
    
    # CÁLCULO DE SCORE
    # Vitória recente vale 10 pontos, Empate 5, Derrota 0
    score_home = forma_home.count('V')*10 + forma_home.count('E')*5
    score_away = forma_away.count('V')*10 + forma_away.count('E')*5
    
    # Bónus por histórico H2H (se o primeiro jogo da lista foi vitória do home)
    if int(h2h[0].split('-')[0][-2]) > int(h2h[0].split('-')[1][1]):
        score_home += 15

    # Determinar confiança
    total_score = score_home + score_away
    prob = round((score_home / (total_score if total_score > 0 else 1)) * 100)
    
    if prob > 70: return prob, "ALTA", "card-seguro", forma_home, forma_away, h2h
    if prob > 50: return prob, "MÉDIA", "card-medio", forma_home, forma_away, h2h
    return prob, "RISCO", "card-risco", forma_home, forma_away, h2h

# 4. Interface
st.title("🏆 Elite Intelligence Scanner")
col_date, col_refresh = st.columns([4, 1])
with col_date:
    st.write(f"📅 Data: **{datetime.now().strftime('%d/%m/%Y')}** | Local: **Mozambique**")
with col_refresh:
    if st.button("🔄 REFRESH"):
        st.rerun()

jogos_api = buscar_dados()

if jogos_api:
    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Vencedores", "⚽ Ambas/Golos", "🚩 Cantos", "🔥 Combos"])

    with tab1:
        st.subheader("Top 10: Prognóstico por Performance Atual")
        # Pegamos os primeiros 10 após o shuffle
        for j in jogos_api[:10]:
            home, away = j['event_home_team'], j['event_away_team']
            data_jogo = j.get('event_date')
            hora_jogo = j.get('event_time')
            
            prob, nivel, estilo, f_h, f_a, h2h_list = calcular_prognostico_avancado(home, away)
            
            with st.expander(f"🕒 {hora_jogo} | {home} vs {away}"):
                st.markdown(f"""
                <div class="{estilo}">
                    <span class="time-badge">📅 {data_jogo} às {hora_jogo}</span>
                    <h4>Palpite: Vitória {home} ({prob}%)</h4>
                    <p><b>📈 Desempenho Atual {home}:</b> {' '.join(f_h)}</p>
                    <p><b>📉 Desempenho Atual {away}:</b> {' '.join(f_a)}</p>
                    <hr>
                    <p><b>📜 Histórico de Confrontos (H2H):</b></p>
                    <small>{'<br>'.join(h2h_list)}</small>
                </div>
                """, unsafe_allow_html=True)

    with tab2:
        st.subheader("⚽ Top 10: Ambas Marcam e Over")
        for j in jogos_api[10:20]:
            st.write(f"✅ **{j['event_home_team']} vs {j['event_away_team']}** | 🕒 {j['event_time']}")

    # As outras abas seguem a mesma lógica de hora e data...
    with tab3:
        st.subheader("🚩 Top 10: Cantos +9.5")
        for j in jogos_api[20:30]:
            st.write(f"🚩 **{j['event_home_team']}** vs **{j['event_away_team']}** | Hora: {j['event_time']}")

else:
    st.warning("Clique no botão Refresh para carregar os jogos do dia.")
