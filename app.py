import streamlit as st
import requests
from mistralai import Mistral
from datetime import datetime

# 1. Estilo e Configuração da Página
st.set_page_config(page_title="Elite Predictor 2.5", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    </style>
    """, unsafe_allow_html=True)

# 2. Inicialização das APIs e do Agente Mistral
MISTRAL_KEY = st.secrets["MISTRAL_API_KEY"]
FOOTBALL_KEY = st.secrets["FOOTBALL_API_KEY"]
AGENT_ID = "ag_019b9bf3d4cb7275a9b0ffd56dd9a7d4" # ID do seu agente

client_mistral = Mistral(api_key=MISTRAL_KEY)

def buscar_h2h_real(id_home, id_away):
    """Busca o H2H real de 5 jogos na API-Football"""
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': FOOTBALL_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("response", [])
    except:
        return []

def analise_agente_mistral(home, away, h2h_data, mercado):
    """Consulta o agente Mistral para o veredito"""
    resumos = [f"{h['teams']['home']['name']} {h['goals']['home']}-{h['goals']['away']} {h['teams']['away']['name']}" for h in h2h_data]
    prompt = f"Analise {home} vs {away}. Histórico: {', '.join(resumos)}. Mercado: {mercado}. Dê veredito com 75% confiança."
    
    try:
        chat_response = client_mistral.agents.complete(
            agent_id=AGENT_ID,
            messages=[{"role": "user", "content": prompt}]
        )
        return chat_response.choices[0].message.content
    except:
        return "⚠️ Erro na resposta do Agente Mistral. Verifique a chave MISTRAL_API_KEY."

# 3. Interface Principal
st.title("🧠 Elite Predictor: API-Football + Mistral")
st.write(f"Análise Real | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR VARREDURA DE ELITE"):
    url_fixtures = "https://v3.football.api-sports.io/fixtures?date=" + datetime.now().strftime('%Y-%m-%d')
    headers = {'x-rapidapi-key': FOOTBALL_KEY}
    
    with st.spinner('Processando dados reais com Mistral AI...'):
        fixtures = requests.get(url_fixtures, headers=headers).json().get("response", [])

    if fixtures:
        tab1, tab2, tab3, tab4 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)", "🔥 Combos"])
        
        with tab1:
            for f in fixtures[:10]:
                h_name = f['teams']['home']['name']
                a_name = f['teams']['away']['name']
                h2h = buscar_h2h_real(f['teams']['home']['id'], f['teams']['away']['id'])
                
                with st.expander(f"🕒 {f['fixture']['date'][11:16]} | {h_name} vs {a_name}"):
                    veredito = analise_agente_mistral(h_name, a_name, h2h, "Vitória (1x2)")
                    st.markdown(f'<div class="card-elite">{veredito}</div>', unsafe_allow_html=True)
                    st.write("**📜 Últimos 5 Confrontos Reais:**")
                    for h in h2h:
                        st.write(f"📅 {h['fixture']['date'][:10]}: {h['teams']['home']['name']} {h['goals']['home']}-{h['goals']['away']} {h['teams']['away']['name']}")
        
        with tab2:
            st.info("Utilize as análises de golos geradas pelo agente Mistral acima.")
        with tab3:
            st.info("Utilize as tendências de cantos geradas pelo agente Mistral acima.")
        with tab4:
             st.success("Combine os favoritos de confiança 90%+ para a sua Odd Betway!")
    else:
        st.error("Nenhum jogo encontrado para hoje. Verifique a sua chave FOOTBALL_API_KEY.")
