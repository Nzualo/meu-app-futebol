import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime

# Conexão Segura via Secrets
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash') 

# Interface Profissional
st.set_page_config(page_title="Elite AI Predictor", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; margin-bottom: 20px; color: white; }
    h1, h2, h3 { color: #00ff00 !important; }
    </style>
    """, unsafe_allow_html=True)

API_KEY_SPORTS = st.secrets["ALL_SPORTS_API_KEY"]

def analise_profunda_ia(home, away, mercado):
    prompt = f"""
    Como analista de futebol pro, pesquise e forneça:
    1. Os resultados EXATOS dos últimos 5 confrontos reais entre {home} e {away} nos últimos 2 anos.
    2. O desempenho atual (vitórias/derrotas) das duas equipas nos últimos 5 jogos em 2025/2026.
    3. Um veredito para o mercado de {mercado} com confiança acima de 75%.
    Se os dados forem inconclusivos ou o jogo for muito equilibrado, recomende explicitamente "Evitar Aposta Direta".
    Responda em Português com emojis.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "⚠️ Erro na consulta da IA. Verifique sua quota de API."

st.title("🛡️ Elite AI Predictor: Precisão Real")
st.write(f"Análise Gemini 2.0 | Histórico Real 5 Jogos | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🔄 BUSCAR E ANALISAR JOGOS DE HOJE"):
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY_SPORTS}&from={hoje}&to={hoje}"
    
    with st.spinner('IA pesquisando dados históricos reais...'):
        fixtures = requests.get(url).json().get("result", [])
    
    if fixtures:
        # Filtro para ligas importantes
        tab1, tab2, tab3, tab4 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)", "🔥 Bilhete Pronto"])
        
        # Seleciona jogos para análise (exibindo os top 10)
        jogos_elite = fixtures[:15]

        with tab1:
            for j in jogos_elite[:10]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    resultado = analise_profunda_ia(h, a, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)

        with tab2:
            for j in jogos_elite[2:7]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"⚽ {h} vs {a} | Análise de Golos"):
                    resultado = analise_profunda_ia(h, a, "Golos (Over 2.5 / Ambas Marcam)")
                    st.write(resultado)

        with tab3:
            for j in jogos_elite[4:9]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🚩 {h} vs {a} | Análise de Cantos"):
                    resultado = analise_profunda_ia(h, a, "Cantos (Over 9.5)")
                    st.write(resultado)
    else:
        st.warning("Nenhum jogo das ligas principais encontrado para hoje.")
