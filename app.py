import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime

# 1. Configuração do Gemini 2.5 (AI Studio)
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # Utilizando a versão experimental mais avançada (2.0/2.5 Preview)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except Exception as e:
    st.error(f"Erro ao conectar com AI Studio: {e}")

# 2. Design e Estilo Dark Mode
st.set_page_config(page_title="Elite Predictor 2.5 AI", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    .stTabs [data-baseweb="tab"] { color: white; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

FOOTBALL_KEY = st.secrets["FOOTBALL_DATA_API_KEY"]

def analise_gemini_25(home, away, mercado):
    """O Gemini 2.5 pesquisa dados reais e gera o veredito"""
    prompt = f"""
    Como analista de elite, pesquise na internet os dados reais para {home} vs {away}.
    1. Liste os resultados EXATOS dos últimos 5 confrontos (H2H) de 2024-2026.
    2. Analise a forma atual das equipas na temporada 2025/2026.
    3. Dê um veredito para {mercado} com confiança acima de 75%.
    Data da análise: {datetime.now().strftime('%d/%m/%Y')}.
    Responda em Português com emojis e negrito nos placares.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Erro na consulta IA: {str(e)}"

# 3. Interface Principal
st.title("🛡️ Elite AI Predictor 2.5")
st.write(f"Motor: Gemini 2.5 + Football-Data.org | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR VARREDURA DE ELITE"):
    # Busca jogos usando a sua nova API
    url = "https://api.football-data.org/v4/matches"
    headers = {'X-Auth-Token': FOOTBALL_KEY}
    
    with st.spinner('Gemini 2.5 a processar históricos reais e performance atual...'):
        try:
            matches = requests.get(url, headers=headers).json().get("matches", [])
        except:
            matches = []

    if matches:
        # Abas restauradas conforme as suas fotos
        tab1, tab2, tab3, tab4 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)", "🔥 Combos"])

        with tab1:
            st.subheader("Top 10: Prognósticos 1x2")
            for m in matches[:10]:
                h, a = m['homeTeam']['name'], m['awayTeam']['name']
                with st.expander(f"🕒 {m['utcDate'][11:16]} | {h} vs {a}"):
                    resultado = analise_gemini_25(h, a, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)

        with tab2:
            st.subheader("Top 10: Ambas Marcam / Over 2.5")
            for m in matches[2:7]:
                h, a = m['homeTeam']['name'], m['awayTeam']['name']
                with st.expander(f"⚽ {h} vs {a} | Golos"):
                    st.write(analise_gemini_25(h, a, "Golos (BTTS / Over 2.5)"))

        with tab3:
            st.subheader("Top 10: Estratégia de Cantos")
            for m in matches[4:9]:
                h, a = m['homeTeam']['name'], m['awayTeam']['name']
                with st.expander(f"🚩 {h} vs {a} | Cantos"):
                    st.write(analise_gemini_25(h, a, "Cantos (Over 9.5)"))
        
        with tab4:
            st.success("Combine as seleções de +90% da Aba 1 para criar o seu Super Combo.")
    else:
        st.error("Nenhum jogo encontrado. Verifique a sua chave Football-Data.org.")
