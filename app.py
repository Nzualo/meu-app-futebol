import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime, timedelta
import pytz

# Configuração de Fuso Horário e Cliente OpenAI
moz_tz = pytz.timezone('Africa/Maputo')
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Elite Scanner Multi-Aba", layout="wide")

# Estilo Visual Profissional
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card-elite { background-color: #1a1c24; padding: 15px; border-radius: 12px; border-left: 8px solid #00ff00; color: white; margin-bottom: 15px; }
    .data-badge { background-color: #00ff00; color: black; padding: 5px 12px; border-radius: 15px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def analise_tecnica(home, away, mercado):
    """Análise fria baseada em factos 2023-2026 para lucro real"""
    prompt = f"""
    ANALISTA MATEMÁTICO: Analise {home} vs {away} para o mercado {mercado}.
    1. H2H REAIS (2023-2026): Liste os resultados dos últimos 5 confrontos.
    2. ODDS/PROB: Confirmação técnica para Odds mínimas de 1.30.
    3. VEREDITO: Apenas se a confiança for > 75%. 
    Sem opiniões. Responda de forma curta e direta em Português.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Algoritmo de previsão desportiva de alta precisão."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro na consulta da IA."

# Lógica de Horário e Busca
agora_moz = datetime.now(moz_tz)
st.title("🛡️ Elite Intelligence Scanner 2.5")
st.write(f"🕒 Hora Atual Maputo: **{agora_moz.strftime('%H:%M')}**")

def buscar_jogos(data_alvo):
    API_KEY = st.secrets["ALL_SPORTS_API_KEY"]
    d_str = data_alvo.strftime('%Y-%m-%d')
    url = f"https://apiv2.allsportsapi.com/football/?met=Fixtures&APIkey={API_KEY}&from={d_str}&to={d_str}"
    try:
        res = requests.get(url).json()
        return res.get("result", [])
    except:
        return []

if st.button("🚀 INICIAR VARREDURA MULTI-ABA"):
    jogos = buscar_jogos(agora_moz)
    # Filtra apenas jogos futuros para o fuso de Moçambique
    jogos_finais = [j for j in jogos if datetime.strptime(j['event_time'], '%H:%M').time() > agora_moz.time()]
    data_label = agora_moz.strftime('%d/%m/%Y')

    if not jogos_finais:
        st.warning("🌙 Sem mais jogos hoje. Buscando amanhã...")
        amanha = agora_moz + timedelta(days=1)
        jogos_finais = buscar_jogos(amanha)
        data_label = amanha.strftime('%d/%m/%Y')

    if jogos_finais:
        st.markdown(f"🗓️ Jogos de: <span class='data-badge'>{data_label}</span>", unsafe_allow_html=True)
        
        # Criação das abas solicitadas
        tabs = st.tabs(["🏆 1x2", "⚽ Ambas (Y/N)", "📈 Over 1.5/2.5", "👥 DC + Over", "🔥 DC + Ambas", "🚩 Cantos +8.5"])
        
        # Divisão dos jogos para não repetir o mesmo jogo em abas diferentes
        chunks = [jogos_finais[i:i + 2] for i in range(0, len(jogos_finais), 2)]

        mercados = [
            ("Vitória (1x2)", 0),
            ("Ambas Marcam (Sim/Não)", 1),
            ("Golos (Over 1.5 ou 2.5)", 2),
            ("Dupla Chance + Over 1.5/2.5", 3),
            ("Dupla Chance + Ambas Marcam", 4),
            ("Cantos (Over 8.5)", 5)
        ]

        for nome_mercado, index in mercados:
            with tabs[index]:
                st.subheader(f"Top Opções: {nome_mercado}")
                # Seleciona 1 a 2 equipas por categoria sem repetir jogos anteriores
                jogos_da_aba = chunks[index] if index < len(chunks) else []
                
                if jogos_da_aba:
                    for j in jogos_da_aba:
                        h, a = j['event_home_team'], j['event_away_team']
                        with st.expander(f"🕒 {j['event_time']} | {h} vs {a}"):
                            analise = analise_tecnica(h, a, nome_mercado)
                            st.markdown(f'<div class="card-elite">{analise}</div>', unsafe_allow_html=True)
                else:
                    st.write("Sem jogos suficientes para este mercado nesta data.")
    else:
        st.error("Nenhum jogo de elite encontrado.")
