import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. Configuração de Estilo e Página
st.set_page_config(page_title="Scanner Betway Pro", layout="wide", page_icon="⚽")

st.markdown("""
    <style>
    .stButton>button { 
        width: 100%; 
        border-radius: 10px; 
        background-color: #00ff00; 
        color: black; 
        font-weight: bold;
        height: 3em;
    }
    .main { background-color: #0e1117; }
    </style>
    """, unsafe_allow_html=True)

# 2. Configuração da API (Sua chave já inserida)
API_KEY = "2f7f513c439d38b4783cb360914ae6d5d4b0ccfaf72f38058e30e979f1cb738c" 

def buscar_jogos_do_dia():
    # Pegamos a data de hoje automaticamente
    hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    
    try:
        response = requests.get(url)
        data = response.json()
        return data.get("result", [])
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return []

# 3. Interface Principal
st.title("🤖 Smart Scanner Betway Moçambique")
st.write(f"Conectado com sucesso. Analisando jogos de: **{datetime.now().strftime('%d/%m/%Y')}**")

# Botão de Sincronização
if st.button("📡 BUSCAR JOGOS E ODDS DO DIA"):
    with st.spinner('Acedendo aos servidores de futebol...'):
        lista_jogos = buscar_jogos_do_dia()
        
        if lista_jogos:
            dados_limpos = []
            for jogo in lista_jogos:
                dados_limpos.append({
                    "Hora": jogo.get('event_time'),
                    "Liga": jogo.get('league_name'),
                    "Equipas": f"{jogo.get('event_home_team')} vs {jogo.get('event_away_team')}",
                    "Odd Betway": 2.10,  # Valor padrão para você editar
                    "Chance % (Sua nota)": 50  # Valor padrão para você editar
                })
            
            # Criar o DataFrame
            df = pd.DataFrame(dados_limpos)
            
            st.divider()
            st.subheader("📋 Painel de Análise Geral")
            st.info("Altere a 'Odd Betway' e a 'Chance %' diretamente na tabela abaixo:")

            # Tabela Editável
            df_editado = st.data_editor(
                df, 
                use_container_width=True, 
                num_rows="dynamic",
                column_config={
                    "Chance % (Sua nota)": st.column_config.NumberColumn(min_value=1, max_value=99),
                    "Odd Betway": st.column_config.NumberColumn(format="%.2f")
                }
            )
            
            # Cálculos de Valor
            df_editado['Odd Justa'] = (100 / df_editado['Chance % (Sua nota)']).round(2)
            df_editado['Lucro/Valor'] = (df_editado['Odd Betway'] - df_editado['Odd Justa']).round(2)

            # Exibição das Picks com Valor
            st.divider()
            st.subheader("🎯 Melhores Entradas (Value Bets)")
            
            # Filtro para mostrar apenas o que compensa
            picks = df_editado[df_editado['Lucro/Valor'] > 0].sort_values(by='Lucro/Valor', ascending=False)
            
            if not picks.empty:
                st.dataframe(
                    picks.style.background_gradient(cmap='Greens', subset=['Lucro/Valor']),
                    use_container_width=True
                )
                st.balloons()
            else:
                st.warning("Nenhuma aposta de valor detectada ainda. Ajuste as notas dos times ou procure odds maiores.")
        else:
            st.warning("Nenhum jogo encontrado para hoje. Verifique se a data está correta ou se a API expirou.")

# 4. Rodapé
st.markdown("---")
st.caption("All Sports API Integrada | Foco: Betway.co.mz | Moçambique 2024")
