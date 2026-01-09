import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz
import random

# 1. Configurações Iniciais
moz_tz = pytz.timezone('Africa/Maputo')
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Elite Predictor 2.6", layout="wide", page_icon="🛡️")

# Estilo Dark Mode Premium
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 15px; border-radius: 12px; border-left: 8px solid #00ff00; color: white; margin-bottom: 15px; }
    .card-zebra { background-color: #1a1c24; padding: 15px; border-radius: 12px; border-left: 8px solid #ff00ff; color: white; margin-bottom: 15px; }
    .stButton>button { width: 100%; border-radius: 10px; background-color: #00ff00; color: black; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def analise_ia(home, away, mercado, extra_info=""):
    """Consulta o ChatGPT com foco em dados reais 2023-2026"""
    prompt = f"""
    ANALISTA DE ELITE: Analise {home} vs {away} para {mercado}. {extra_info}
    1. H2H (2023-2026): Liste placares reais dos últimos 5 jogos.
    2. ODDS: Valide se a probabilidade real é maior que a odd sugerida.
    3. VEREDITO: Apenas factos para lucro. Confiança > 75%.
    Responda em Português, curto e com emojis.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Algoritmo de alta precisão para Betway Moçambique."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro ao consultar IA. Tente o refresh."

# 2. Lógica de Horário e API
agora_moz = datetime.now(moz_tz)
st.title("🛡️ Elite Intelligence Scanner 2.6")

def buscar_e_filtrar():
    API_KEY = st.secrets["ALL_SPORTS_API_KEY"]
    d_alvo = agora_moz
    d_str = d_alvo.strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={d_str}&to={d_str}"
    
    try:
        res = requests.get(url).json().get("result", [])
        # Filtra jogos futuros
        jogos = [j for j in res if datetime.strptime(j['event_time'], '%H:%M').time() > agora_moz.time()]
        
        # Se não houver mais jogos hoje, busca amanhã
        if not jogos:
            amanha = d_alvo + timedelta(days=1)
            d_str = amanha.strftime('%Y-%m-%d')
            url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={d_str}&to={d_str}"
            jogos = requests.get(url).json().get("result", [])
            st.info(f"📅 Agenda de Amanhã: {amanha.strftime('%d/%m/%Y')}")
        
        random.shuffle(jogos) # Garante que o Refresh mude os jogos
        return jogos
    except:
        return []

# Botão de Refresh
if st.sidebar.button("🔄 REFRESH (NOVOS JOGOS)"):
    st.cache_data.clear()
    st.rerun()

jogos_pool = buscar_e_filtrar()

if jogos_pool:
    tabs = st.tabs(["🏆 1x2", "⚽ Ambas Y/N", "📈 Over 1.5/2.5", "👥 DC + Over", "🔥 DC + Ambas", "🚩 Cantos +8.5", "🟣 ZEBRAS (Odds 4-11)"])
    
    # Mercados definidos
    mercados = [
        ("Vencedor (1x2)", 0, 0),
        ("Ambas Marcam", 10, 1),
        ("Total de Golos (+1.5/2.5)", 20, 2),
        ("Dupla Chance e Over 1.5", 30, 3),
        ("Dupla Chance e Ambas Marcam", 40, 4),
        ("Cantos (+8.5)", 50, 5),
    ]

    for nome, start, idx in mercados:
        with tabs[idx]:
            st.subheader(f"Top 10: {nome}")
            # Pega 10 jogos sem repetir com as outras abas
            lista = jogos_pool[start : start + 10]
            for j in lista:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    analise = analise_ia(h, a, nome)
                    st.markdown(f'<div class="card-elite">{analise}</div>', unsafe_allow_html=True)

    # Aba Especial: Zebras Enganadoras
    with tabs[6]:
        st.subheader("🟣 Top 10: Odds Enganadoras (4.0 - 11.0)")
        st.caption("Equipas subestimadas pelas casas com alto potencial de ganhar ou empatar.")
        zebras = jogos_pool[60 : 70] # Seleciona um grupo diferente para as zebras
        for j in zebras:
            h, a = j['event_home_team'], j['event_away_team']
            with st.expander(f"🔥 SURPRESA: {j['event_time']} | {h} vs {a}"):
                analise = analise_ia(h, a, "Zebra/Underdog", "Foca em encontrar valor em odds altas de 4 a 11.")
                st.markdown(f'<div class="card-zebra">{analise}</div>', unsafe_allow_html=True)
else:
    st.error("Não foi possível carregar os jogos. Verifique a conexão.")
