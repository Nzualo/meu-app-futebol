import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. Configuração de Estilo
st.set_page_config(page_title="Elite Predictor - Real Data", layout="wide")

st.markdown("""
    <style>
    .card-real { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; }
    .warning-card { border-left: 10px solid #ffcc00; background-color: #1a1c24; padding: 20px; border-radius: 15px; }
    </style>
    """, unsafe_allow_html=True)

API_KEY = "2f7f513c439d38b4783cb360914ae6d5d4b0ccfaf72f38058e30e979f1cb738c"

# FUNÇÃO PARA BUSCAR H2H REAL
def buscar_h2h_real(home_id, away_id):
    url = f"https://apiv2.allsportsapi.com/football/?met=H2H&APIkey={API_KEY}&firstTeamId={home_id}&secondTeamId={away_id}"
    try:
        res = requests.get(url).json()
        return res.get("result", {}).get("firstTeam_VS_secondTeam", [])[:5]
    except:
        return []

st.title("🛡️ Scanner de Precisão Real (Sem Simulação)")

if st.button("🔍 ANALISAR JOGOS COM DADOS REAIS"):
    hoje = datetime.now().strftime('%Y-%m-%d')
    url_fixtures = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    
    fixtures = requests.get(url_fixtures).json().get("result", [])
    
    if fixtures:
        for j in fixtures[:10]: # Analisando os 10 primeiros
            home_name = j['event_home_team']
            away_name = j['event_away_team']
            home_id = j['home_team_key']
            away_id = j['away_team_key']
            
            # BUSCA O H2H REAL DA API
            historico = buscar_h2h_real(home_id, away_id)
            
            # LÓGICA DE VEREDITO REAL
            vitorias_home = 0
            empates = 0
            for h in historico:
                score = h['event_final_result'].split(" - ")
                if int(score[0]) > int(score[1]): vitorias_home += 1
                elif int(score[0]) == int(score[1]): empates += 1
            
            # SÓ DÁ VITÓRIA SE TIVER DOMÍNIO REAL (Ex: + de 60% de vitórias no H2H)
            prob_real = (vitorias_home / len(historico)) * 100 if historico else 0
            
            with st.expander(f"📊 {home_name} vs {away_name}"):
                if prob_real >= 60:
                    st.markdown(f"""<div class="card-real">
                        <h4>✅ Veredito Real: Vitória do {home_name}</h4>
                        <p>Probabilidade baseada em H2H Real: {prob_real}%</p>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div class="warning-card">
                        <h4>⚠️ Jogo Equilibrado (Evitar Vitória Direta)</h4>
                        <p>O histórico real não mostra domínio claro. Sugestão: Chance Dupla ou Ambas Marcam.</p>
                    </div>""", unsafe_allow_html=True)
                
                st.write("**Últimos Resultados Reais (H2H):**")
                for h in historico:
                    st.write(f"📅 {h['event_date']}: {h['event_home_team']} {h['event_final_result']} {h['event_away_team']}")
    else:
        st.error("Não foi possível carregar os jogos de hoje.")
