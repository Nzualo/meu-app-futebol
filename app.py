import streamlit as st
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Scanner Geral Betway", layout="wide")

st.title("📋 Scanner de Oportunidades - Betway MZ")
st.write("Análise rápida de múltiplos jogos para encontrar as melhores entradas do dia.")

# --- ENTRADA DE DADOS EM MASSA ---
st.subheader("1. Inserir Jogos do Dia")
st.info("Dica: Você pode copiar dados de uma tabela ou preencher abaixo.")

# Criando uma tabela editável para análise rápida
data = {
    "Jogo": ["Costa do Sol vs Black Bulls", "Fer. Maputo vs Textáfrica", "Real Madrid vs Mallorca", "Man City vs Arsenal"],
    "Odd Betway (1)": [2.10, 1.50, 1.30, 1.85],
    "Força Casa (0-10)": [7, 8, 9, 8],
    "Força Fora (0-10)": [6, 3, 4, 8]
}
df_inicial = pd.DataFrame(data)

# Tabela editável onde você pode mudar os nomes e odds rapidamente
df_usuario = st.data_editor(df_inicial, num_rows="dynamic", use_container_width=True)

# --- BOTÃO DE PROCESSAMENTO GERAL ---
if st.button("🔍 ANALISAR TODOS OS JOGOS"):
    
    # Lógica de Cálculo em Massa
    def calcular_valor(row):
        # Cálculo de probabilidade baseada na força relativa (0-10)
        total_forca = row["Força Casa (0-10)"] + row["Força Fora (0-10)"]
        prob_casa = row["Força Casa (0-10)"] / total_forca
        odd_justa = 1 / (prob_casa * 0.9) # 0.9 é a margem de segurança
        
        valor = row["Odd Betway (1)"] - odd_justa
        return round(odd_justa, 2), round(valor, 2)

    # Aplicando o cálculo na tabela
    df_usuario[['Odd Justa', 'Margem Valor']] = df_usuario.apply(
        lambda row: pd.Series(calcular_valor(row)), axis=1
    )

    # --- RESULTADOS ---
    st.divider()
    st.subheader("📊 Ranking de Melhores Apostas")
    
    # Colorindo a tabela para facilitar a visão
    def colorir_valor(val):
        color = 'green' if val > 0 else 'red'
        return f'color: {color}'

    df_final = df_usuario.sort_values(by="Margem Valor", ascending=False)
    st.dataframe(df_final.style.applymap(colorir_valor, subset=['Margem Valor']), use_container_width=True)

    # Resumo Rápido
    melhor_jogo = df_final.iloc[0]
    st.success(f"💎 **Melhor Oportunidade:** {melhor_jogo['Jogo']} com margem de {melhor_jogo['Margem Valor']}")

else:
    st.info("Ajuste as Forças e as Odds na tabela acima e clique em Analisar.")

st.markdown("""
---
**Como usar rápido:**
1. Altere o nome dos jogos e as **Odds** que estão na Betway.
2. Atribua uma nota de 0 a 10 para cada time (ex: Real Madrid = 9, Mallorca = 4).
3. O sistema dirá instantaneamente onde o dinheiro está mais "seguro".
""")
