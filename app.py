import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime
import pytz

# 1. Configuração de Fuso Horário e API
moz_tz = pytz.timezone('Africa/Maputo')
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Scanner Elite Pro - MOZ", layout="wide")

# Estilo Visual Focado em Performance
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    .status-live { color: #ff0000; font-weight: bold; animation: blinker 1s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    </style>
    """, unsafe_allow_html=True)

def analise_precisa_gpt(home, away, mercado):
    """Análise técnica fria focada em lucro (H2H 2023-2026)"""
    prompt = f"""
    ANALISTA TÉCNICO: Forneça dados brutos e probabilidade real para {home} vs {away}.
    1. H2H (2023-2026): Liste apenas placares REAIS dos últimos 5 confrontos.
    2. DESEMPENHO: Forma física e técnica das equipas nos últimos 3 meses.
    3. VEREDITO: Probabilidade matemática para {mercado}.
    4. ALVO: Apenas prognósticos com confiança > 75%.
    ESTILO: Sem opiniões, apenas factos e números. Responda em Português.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "És um algoritmo de previsão desportiva de alta precisão."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro na consulta de dados."

# 2. Interface e Lógica de Horário
st.title("🏆 Elite Intelligence Scanner")
agora_moz = datetime.now(moz_tz)
st.write(f"📍 Fuso Horário: **Maputo (GMT+2)** | 🕒 Hora Atual: **{agora_moz.strftime('%H:%M')}**")

if st.button("🚀 VARREDURA DE JOGOS FUTUROS"):
    API_KEY = st.secrets["ALL_SPORTS_API_KEY"]
    hoje = agora_moz.strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={hoje}&to={hoje}"
    
    with st.spinner('A filtrar jogos por decorrer...'):
        res = requests.get(url).json()
        todos_jogos = res.get("result", [])
        
        # FILTRO DE HORÁRIO: Apenas jogos cuja hora seja maior que a hora atual de Moçambique
        jogos_filtrados = []
        for j in todos_jogos:
            hora_jogo = datetime.strptime(j['event_time'], '%H:%M').time()
            if hora_jogo > agora_moz.time():
                jogos_filtrados.append(j)

    if jogos_filtrados:
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos", "🚩 Cantos"])
        
        with tab1:
            st.subheader(f"Próximos Jogos (A partir das {agora_moz.strftime('%H:%M')})")
            for j in jogos_filtrados[:12]:
                home, away = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {home} vs {away}"):
                    analise = analise_precisa_gpt(home, away, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{analise}</div>', unsafe_allow_html=True)
        
        with tab2:
            for j in jogos_filtrados[2:7]:
                home, away = j['event_home_team'], j['event_away_team']
                with st.expander(f"⚽ {home} vs {away} | Golos"):
                    st.write(analise_precisa_gpt(home, away, "Golos (Over 2.5)"))
                    
        with tab3:
            for j in jogos_filtrados[4:9]:
                home, away = j['event_home_team'], j['event_away_team']
                with st.expander(f"🚩 {home} vs {away} | Cantos"):
                    st.write(analise_precisa_gpt(home, away, "Cantos (Over 9.5)"))
    else:
        st.warning("Não existem mais jogos agendados para hoje após este horário.")
