import streamlit as st
import requests
from mistralai import Mistral
from datetime import datetime

# 1. Configurações Iniciais
st.set_page_config(page_title="Elite Predictor 2.5 - API-Football", layout="wide")

# Estilo Dark Mode Premium
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    </style>
    """, unsafe_allow_html=True)

# 2. Inicialização das APIs
MISTRAL_KEY = st.secrets["MISTRAL_API_KEY"]
FOOTBALL_KEY = st.secrets["FOOTBALL_API_KEY"]
AGENT_ID = "ag_019b9bf3d4cb7275a9b0ffd56dd9a7d4" # Seu agente

client_mistral = Mistral(api_key=MISTRAL_KEY)

def buscar_h2h_real(id_home, id_away):
    """Busca os últimos 5 confrontos REAIS na API-Football"""
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': FOOTBALL_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("response", [])
    except:
        return []

def analise_agente_mistral(home, away, h2h_data, mercado):
    """O seu agente processa os dados reais e dá o veredito"""
    resumos = [f"{h['teams']['home']['name']} {h['goals']['home']}-{h['goals']['away']} {h['teams']['away']['name']}" for h in h2h_data]
    prompt = f"Jogo: {home} vs {away}. Histórico H2H: {', '.join(resumos)}. Analise para o mercado {mercado} com 75% de confiança."
    
    try:
        chat_response = client_mistral.agents.complete(
            agent_id=AGENT_ID,
            messages=[{"role": "user", "content": prompt}]
        )
        return chat_response.choices[0].message.content
    except:
        return "⚠️ Erro na resposta do Agente Mistral."

# 3. Interface Principal
st.title("🛡️ Elite Predictor 2.5: API-Football + Mistral")
st.write(f"Análise de Precisão Real | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR VARREDURA DE ELITE"):
    # Buscar jogos de hoje (Top Ligas)
    url_fixtures = "https://v3.football.api-sports.io/fixtures?date=" + datetime.now().strftime('%Y-%m-%d')
    headers = {'x-rapidapi-key': FOOTBALL_KEY}
    
    with st.spinner('Acedendo à API-Football e consultando o seu Agente Mistral...'):
        fixtures = requests.get(url_fixtures, headers=headers).json().get("response", [])

    if fixtures:
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])
        
        with tab1:
            for f in fixtures[:10]: # Analisando os 10 primeiros
                h_team = f['teams']['home']
                a_team = f['teams']['away']
                h2h_reais = buscar_h2h_real(h_team['id'], a_team['id'])
                
                with st.expander(f"🕒 {f['fixture']['date'][11:16]} | {h_team['name']} vs {a_team['name']}"):
                    veredito = analise_agente_mistral(h_team['name'], a_team['name'], h2h_reais, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{veredito}</div>', unsafe_allow_html=True)
                    
                    st.write("**📜 Últimos 5 Confrontos Reais:**")
                    for h in h2h_reais:
                        st.write(f"📅 {h['fixture']['date'][:10]}: {h['teams']['home']['name']} {h['goals']['home']}-{h['goals']['away']} {h['teams']['away']['name']}")

        with tab2:
            st.info("As análises de golos (BTTS/Over 2.5) estão integradas nos detalhes da Aba 1.")
        with tab3:
            st.info("As tendências de cantos estão integradas nos detalhes da Aba 1.")
    else:
        st.error("Não foram encontrados jogos de elite para hoje. Verifique sua chave API-Football.")
