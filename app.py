import streamlit as st

# Configuração da página
st.set_page_config(page_title="Prognósticos Betway MZ", layout="wide")

st.title("⚽ Analisador de Valor - Betway.co.mz")
st.write("Insira os dados do jogo para calcular se a odd tem valor.")

# --- BARRA LATERAL / ENTRADA DE DADOS ---
st.sidebar.header("Dados da Partida")
time_casa = st.sidebar.text_input("Time da Casa", "Ex: Black Bulls")
time_fora = st.sidebar.text_input("Time de Fora", "Ex: Ferroviário de Maputo")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Estatísticas (Últimos 5 jogos)")
    gols_marcados_casa = st.number_input(f"Gols marcados pelo {time_casa}", min_value=0.0, value=1.5)
    gols_sofridos_fora = st.number_input(f"Gols sofridos pelo {time_fora}", min_value=0.0, value=1.2)

with col2:
    st.subheader("Mercado Betway")
    odd_betway = st.number_input(f"Odd na Betway para vitória do {time_casa}", min_value=1.01, value=2.0)

# --- LÓGICA DE PROGNÓSTICO (SIMPLIFICADA) ---
# Cálculo de probabilidade baseada na média de gols
probabilidade_estimada = (gols_marcados_casa + gols_sofridos_fora) / 4 
if probabilidade_estimada > 0.9: probabilidade_estimada = 0.85 # Teto de segurança

odd_justa = 1 / probabilidade_estimada

# --- RESULTADO ---
st.divider()
st.header(f"Análise: {time_casa} vs {time_fora}")

res_col1, res_col2, res_col3 = st.columns(3)

res_col1.metric("Nossa Probabilidade", f"{probabilidade_estimada*100:.1f}%")
res_col2.metric("Odd Justa Calculada", f"{odd_justa:.2f}")
res_col3.metric("Odd Atual Betway", f"{odd_betway:.2f}")

if odd_betway > odd_justa:
    st.success(f"✅ APOSTA COM VALOR! A Betway está pagando mais do que o risco calculado.")
    lucro_esperado = (odd_betway - odd_justa) / odd_justa * 100
    st.write(f"**Vantagem sobre a casa:** {lucro_esperado:.1f}%")
else:
    st.error("❌ SEM VALOR. A odd da Betway está muito baixa para o risco desta partida.")

st.info("Nota: Este é um modelo estatístico básico. Sempre gerencie sua banca com cuidado.")
