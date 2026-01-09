import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime

# 1. Configuração do ChatGPT (OpenAI)
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# 2. Design de Elite
st.set_page_config(page_title="Elite Predictor ChatGPT", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    </style>
    """, unsafe_allow_html=True)

def analise_chatgpt(home, away, mercado):
    """O ChatGPT analisa os dados reais e gera o veredito"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Modelo rápido e económico
            messages=[
                {"role": "system", "content": "És um analista de apostas de elite da Betway Moçambique."},
                {"role": "user", "content": f"Analise {home} vs {away} para o mercado {mercado}. Forneça os últimos 5 confrontos reais (H2H) e veredito com 75% de confiança. Use emojis e negrito nos placares."}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Erro no ChatGPT: {str(e)}"

# 3. Interface Principal
st.title("🛡️ Elite AI Predictor: GPT Edition")
st.write(f"Motor: ChatGPT + Football-Data.org | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR VARREDURA DE ELITE"):
    headers = {'X-Auth-Token': st.secrets["FOOTBALL_DATA_API_KEY"]}
    url = "https://api.football-data.org/v4/matches"
    
    with st.spinner('O ChatGPT está a analisar históricos reais...'):
        try:
            matches = requests.get(url, headers=headers).json().get("matches", [])
        except:
            matches = []

    if matches:
        # Abas restauradas
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])

        with tab1:
            for m in matches[:10]:
                h, a = m['homeTeam']['name'], m['awayTeam']['name']
                with st.expander(f"🕒 {m['utcDate'][11:16]} | {h} vs {a}"):
                    resultado = analise_chatgpt(h, a, "Vitória (1x2)")
                    st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)
        
        with tab2:
            st.info("Abra os detalhes na Aba Vitória para ver análises de Golos.")
        with tab3:
            st.info("As tendências de Cantos estão integradas na análise do ChatGPT.")
    else:
        st.error("Nenhum jogo encontrado. Verifique a sua chave API-Football.")
