import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime

# 1. Configuração de Estilo Profissional
st.set_page_config(page_title="Elite Predictor 2.5", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; font-family: 'Arial Black'; }
    </style>
    """, unsafe_allow_html=True)

# 2. Inicialização Segura da IA
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # Usando o modelo 1.5-pro para maior precisão em 2026
    model = genai.GenerativeModel('gemini-1.5-pro')
except Exception as e:
    st.error("⚠️ Erro de Configuração: Verifique sua Chave Google nos Secrets.")

def analise_ia_pro(home, away, mercado):
    prompt = f"""
    Como analista senior, pesquise dados REAIS de 2025/2026 para: {home} vs {away}.
    1. Liste placares REAIS dos últimos 5 confrontos (H2H) dos últimos 2 anos.
    2. Analise a forma atual (V-E-D) das equipas.
    3. Dê veredito para {mercado} com confiança acima de 75%.
    Se for arriscado, escreva 'EVITAR'. Responda em Português com emojis.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Erro na IA: {str(e)}"

# 3. Interface Principal
st.title("🛡️ Elite Predictor: Inteligência Real")
st.write(f"Sincronizado: Gemini 2.5 + All Sports API | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 EXECUTAR ANÁLISE DE ELITE"):
    try:
        api_key_sports = st.secrets["ALL_SPORTS_API_KEY"]
        hoje = datetime.now().strftime('%Y-%m-%d')
        url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={api_key_sports}&from={hoje}&to={hoje}"
        
        with st.spinner('Buscando jogos e consultando a IA...'):
            res = requests.get(url).json()
            jogos = res.get("result", [])
    except:
        st.error("Erro nos Secrets: 'ALL_SPORTS_API_KEY' não encontrada.")
        jogos = []

    if jogos:
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])
        
        with tab1:
            for j in jogos[:10]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    st.markdown(f'<div class="card-elite">{analise_ia_pro(h, a, "Vencedor (1x2)")}</div>', unsafe_allow_html=True)

        with tab2:
            for j in jogos[2:7]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"⚽ {h} vs {a} | Golos"):
                    st.write(analise_ia_pro(h, a, "Golos (Over 2.5 / BTTS)"))

        with tab3:
            for j in jogos[4:9]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🚩 {h} vs {a} | Cantos"):
                    st.write(analise_ia_pro(h, a, "Cantos (Over 9.5)"))
    else:
        st.warning("Nenhum jogo encontrado para hoje.")
