import streamlit as st
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd

# 1. Configuração Inicial
st.set_page_config(page_title="Scanner Betway MZ", layout="wide", page_icon="⚽")

st.markdown("""
    <style>
    .main { background-color: #1a1a1a; color: white; }
    .stMetric { background-color: #2d2d2d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. Cabeçalho
st.title("⚽ Smart Predictor - Betway.co.mz")
st.subheader("Analise odds em tempo real e encontre apostas de valor")

# 3. Sidebar e Inputs (Garantindo que as variáveis existam sempre)
st.sidebar.header("Configurações de Análise")

# Definindo valores padrão para evitar o NameError
time_h = "Time Casa"
time_a = "Time Fora"
odd_casa = 2.0
media_gols_h = 1.5
media_gols_a = 1.0

modo = st.sidebar.radio("Modo de Análise", ["Manual", "Automático (Em breve)"])

if modo == "Manual":
    time_h = st.text_input("Nome do Time da Casa", "Costa do Sol")
    time_a = st.text_input("Nome do Time de Fora", "Black Bulls")
    
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        odd_casa = st.number_input("Odd na Betway (Casa)", min_value=1.01, value=2.10)
        media_gols_h = st.slider("Média de gols marcados (Casa)", 0.0, 5.0, 1.8)
    with col_in2:
        st.write("") # Espaçamento
        st.write("")
        media_gols_a = st.slider("Média de gols sofridos (Pelo visitante)", 0.0, 5.0, 1.2)

# 4. Função de Cálculo
def calcular_prognostico(gols_h, gols_a):
    total = gols_h + gols_a
    if total == 0: total = 0.01 # Evita divisão por zero
    
    prob_h = (gols_h / total) * 0.80 # Margem de erro de 20%
    if prob_h > 0.95: prob_h = 0.95
    if prob_h < 0.05: prob_h = 0.05
    
    prob_e = 0.25 # Média fixa de empate para simplificar
    prob_a = 1 - prob_h - prob_e
    
    return prob_h, prob_e, prob_a

# 5. Execução do Cálculo (Agora sem erro!)
p_h, p_e, p_a = calcular_prognostico(media_gols_h, media_gols_a)
odd_justa_h = 1 / p_h

# 6. Resultados Visuais
st.divider()
st.header(f"Análise: {time_h} vs {time_a}")

c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Nossa Odd Justa", f"{odd_justa_h:.2f}")
    if odd_casa > odd_justa_h:
        st.success("✅ TEM VALOR")
    else:
        st.error("❌ SEM VALOR")

with c2:
    st.metric("Probabilidade Vitória", f"{p_h*100:.1f}%")

with c3:
    vantagem = ((odd_casa / odd_justa_h) - 1) * 100
    st.metric("Vantagem (Value)", f"{vantagem:.1f}%")

# Dica Final
if odd_casa > odd_justa_h:
    st.balloons()
    st.info(f"Dica: A odd da Betway ({odd_casa}) está mais alta que o risco ({odd_justa_h:.2f}). Boa oportunidade!")
