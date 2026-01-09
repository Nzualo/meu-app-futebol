import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz

# 1. Configuração de Fuso Horário e IA
moz_tz = pytz.timezone('Africa/Maputo')
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Elite Scanner Pro", layout="wide")

# Estilo Visual Dark Premium
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 15px; border-radius: 12px; border-left: 8px solid #00ff00; color: white; margin-bottom: 15px; }
    .data-badge { background-color: #00ff00; color: black; padding: 5px 12px; border-radius: 15px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def buscar_h2h_real(id_home, id_away):
    """Extrai os últimos 5 confrontos REAIS da API-Football para evitar divergências"""
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': st.secrets["FOOTBALL_API_KEY"]}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("response", [])
    except:
        return []

def analise_fria_gpt(home, away, h2h_lista, mercado):
    """O ChatGPT analisa apenas os dados reais fornecidos pela API"""
    dados_brutos = "\n".join([f"{m['fixture']['date'][:10]}: {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}" for m in h2h_lista])
    
    prompt = f"""
    ANALISTA MATEMÁTICO: Analise {home} vs {away} para o mercado {mercado}.
    HISTÓRICO REAL (2023-2026) FORNECIDO PELA API:
    {dados_brutos}
    
    TAREFA: Baseie-se APENAS nos dados acima para calcular a probabilidade.
    1. Veredito direto para lucro (Odd min 1.30).
    2. Confiança deve ser > 75%. Se for menor, recomende 'EVITAR'.
    Sem opiniões. Apenas factos e números em Português.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Algoritmo de precisão estatística."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro na análise da IA."

# 2. Interface e Lógica de Tempo (Maputo GMT+2)
agora_moz = datetime.now(moz_tz)
st.title("🛡️ Elite Intelligence Scanner 2.5")
st.write(f"🕒 Hora Maputo: **{agora_moz.strftime('%H:%M')}**")

def carregar_jogos(data_alvo):
    headers = {'x-rapidapi-key': st.secrets["FOOTBALL_API_KEY"]}
    url = f"https://v3.football.api-sports.io/fixtures?date={data_alvo.strftime('%Y-%m-%d')}"
    res = requests.get(url, headers=headers).json()
    return res.get("response", [])

if st.button("🚀 INICIAR VARREDURA"):
    fixtures = carregar_jogos(agora_moz)
    # Filtra apenas jogos futuros
    jogos_filtrados = [f for f in fixtures if datetime.fromisoformat(f['fixture']['date']).astimezone(moz_tz) > agora_moz]
    data_label = agora_moz.strftime('%d/%m/%Y')

    if not jogos_filtrados:
        st.warning("🌙 Sem mais jogos hoje. Buscando amanhã...")
        amanha = agora_moz + timedelta(days=1)
        jogos_filtrados = carregar_jogos(amanha)
        data_label = amanha.strftime('%d/%m/%Y')

    if jogos_filtrados:
        st.markdown(f"🗓️ Jogos de: <span class='data-badge'>{data_label}</span>", unsafe_allow_html=True)
        tab_list = ["🏆 1x2", "⚽ Ambas Y/N", "📈 Over 1.5/2.5", "👥 DC+Over", "🔥 DC+Ambas", "🚩 Cantos +8.5", "🟣 ZEBRAS"]
        tabs = st.tabs(tab_list)
        
        # Mercados solicitados
        mercados = ["Vencedor (1x2)", "Ambas Marcam", "Over 1.5/2.5", "Dupla Chance + Over", "Dupla Chance + Ambas", "Cantos +8.5", "Zebra (Odd 4-11)"]

        for i, mercado in enumerate(mercados):
            with tabs[i]:
                # Mostra os primeiros 10 jogos da lista para cada mercado
                for f in jogos_filtrados[:10]:
                    h, a = f['teams']['home'], f['teams']['away']
                    with st.expander(f"🕒 {f['fixture']['date'][11:16]} | {h['name']} vs {a['name']}"):
                        h2h_data = buscar_h2h_real(h['id'], a['id'])
                        analise = analise_fria_gpt(h['name'], a['name'], h2h_data, mercado)
                        st.markdown(f'<div class="card-elite">{analise}</div>', unsafe_allow_html=True)
    else:
        st.error("Nenhum jogo encontrado.")
