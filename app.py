import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz

# 1. CONFIGURAÇÕES DE API E LOCALIZAÇÃO
# Detecta automaticamente ou usa Maputo/Inhassoro como base (GMT+2)
local_tz = pytz.timezone('Africa/Maputo') 
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
FOOTBALL_API_KEY = "2f3bc9f0346c3803720553cecbdbb6bd"

st.set_page_config(page_title="Elite Scanner - Inhassoro", layout="wide")

# Estilo Visual Dark
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 15px; border-radius: 12px; border-left: 8px solid #00ff00; color: white; margin-bottom: 15px; }
    .data-badge { background-color: #00ff00; color: black; padding: 5px 12px; border-radius: 15px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def buscar_h2h_real(id_home, id_away):
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': FOOTBALL_API_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("response", [])
    except: return []

def analise_ia_detalhada(home, away, h2h_lista, mercado):
    historico = "\n".join([f"- {m['fixture']['date'][:10]}: {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}" for m in h2h_lista])
    prompt = f"""
    ANALISTA PROFISSIONAL: Analise {home} vs {away} para {mercado}.
    DADOS REAIS H2H (2023-2026):
    {historico if historico else "Sem histórico recente."}
    
    TAREFA: Forneça o veredito com detalhes técnicos. Confiança > 75%. 
    Se não houver dados suficientes, não invente, diga 'DADOS INSUFICIENTES'.
    """
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content
    except: return "⚠️ IA temporariamente indisponível."

# 2. RELÓGIO E LÓGICA DE FILTRAGEM
agora_local = datetime.now(local_tz)
st.title("🛡️ Elite Intelligence Scanner 2.7")
# Exibição com Segundos como solicitado
st.write(f"📍 Localização: **Inhassoro/Maputo** | 🕒 Hora Atual: **{agora_local.strftime('%H:%M:%S')}**")

def carregar_dados_api(data_alvo):
    headers = {'x-rapidapi-key': FOOTBALL_API_KEY}
    url = f"https://v3.football.api-sports.io/fixtures?date={data_alvo.strftime('%Y-%m-%d')}"
    res = requests.get(url, headers=headers).json()
    return res.get("response", [])

if st.button("🚀 EXECUTAR VARREDURA EM TEMPO REAL"):
    # 1. Tenta buscar jogos de hoje
    fixtures = carregar_dados_api(agora_local)
    
    # FILTRO RIGOROSO: Hora e Minuto. Exclui jogos das 00:00 se já for 01:00.
    jogos_futuros = []
    for f in fixtures:
        # Converter hora do jogo para o fuso local para comparação justa
        hora_jogo_utc = datetime.fromisoformat(f['fixture']['date'].replace('Z', '+00:00'))
        hora_jogo_local = hora_jogo_utc.astimezone(local_tz)
        
        if hora_jogo_local > agora_local:
            jogos_futuros.append(f)

    # 2. Se não houver nada futuro para hoje, pula para amanhã
    data_mostrar = agora_local
    if not jogos_futuros:
        st.warning("🌙 Sem jogos futuros para hoje em Inhassoro. A buscar agenda de AMANHÃ...")
        data_mostrar = agora_local + timedelta(days=1)
        jogos_futuros = carregar_dados_api(data_mostrar)

    if jogos_futuros:
        st.markdown(f"🗓️ Agenda para: <span class='data-badge'>{data_mostrar.strftime('%d/%m/%Y')}</span>", unsafe_allow_html=True)
        
        tabs = st.tabs(["🏆 1x2", "⚽ Ambas", "📈 Over", "👥 DC+Over", "🔥 DC+Ambas", "🚩 Cantos", "🟣 ZEBRAS"])
        mercados = ["Vitória (1x2)", "Ambas Marcam", "Over 1.5/2.5", "Dupla Chance + Over", "Dupla Chance + Ambas", "Cantos +8.5", "Zebra (Odd 4-11)"]

        for i, mercado in enumerate(mercados):
            with tabs[i]:
                # Mostra o Top 10 por aba para garantir detalhes
                selecao = jogos_futuros[i*3 : (i*3)+10] # Garante que as abas mostrem jogos diferentes
                if not selecao: selecao = jogos_futuros[:10]
                
                for f in selecao:
                    h, a = f['teams']['home'], f['teams']['away']
                    # Mostrar hora local formatada no expander
                    hora_formatada = datetime.fromisoformat(f['fixture']['date'].replace('Z', '+00:00')).astimezone(local_tz).strftime('%H:%M')
                    
                    with st.expander(f"🕒 {hora_formatada} | {h['name']} vs {a['name']}"):
                        h2h = buscar_h2h_real(h['id'], a['id'])
                        detalhes = analise_ia_detalhada(h['name'], a['name'], h2h, mercado)
                        st.markdown(f'<div class="card-elite">{detalhes}</div>', unsafe_allow_html=True)
    else:
        st.error("Nenhum jogo encontrado na base de dados para as próximas 24 horas.")
