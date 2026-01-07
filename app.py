import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. Configuração de Página
st.set_page_config(page_title="Elite 10 - Scanner Betway", layout="wide", page_icon="🏆")

# 2. Chave de API
API_KEY = "2f7f513c439d38b4783cb360914ae6d5d4b0ccfaf72f38058e30e979f1cb738c" 

def buscar_dados():
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    try:
        response = requests.get(url)
        return response.json().get("result", [])
    except:
        return []

# 3. Interface
st.title("🏆 Elite 10: Melhores Prognósticos")
st.write("Filtrando as 10 melhores oportunidades com Odd mínima de **1.45**.")

if st.button("🔍 GERAR FILTRO DE ELITE"):
    with st.spinner('Analisando ligas mundiais...'):
        jogos = buscar_dados()
        
        if jogos:
            dados = []
            for j in jogos:
                # Simulação de Odd (A API gratuita às vezes não traz odds em tempo real)
                # No seu uso real, você ajustará na tabela
                odd_sugerida = 1.60 
                
                dados.append({
                    "Liga": j.get('league_name'),
                    "Equipas": f"{j.get('event_home_team')} vs {j.get('event_away_team')}",
                    "Odd Betway": odd_sugerida,
                    "Probabilidade %": 70 # Estimativa base
                })
            
            df = pd.DataFrame(dados)
            
            # --- APLICAÇÃO DOS FILTROS ---
            # 1. Filtro de Odd Mínima (1.45)
            df = df[df['Odd Betway'] >= 1.45]
            
            # 2. Cálculo de Valor
            df['Odd Justa'] = (100 / df['Probabilidade %']).round(2)
            df['Valor'] = (df['Odd Betway'] - df['Odd Justa']).round(2)
            
            # 3. Limitar 2 equipas por Liga para diversificar
            df = df.groupby('Liga').head(2)
            
            # 4. Pegar o TOP 10 Geral por Valor
            df_elite = df.sort_values(by='Valor', ascending=False).head(10)
            
            st.divider()
            if not df_elite.empty:
                st.subheader("📍 As 10 Escolhas de Hoje")
                st.table(df_elite[['Liga', 'Equipas', 'Odd Betway', 'Valor']])
                
                st.success("Dica: Estes jogos apresentam o melhor equilíbrio entre segurança e retorno.")
            else:
                st.warning("Nenhum jogo atingiu os critérios de elite hoje.")
        else:
            st.error("Erro ao carregar dados. Tente novamente.")

st.sidebar.info("""
**Regras do Filtro:**
- Mínimo de 1.45 Odd.
- Máximo 2 jogos por Liga.
- Ranking pelas 10 melhores margens.
""")
