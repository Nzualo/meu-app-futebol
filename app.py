import streamlit as st
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import pytz

# Configuração de Fuso e IA
moz_tz = pytz.timezone('Africa/Maputo')
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-2.0-flash-exp')

def buscar_h2h_oficial(id_home, id_away):
    """Extrai os últimos 5 jogos REAIS da API-Football para evitar divergências"""
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': st.secrets["FOOTBALL_API_KEY"]}
    res = requests.get(url, headers=headers).json()
    return res.get("response", [])

def gerar_analise_fiel(home, away, h2h_lista, mercado):
    """Obriga a IA a usar APENAS os dados fornecidos pela API"""
    dados_brutos = "\n".join([f"{m['fixture']['date'][:10]}: {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}" for m in h2h_lista])
    
    prompt = f"""
    PROIBIDO INVENTAR. Use apenas estes dados REAIS de H2H para {home} vs {away}:
    {dados_brutos}
    
    Analise para o mercado: {mercado}
    1. A tendência é de lucro real (Odd > 1.30)?
    2. Veredito matemático seco (Confiança > 75%).
    3. Se houver divergência nos dados, diga 'DADOS INCONCLUSIVOS'.
    """
    response = model.generate_content(prompt)
    return response.text

# Lógica de Horário Moçambique
agora_moz = datetime.now(moz_tz)
st.title("🛡️ Elite Intelligence Scanner 2.5")
st.write(f"🕒 Hora Maputo: {agora_moz.strftime('%H:%M')}")

if st.button("🚀 VARREDURA SEM ERROS"):
    # Busca jogos de hoje
    headers = {'x-rapidapi-key': st.secrets["FOOTBALL_API_KEY"]}
    url = f"https://v3.football.api-sports.io/fixtures?date={agora_moz.strftime('%Y-%m-%d')}"
    
    with st.spinner('A extrair dados oficiais...'):
        fixtures = requests.get(url, headers=headers).json().get("response", [])
        # Filtra jogos que ainda não começaram
        jogos_futuros = [f for f in fixtures if datetime.fromisoformat(f['fixture']['date']).astimezone(moz_tz) > agora_moz]

    if jogos_futuros:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏆 1x2", "⚽ Ambas", "📈 Over", "👥 DC+Over", "🔥 DC+Ambas", "🚩 Cantos"])
        
        for idx, f in enumerate(jogos_futuros[:10]):
            h, a = f['teams']['home'], f['teams']['away']
            h2h_reais = buscar_h2h_oficial(h['id'], a['id'])
            
            with tab1: # Exemplo Aba 1x2
                with st.expander(f"🕒 {f['fixture']['date'][11:16]} | {h['name']} vs {a['name']}"):
                    analise = gerar_analise_fiel(h['name'], a['name'], h2h_reais, "Vencedor 1x2")
                    st.markdown(f"**Análise Baseada em Factos:**\n{analise}")
    else:
        st.warning("Sem mais jogos hoje. Verifique a agenda de amanhã.")
