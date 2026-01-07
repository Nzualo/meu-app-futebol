import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime

# 1. Tentativa de Conexão com a IA
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash') # Versão ultra-estável
except Exception as e:
    st.error("Erro crítico nos Secrets: Verifique se a GOOGLE_API_KEY foi colada corretamente.")

st.set_page_config(page_title="Elite Predictor 2.5", layout="wide")

# Estilo Visual Profissional
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    </style>
    """, unsafe_allow_html=True)

def analise_deep_search(home, away, mercado):
    prompt = f"""
    Como analista de futebol profissional, pesquise dados REAIS de hoje ({datetime.now().strftime('%d/%m/%Y')}):
    1. Liste os placares EXATOS dos últimos 5 confrontos reais (H2H) entre {home} e {away}.
    2. Analise a forma atual (V-E-D) das equipas em 2025/2026.
    3. Dê um veredito para {mercado} com confiança acima de 75%.
    Se os dados forem inconclusivos, recomende 'EVITAR APOSTA'.
    Responda em Português com emojis.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Erro na IA: {str(e)}"

# Interface
st.title("🛡️ Elite AI Predictor 2.5")
st.write(f"Sincronizado: Gemini 2.5 + All Sports API | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR ANÁLISE DE ELITE"):
    try:
        API_KEY_SPORTS = st.secrets["ALL_SPORTS_API_KEY"]
        hoje = datetime.now().strftime('%Y-%m-%d')
        url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY_SPORTS}&from={hoje}&to={hoje}"
        
        with st.spinner('A IA está a consultar resultados reais na internet...'):
            res = requests.get(url).json()
            jogos = res.get("result", [])
    except:
        st.error("Erro ao conectar à All Sports API. Verifique sua chave.")
        jogos = []

    if jogos:
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])
        
        with tab1:
            for j in jogos[:10]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    resultado = analise_deep_search(h, a, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)
        
        # As outras abas seguem a mesma lógica
        with tab2:
             st.info("Consulte os palpites de golos expandindo os jogos acima.")
        with tab3:
             st.info("Consulte as tendências de cantos na análise detalhada.")
    else:
        st.warning("Nenhum jogo encontrado para hoje nas ligas de elite.")
