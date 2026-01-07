import streamlit as st
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd

# 1. Configuração Inicial
st.set_page_config(page_title="Scanner Betway MZ", layout="wide", page_icon="⚽")

# Estilo CSS para parecer um app profissional
st.markdown("""
    <style>
    .main { background-color: #1a1a1a; color: white; }
    .stMetric { background-color: #2d2d2d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. Função para capturar dados (Scraper)
def get_betway_data():
    scraper = cloudscraper.create_scraper()
    url = "https://www.betway.co.mz/sport/soccer" # URL principal
    
    try:
        response = scraper.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Esta parte busca os blocos de jogos (as classes podem variar na Betway)
        # Vamos criar um simulador de dados caso o scraper seja bloqueado temporariamente
        eventos = []
        
        # Lógica de extração de exemplo (precisa ser refinada conforme o HTML da Betway)
        # Se falhar, ele retorna uma lista vazia e usamos a entrada manual
        return eventos
    except Exception as e:
        return None

# 3. Cabeçalho do App
st.title("⚽ Smart Predictor - Betway.co.mz")
st.subheader("Analise odds em tempo real e encontre apostas de valor")

# 4. Interface Lateral (Input)
st.sidebar.header("Configurações de Análise")
modo = st.sidebar.radio("Modo de Análise", ["Manual", "Automático (Beta)"])

if modo == "Manual":
    st.sidebar.info("Insira os dados da Betway abaixo")
    time_h = st.text_input("Time da Casa", "Costa do Sol")
    time_a = st.text_input("Time de Fora", "Black Bulls")
    
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        odd_casa = st.number_input("Odd Betway (Vencer Casa)", min_value=1.0, value=2.10)
        media_gols_h = st.slider("Média de gols (Casa)", 0.0, 5.0, 1.8)
    with col_input2:
        odd_fora = st.number_input("Odd Betway (Vencer Fora)", min_value=1.0, value=3.20)
        media_gols_a = st.slider("Média de gols (Fora)", 0.0, 5.0, 1.2)

# 5. O Cérebro (Cálculo de Probabilidade - Poisson/Média)
def calcular_prognostico(gols_h, gols_a):
    # Modelo simplificado de força de ataque
    total = gols_h + gols_a
    prob_h = (gols_h / total) * 0.85 # margem de segurança
    prob_a = (gols_a / total) * 0.85
    prob_e = 1 - prob_h - prob_a
    
    return prob_h, prob_e, prob_a

p_h, p_e, p_a = calcular_prognostico(media_gols_h, media_gols_a)
odd_justa_h = 1 / p_h

# 6. Exibição dos Resultados
st.divider()
st.header(f"Prognóstico: {time_h} vs {time_a}")

c1, c2, c3 = st.columns(3)

with c1:
    valor = odd_casa > odd_justa_h
    st.metric("Odd Justa (Calculada)", f"{odd_justa_h:.2f}")
    if valor:
        st.success("✅ HÁ VALOR NA CASA")
    else:
        st.error("❌ SEM VALOR")

with c2:
    st.metric("Probabilidade de Vitória", f"{p_h*100:.1f}%")

with c3:
    st.metric("Margem de Lucro Est.", f"{((odd_casa/odd_justa_h)-1)*100:.1f}%")

# 7. Sugestão Final
st.divider()
if valor and p_h > 0.5:
    st.warning(f"🚩 Dica de Aposta: Vitória do {time_h} tem valor estatístico na Betway.")
elif p_h + p_a > 0.7:
    st.info("🚩 Dica de Aposta: Mercado de 'Ambas Marcam' parece provável.")
else:
    st.write("Aguarde por melhores oportunidades neste jogo.")

st.caption("Aviso: Apostas envolvem risco. Use este software apenas como ferramenta de auxílio.")
