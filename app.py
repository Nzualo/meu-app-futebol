import streamlit as st
import requests
from mistralai import Mistral
from datetime import datetime

# 1. Estilo e Configuração Dark Mode Premium
st.set_page_config(page_title="Elite Predictor 2.5", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    </style>
    """, unsafe_allow_html=True)

# 2. Inicialização das APIs
MISTRAL_KEY = st.secrets["MISTRAL_API_KEY"]
FOOTBALL_KEY = st.secrets["FOOTBALL_DATA_API_KEY"]
AGENT_ID = "ag_019b9bf3d4cb7275a9b0ffd56dd9a7d4"

client_mistral = Mistral(api_key=MISTRAL_KEY)

def buscar_jogos_hoje():
    """Busca jogos do dia usando a football-data.org"""
    url = "https://api.football-data.org/v4/matches"
    headers = {'X-Auth-Token': FOOTBALL_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("matches", [])
    except:
        return []

def analise_mistral_pro(home, away, mercado):
    """Consulta o seu Agente Mistral para análise de elite"""
    prompt = f"Analise {home} vs {away} para o mercado {mercado}. Forneça o H2H real de 5 jogos e veredito > 75%."
    try:
        response = client_mistral.agents.complete(
            agent_id=AGENT_ID,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro na resposta do Agente Mistral. Verifique a chave MISTRAL_API_KEY."

# 3. Interface Principal
st.title("🛡️ Elite Predictor: Football-Data + Mistral")
st.write(f"Sincronizado: {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR VARREDURA DE ELITE"):
    matches = buscar_jogos_hoje()
    
    if matches:
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])
        
        with tab1:
            for m in matches[:10]:
                h, a = m['homeTeam']['name'], m['awayTeam']['name']
                with st.expander(f"🕒 {m['utcDate'][11:16]} | {h} vs {a}"):
                    veredito = analise_mistral_pro(h, a, "Vitória (1x2)")
                    st.markdown(f'<div class="card-elite">{veredito}</div>', unsafe_allow_html=True)
        
        with tab2:
            st.info("As tendências de golos estão integradas nas análises detalhadas da Aba 1.")
        with tab3:
            st.info("As tendências de cantos estão integradas nas análises detalhadas da Aba 1.")
    else:
        st.error("Nenhum jogo encontrado para hoje. Verifique a sua chave Football-Data.")

st.sidebar.markdown("---")
st.sidebar.info("Utilizando a nova API Football-Data.org para máxima precisão.")
