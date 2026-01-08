import streamlit as st
import requests
from mistralai import Mistral
from datetime import datetime

# 1. Configuração do Agente Mistral
MISTRAL_API_KEY = st.secrets["MISTRAL_API_KEY"]
AGENT_ID = "ag_019b9bf3d4cb7275a9b0ffd56dd9a7d4"
client = Mistral(api_key=MISTRAL_API_KEY)

st.set_page_config(page_title="Elite Predictor - Mistral AI", layout="wide")

# Estilo Dark Premium
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; }
    </style>
    """, unsafe_allow_html=True)

def analise_mistral_agente(home, away, mercado):
    """Consulta o SEU Agente Mistral para obter dados reais"""
    pergunta = f"Analise {home} vs {away} para o mercado de {mercado}. Forneça os últimos 5 confrontos H2H reais e um veredito com 75% de confiança."
    try:
        response = client.agents.complete(
            agent_id=AGENT_ID,
            messages=[{"role": "user", "content": pergunta}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Erro no Agente Mistral: {str(e)}"

# 2. Interface Principal
st.title("🛡️ Elite AI Predictor (Mistral Edition)")
st.write(f"Utilizando Agente Personalizado | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR VARREDURA COM MISTRAL"):
    API_KEY_SPORTS = st.secrets["ALL_SPORTS_API_KEY"]
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY_SPORTS}&from={hoje}&to={hoje}"
    
    with st.spinner('O seu Agente Mistral está a processar os dados...'):
        res = requests.get(url).json()
        jogos = res.get("result", [])
    
    if jogos:
        # Recuperação total das abas
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])
        
        with tab1:
            for j in jogos[:10]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    resultado = analise_mistral_agente(h, a, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)
        
        with tab2:
            for j in jogos[2:7]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"⚽ {h} vs {a}"):
                    st.write(analise_mistral_agente(h, a, "Golos (Over 2.5 / BTTS)"))
        
        with tab3:
            for j in jogos[4:9]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🚩 {h} vs {a}"):
                    st.write(analise_mistral_agente(h, a, "Cantos (Over 9.5)"))
    else:
        st.warning("Nenhum jogo encontrado para hoje.")
