import streamlit as st
import cloudscraper
from bs4 import BeautifulSoup

# 1. Configuração
st.set_page_config(page_title="Scanner Betway MZ", layout="wide", page_icon="⚽")

# 2. Função Scraper para o Link
def extrair_dados_betway(url):
    try:
        scraper = cloudscraper.create_scraper()
        res = scraper.get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Tentativa de pegar o nome dos times no título da página
        titulo = soup.title.string if soup.title else ""
        nome_jogo = titulo.replace("Betway", "").strip()
        
        return nome_jogo
    except:
        return None

# 3. Cabeçalho
st.title("⚽ Smart Predictor - Betway.co.mz")

# 4. Campo de Link
st.info("Copie o link do jogo na Betway e cole abaixo para analisar")
link_betway = st.text_input("Link do Jogo (ex: https://www.betway.co.mz/sport/soccer/...)")

if link_betway:
    with st.spinner('Analisando link da Betway...'):
        info_jogo = extrair_dados_betway(link_betway)
        if info_jogo:
            st.write(f"🎮 Jogo detectado: **{info_jogo}**")

st.divider()

# 5. Entradas de Dados (Ajustado)
col_in1, col_in2 = st.columns(2)

with col_in1:
    st.subheader("📊 Dados do Mercado")
    time_h = st.text_input("Time da Casa", "Costa do Sol")
    odd_casa = st.number_input("Odd na Betway (Vencer Casa)", min_value=1.01, value=2.10)

with col_in2:
    st.subheader("📈 Nossa Estatística")
    media_gols_h = st.slider("Força de Ataque (Casa)", 0.0, 5.0, 1.8)
    media_gols_a = st.slider("Fraqueza de Defesa (Visitante)", 0.0, 5.0, 1.2)

# 6. Lógica de Cálculo
def calcular_prognostico(g_h, g_a):
    prob_h = (g_h / (g_h + g_a)) * 0.82 if (g_h + g_a) > 0 else 0.5
    return prob_h

prob_vitoria = calcular_prognostico(media_gols_h, media_gols_a)
odd_justa = 1 / prob_vitoria

# 7. Resultados
st.divider()
res1, res2 = st.columns(2)

with res1:
    st.metric("Nossa Odd Justa", f"{odd_justa:.2f}")
    if odd_casa > odd_justa:
        st.success("✅ APOSTA COM VALOR")
        st.balloons()
    else:
        st.error("❌ SEM VALOR AGORA")

with res2:
    st.metric("Probabilidade Real", f"{prob_vitoria*100:.1f}%")
    vantagem = ((odd_casa / odd_justa) - 1) * 100
    st.write(f"**Sua vantagem sobre a Betway:** {vantagem:.1f}%")

st.caption("Dica: Se colar o link e os nomes não mudarem, preencha manualmente os nomes e as odds.")
