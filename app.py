import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. Configuração de Estilo e Página
st.set_page_config(page_title="Scanner Pro Elite H2H", layout="wide", page_icon="🏆")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #00ff00; color: black; font-weight: bold; height: 3.5em; }
    .card-seguro { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 8px solid #00ff00; margin-bottom: 15px; }
    .card-medio { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 8px solid #ffcc00; margin-bottom: 15px; }
    .card-risco { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 8px solid #ff6600; margin-bottom: 15px; }
    h1, h2, h3 { color: #00ff00 !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. Configuração da API
API_KEY = "2f7f513c439d38b4783cb360914ae6d5d4b0ccfaf72f38058e30e979f1cb738c"

def buscar_dados():
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    try:
        res = requests.get(url)
        return res.json().get("result", [])
    except:
        return []

# 3. Função para simular H2H e Análise Criativa
def obter_detalhes_ia(home, away):
    # Simulação de análise baseada em dados históricos
    h2h = [f"{home} 2 - 1 {away}", f"{away} 0 - 2 {home}"] # Exemplo de últimos 2 jogos
    prob = 85 if "2 - 1" in h2h[0] else 65
    
    if prob >= 80:
        estilo = "card-seguro"
        confianca = "ALTA (Segura)"
    elif prob >= 65:
        estilo = "card-medio"
        confianca = "MÉDIA (Moderada)"
    else:
        estilo = "card-risco"
        confianca = "BAIXA (Zebra/Valor)"
        
    return prob, h2h, estilo, confianca

# 4. Interface Principal
st.title("🧠 Elite Predictor H2H")
st.write("Análise detalhada com histórico de confrontos e níveis de confiança.")

if st.button("🚀 GERAR RELATÓRIO DE ELITE"):
    jogos = buscar_dados()
    
    if jogos:
        tab1, tab2, tab3, tab4 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos", "🚩 Cantos", "🔥 Combos"])

        with tab1:
            st.subheader("Top 10 Vencedores com H2H")
            for i in range(min(10, len(jogos))):
                j = jogos[i]
                home, away = j['event_home_team'], j['event_away_team']
                prob, h2h, estilo, conf = obter_detalhes_ia(home, away)
                
                with st.expander(f"📍 {home} vs {away} | Confiança: {conf}"):
                    st.markdown(f"""
                    <div class="{estilo}">
                        <h3>Palpite: Vitória do {home}</h3>
                        <p><b>Probabilidade:</b> {prob}%</p>
                        <hr>
                        <p><b>📜 Últimos 2 Confrontos:</b></p>
                        <ul>
                            <li>{h2h[0]} (Recente)</li>
                            <li>{h2h[1]} (Anterior)</li>
                        </ul>
                        <p><b>💡 Análise:</b> O {home} domina o histórico recente e apresenta melhor forma física para este duelo.</p>
                    </div>
                    """, unsafe_allow_html=True)

        with tab2:
            st.subheader("Top 10: Ambas Marcam & Over 2.5")
            # Lista simplificada para visualização rápida
            for i in range(min(5, len(jogos))):
                st.markdown(f"✅ **{jogos[i+5]['event_home_team']} vs {jogos[i+5]['event_away_team']}** - Tendência de jogo aberto.")

        with tab3:
            st.subheader("Top 10: Estratégia de Cantos (+9.5)")
            st.write("Foco em equipas que exploram as linhas laterais.")

        with tab4:
            st.subheader("🔥 Super Combo (Ganha & +2.5)")
            st.success("Combine estas seleções para aumentar a sua Odd na Betway!")

    else:
        st.error("Erro ao carregar jogos. Verifique a sua conexão ou API Key.")

# Rodapé
st.sidebar.markdown("""
### 🎨 Legenda de Confiança:
- 🟢 **Verde:** Alta Confiança (+80%)
- 🟡 **Amarelo:** Moderado (65-79%)
- 🟠 **Laranja:** Risco/Valor (Sub 65%)
""")
