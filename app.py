import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime

# Estilo e Configuração
st.set_page_config(page_title="Elite Predictor 2.5", layout="wide")
st.markdown("""<style>.card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }</style>""", unsafe_allow_html=True)

# Inicialização da IA com tratamento de erro de versão
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # Mudança para o modelo Flash para evitar erro 404
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Erro de Configuração: {e}")

def analise_ia_final(home, away, mercado):
    prompt = f"Analise o jogo {home} vs {away} (mercado: {mercado}). Liste os últimos 5 resultados H2H reais e dê um veredito de 75% de confiança. Use emojis e português."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Erro na IA: {e}"

st.title("🛡️ Elite Predictor 2.5 AI")

if st.button("🚀 EXECUTAR ANÁLISE DE ELITE"):
    api_key = st.secrets["ALL_SPORTS_API_KEY"]
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={api_key}&from={hoje}&to={hoje}"
    
    with st.spinner('A IA está a consultar dados reais...'):
        try:
            res = requests.get(url).json()
            jogos = res.get("result", [])
            
            if jogos:
                tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos", "🚩 Cantos"])
                with tab1:
                    for j in jogos[:10]:
                        h, a = j['event_home_team'], j['event_away_team']
                        with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                            st.markdown(f'<div class="card-elite">{analise_ia_final(h, a, "1x2")}</div>', unsafe_allow_html=True)
                with tab2:
                    st.info("Expanda os jogos na aba Vitória para ver detalhes de golos.")
                with tab3:
                    st.info("Detalhes de cantos incluídos na análise da IA.")
            else:
                st.warning("Nenhum jogo encontrado.")
        except:
            st.error("Erro ao buscar jogos. Verifique a ALL_SPORTS_API_KEY.")
