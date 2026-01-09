import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz

# 1. Configuração de Fuso Horário e OpenAI
moz_tz = pytz.timezone('Africa/Maputo')

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception as e:
    st.error("Erro: Verifique a OPENAI_API_KEY nos Secrets.")

st.set_page_config(page_title="Elite Scanner Pro", layout="wide")

# Estilo Visual Profissional
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 20px; border-radius: 15px; border-left: 10px solid #00ff00; color: white; margin-bottom: 20px; }
    .data-badge { background-color: #00ff00; color: black; padding: 5px 15px; border-radius: 20px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def analise_precisa_gpt(home, away, mercado):
    """Análise fria e técnica: H2H 2023-2026"""
    prompt = f"""
    ANALISTA: Analise {home} vs {away} para {mercado}.
    1. H2H (2023-2026): Liste resultados REAIS dos últimos 5 jogos.
    2. FORMA: Desempenho técnico atual.
    3. VEREDITO: Probabilidade matemática > 75%.
    Sem opiniões. Apenas factos para lucro.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Mais rápido e estável para evitar erros de tempo
            messages=[{"role": "system", "content": "Algoritmo de previsão desportiva."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception:
        return "⚠️ Erro na consulta de dados da IA. Tente novamente."

# 2. Lógica de Busca de Jogos
agora_moz = datetime.now(moz_tz)
st.title("🏆 Elite Intelligence Scanner")
st.write(f"📍 Maputo: **{agora_moz.strftime('%H:%M')}**")

def carregar_jogos(data_alvo):
    API_KEY = st.secrets["ALL_SPORTS_API_KEY"]
    data_str = data_alvo.strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={data_str}&to={data_str}"
    try:
        res = requests.get(url).json()
        return res.get("result", [])
    except:
        return []

if st.button("🚀 INICIAR VARREDURA"):
    # Busca HOJE
    jogos = carregar_jogos(agora_moz)
    
    # Filtro de horário: apenas jogos que começam DEPOIS de agora em Moçambique
    jogos_filtrados = [j for j in jogos if datetime.strptime(j['event_time'], '%H:%M').time() > agora_moz.time()]
    data_exibicao = agora_moz.strftime('%d/%m/%Y')

    # Se não houver jogos hoje, pula para AMANHÃ automaticamente
    if not jogos_filtrados:
        st.warning("🌙 Sem mais jogos para hoje. Buscando agenda de AMANHÃ...")
        amanha = agora_moz + timedelta(days=1)
        jogos_filtrados = carregar_jogos(amanha)
        data_exibicao = amanha.strftime('%d/%m/%Y')

    if jogos_filtrados:
        st.markdown(f"Exibindo jogos de: <span class='data-badge'>{data_exibicao}</span>", unsafe_allow_html=True)
        tab1, tab2, tab3 = st.tabs(["🏆 Vitória", "⚽ Golos", "🚩 Cantos"])
        
        with tab1:
            for j in jogos_filtrados[:15]:
                h, a = j['event_home_team'], j['event_away_team']
                with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                    analise = analise_precisa_gpt(h, a, "Vencedor (1x2)")
                    st.markdown(f'<div class="card-elite">{analise}</div>', unsafe_allow_html=True)
        # (Outras abas seguem a mesma lógica...)
    else:
        st.error("Não foram encontrados jogos para hoje nem para amanhã.")
