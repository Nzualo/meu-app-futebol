import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. Configuração de Estilo e Página
st.set_page_config(page_title="Scanner Betway Pro", layout="wide", page_icon="⚽")

# 2. Configuração da API (Sua chave integrada)
API_KEY = "2f7f513c439d38b4783cb360914ae6d5d4b0ccfaf72f38058e30e979f1cb738c" 

def buscar_jogos_do_dia():
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    
    try:
        response = requests.get(url)
        data = response.json()
        return data.get("result", [])
    except Exception as e:
        return []

# 3. Interface Principal
st.title("🤖 Smart Scanner Betway")
st.write(f"Analisando jogos de hoje: **{datetime.now().strftime('%d/%m/%Y')}**")

if st.button("📡 BUSCAR JOGOS DO DIA"):
    with st.spinner('Acedendo aos dados...'):
        lista_jogos = buscar_jogos_do_dia()
        
        if lista_jogos:
            dados_limpos = []
            for jogo in lista_jogos:
                dados_limpos.append({
                    "Hora": jogo.get('event_time'),
                    "Liga": jogo.get('league_name'),
                    "Equipas": f"{jogo.get('event_home_team')} vs {jogo.get('event_away_team')}",
                    "Odd Betway": 2.10,
                    "Sua Nota %": 50
                })
            
            df = pd.DataFrame(dados_limpos)
            
            st.divider()
            st.subheader("📋 Painel de Edição")
            st.info("Ajuste as Notas e Odds na tabela:")

            # Tabela Editável
            df_editado = st.data_editor(df, use_container_width=True)
            
            # Cálculos
            df_editado['Odd Justa'] = (100 / df_editado['Sua Nota %']).round(2)
            df_editado['Valor'] = (df_editado['Odd Betway'] - df_editado['Odd Justa']).round(2)

            # Exibição simplificada para evitar ImportError
            st.divider()
            st.subheader("🎯 Melhores Entradas (Value Bets)")
            
            picks = df_editado[df_editado['Valor'] > 0].sort_values(by='Valor', ascending=False)
            
            if not picks.empty:
                # Mostra a tabela de forma simples e direta
                st.table(picks[['Hora', 'Equipas', 'Odd Betway', 'Odd Justa', 'Valor']])
                st.success("💎 Apostas com valor matemático encontradas!")
            else:
                st.warning("Nenhuma aposta de valor detectada. Aumente a nota do time ou a Odd.")
        else:
            st.error("Nenhum jogo encontrado. Verifique sua conexão ou chave API.")
