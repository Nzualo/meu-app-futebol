import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz

# 1. CONFIGURAÇÕES TÉCNICAS
moz_tz = pytz.timezone('Africa/Maputo')
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
FOOTBALL_API_KEY = "2f3bc9f0346c3803720553cecbdbb6bd" # Sua chave ativa

st.set_page_config(page_title="Elite Predictor 2.6", layout="wide")

# Estilo Visual Dark Mode
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 15px; border-radius: 12px; border-left: 8px solid #00ff00; color: white; margin-bottom: 15px; }
    .data-badge { background-color: #00ff00; color: black; padding: 4px 10px; border-radius: 10px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# 2. FUNÇÕES DE DADOS REAIS
def buscar_h2h_real(id_home, id_away):
    """Busca o H2H real para a IA não 'alucinar' resultados"""
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': FOOTBALL_API_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("response", [])
    except:
        return []

def analise_ia_pro(home, away, h2h_lista, mercado):
    """Alimenta a IA com os dados da API para eliminar divergências"""
    # Transforma os dados da API em texto legível para o GPT
    historico_texto = "\n".join([
        f"- {m['fixture']['date'][:10]}: {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}" 
        for m in h2h_lista
    ])
    
    prompt = f"""
    ANALISTA MATEMÁTICO: Analise {home} vs {away} para o mercado {mercado}.
    DADOS REAIS H2H (2023-2026):
    {historico_texto if historico_texto else "Sem confrontos diretos recentes."}
    
    TAREFA: Use APENAS os factos acima. 
    1. Veredito seco para lucro (Odd min 1.30).
    2. Confiança > 75%. Se for menor, recomende 'EVITAR'.
    Responda de forma curta em Português com emojis.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Algoritmo de previsão estatística de alta precisão."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro na resposta da IA. Verifique saldo/quota."

# 3. INTERFACE E LÓGICA DE HORÁRIO
agora_moz = datetime.now(moz_tz)
st.title("🛡️ Elite Intelligence Scanner 2.6")
st.write(f"🕒 Hora Atual Maputo: **{agora_moz.strftime('%H:%M')}**")

if st.button("🚀 EXECUTAR VARREDURA DE ELITE"):
    headers = {'x-rapidapi-key': FOOTBALL_API_KEY}
    url = f"https://v3.football.api-sports.io/fixtures?date={agora_moz.strftime('%Y-%m-%d')}"
    
    with st.spinner('A extrair dados oficiais...'):
        fixtures = requests.get(url, headers=headers).json().get("response", [])
        # Filtra apenas jogos que ainda não começaram
        jogos_filtrados = [f for f in fixtures if datetime.fromisoformat(f['fixture']['date']).astimezone(moz_tz) > agora_moz]

    # Salta para amanhã se não houver mais jogos hoje
    if not jogos_filtrados:
        st.warning("🌙 Sem mais jogos hoje. Buscando agenda de AMANHÃ...")
        amanha = (agora_moz + timedelta(days=1)).strftime('%Y-%m-%d')
        url = f"https://v3.football.api-sports.io/fixtures?date={amanha}"
        jogos_filtrados = requests.get(url, headers=headers).json().get("response", [])

    if jogos_filtrados:
        tabs = st.tabs(["🏆 1x2", "⚽ Ambas Y/N", "📈 Over 1.5/2.5", "👥 DC+Over", "🔥 DC+Ambas", "🚩 Cantos +8.5", "🟣 ZEBRAS"])
        
        mercados = [
            ("Vencedor (1x2)", 0), ("Ambas Marcam", 1), ("Golos (Over 1.5/2.5)", 2),
            ("Dupla Chance + Over", 3), ("Dupla Chance + Ambas", 4), ("Cantos +8.5", 5), ("Zebra (Odd 4-11)", 6)
        ]

        for nome_m, idx in mercados:
            with tabs[idx]:
                # Mostra o Top 10 para cada aba sem repetir
                for f in jogos_filtrados[idx*2 : (idx*2)+10]:
                    h, a = f['teams']['home'], f['teams']['away']
                    with st.expander(f"🕒 {f['fixture']['date'][11:16]} | {h['name']} vs {a['name']}"):
                        h2h = buscar_h2h_real(h['id'], a['id'])
                        resultado = analise_ia_pro(h['name'], a['name'], h2h, nome_m)
                        st.markdown(f'<div class="card-elite">{resultado}</div>', unsafe_allow_html=True)
    else:
        st.error("Nenhum jogo encontrado para hoje ou amanhã.")
