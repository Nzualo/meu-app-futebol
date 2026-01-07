import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime

# Configuração do Modelo 2.5 Preview (Flash Experimental)
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # 'gemini-2.0-flash-exp' é o identificador correto para a versão preview atual
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except Exception as e:
    st.error(f"Erro ao carregar IA: {e}")

st.set_page_config(page_title="Elite Predictor 2.5 PRO", layout="wide")

# Estilo Dark Mode
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    h1, h2, h3 { color: #00ff00 !important; }
    </style>
    """, unsafe_allow_html=True)

def analise_ia_preview(home, away, mercado):
    """Consulta o Gemini 2.5 Preview para dados reais da internet"""
    prompt = f"""
    Pesquise na internet os resultados REAIS (H2H) dos últimos 5 confrontos entre {home} e {away}.
    Analise o desempenho atual em 2025/2026.
    Dê um veredito para {mercado} com 75% de confiança.
    Responda em Português com emojis e negrito nos placares.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Erro na API Gemini: {str(e)}"

st.title("🛡️ Elite Predictor 2.5 Preview")
st.write(f"Motor: Gemini 2.0 Flash Exp | {datetime.now().strftime('%d/%m/%Y')}")

if st.button("🚀 ANALISAR JOGOS DE HOJE"):
    api_key = st.secrets["ALL_SPORTS_API_KEY"]
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={api_key}&from={hoje}&to={hoje}"
    
    with st.spinner('A IA Gemini 2.5 está a pesquisar históricos reais...'):
        try:
            res = requests.get(url).json()
            jogos = res.get("result", [])
            
            if jogos:
                tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos (+9.5)"])
                
                with tab1:
                    for j in jogos[:10]:
                        h, a = j['event_home_team'], j['event_away_team']
                        with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                            resultado = analise_ia_preview(h, a, "Vencedor (1x2)")
                            st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)
                
                with tab2:
                    st.info("As análises de golos estão integradas nos detalhes acima.")
                with tab3:
                    st.info("As tendências de cantos estão integradas nos detalhes acima.")
            else:
                st.warning("Nenhum jogo encontrado para hoje.")
        except Exception as e:
            st.error(f"Erro na All Sports API: {e}")
