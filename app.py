import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz

# 1. Configurações de Fuso Horário e API
moz_tz = pytz.timezone('Africa/Maputo')
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Elite Scanner - MOZ", layout="wide")

# Estilo Visual Dark Mode
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    .data-badge { background-color: #00ff00; color: black; padding: 5px 12px; border-radius: 20px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def analise_precisa_gpt(home, away, mercado):
    """Análise técnica direta: H2H 2023-2026 e Probabilidade Fria"""
    prompt = f"""
    ESTATÍSTICO: Analise {home} vs {away} para o mercado {mercado}.
    1. H2H (2023-2026): Liste apenas resultados REAIS dos últimos 5 jogos.
    2. FORMA: Desempenho técnico atual (últimos 5 jogos).
    3. VEREDITO: Probabilidade matemática de vitória. 
    REGRAS: Apenas confiança > 75%. Sem opiniões, apenas factos para lucro.
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

# 2. Interface e Lógica de Busca
st.title("🛡️ Elite Intelligence Scanner")
agora_moz = datetime.now(moz_tz)
st.write(f"🕒 Hora Maputo: **{agora_moz.strftime('%H:%M')}**")

def carregar_jogos(data_alvo):
    API_KEY = st.secrets["ALL_SPORTS_API_KEY"]
    data_str = data_alvo.strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={data_str}&to={data_str}"
    res = requests.get(url).json()
    return res.get("result", [])

if st.button("🚀 INICIAR VARREDURA DE ELITE"):
    # Busca jogos de HOJE
    jogos = carregar_jogos(agora_moz)
    
    # Filtra jogos que ainda não começaram (Hora de Moçambique)
    jogos_filtrados = [j for j in jogos if datetime.strptime(j['event_time'], '%H:%M').time() > agora_moz.time()]
    data_exibicao = agora_moz.strftime('%d/%m/%Y')

    # SE NÃO HOUVER JOGOS HOJE, BUSCA AMANHÃ
    if not jogos_filtrados:
        st.warning("⚠️ Não existem mais jogos para hoje. A carregar agenda de AMANHÃ...")
        amanha = agora_moz + timedelta(days=1)
        jogos_filtrados = carregar_jogos(amanha)
        data_exibicao = amanha.strftime('%d/%m/%Y')

    if jogos_filtrados:
        st.markdown(f"Exibindo jogos de: <span class='data-badge'>{data_exibicao}</span>", unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória (1x2)", "⚽ Golos Elite", "🚩 Cantos"])
        
        with tab1:
            for j in jogos_filtrados[:12]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    analise = analise_precisa_gpt(h, a, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{analise}</div>', unsafe_allow_html=True)

        with tab2:
            for j in jogos_filtrados[2:7]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"⚽ {h} vs {a} | Over 2.5"):
                    st.write(analise_precisa_gpt(h, a, "Golos (Over 2.5)"))

        with tab3:
            for j in jogos_filtrados[4:9]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🚩 {h} vs {a} | Cantos"):
                    st.write(analise_precisa_gpt(h, a, "Cantos (Over 9.5)"))
    else:
        st.error("Nenhum jogo encontrado para hoje ou amanhã.")
