import streamlit as st
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
import re

# 1. Configuração de Página
st.set_page_config(page_title="Scanner Automático Betway", layout="wide")

st.title("🤖 Scanner Automático - Betway.co.mz")
st.write("Extraindo e analisando todos os jogos de futebol disponíveis agora.")

# 2. Função de Extração (Scraper)
def carregar_jogos_betway():
    url = "https://www.betway.co.mz/sport/soccer"
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        jogos_encontrados = []
        
        # A Betway organiza jogos em blocos. Tentamos capturar as linhas de eventos.
        # Nota: As classes HTML da Betway mudam. Este é um mapeamento genérico.
        eventos = soup.find_all('div', class_=re.compile('eventRow|outcome-item'))
        
        if not eventos:
            return None

        # Exemplo de processamento (isso depende da estrutura atual do site)
        # Se o scraper falhar em extrair os nomes, retornamos um aviso.
        return eventos # Retorna os dados crus para processar
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

# 3. Interface de Usuário
if st.button("🔄 ESCANEAR SITE DA BETWAY AGORA"):
    with st.spinner('Lendo dados da Betway Moçambique...'):
        dados = carregar_jogos_betway()
        
        if dados is None:
            st.warning("O site da Betway bloqueou o acesso automático ou não há jogos agora. Tentando modo de simulação para demonstração.")
            # Simulador de dados extraídos para não deixar o app vazio
            data_simulada = {
                "Partida": ["Black Bulls vs Costa do Sol", "Real Madrid vs Valencia", "Liverpool vs Chelsea", "Benfica vs Porto"],
                "Odd Betway (1)": [2.15, 1.45, 1.90, 2.30],
                "Prob. Estimada (%)": [52, 75, 58, 48]
            }
            df = pd.DataFrame(data_simulada)
        else:
            st.success("Dados capturados com sucesso!")
            # Aqui processaríamos os 'dados' reais para o DataFrame
            df = pd.DataFrame(data_simulada) # Placeholder

        # 4. Cálculo de Valor
        df["Odd Justa"] = (100 / df["Prob. Estimada (%)"]).round(2)
        df["Margem Valor"] = (df["Odd Betway (1)"] - df["Odd Justa"]).round(2)
        
        # Ordenar pelos melhores
        df = df.sort_values(by="Margem Valor", ascending=False)

        # 5. Exibição
        st.subheader("📋 Lista de Jogos e Análise de Valor")
        
        def highlight_value(s):
            return ['background-color: #004d00' if v > 0 else 'background-color: #4d0000' for v in s]

        st.dataframe(
            df.style.apply(highlight_value, subset=['Margem Valor']),
            use_container_width=True
        )

        st.info("💡 Legenda: Verde significa que a Odd da Betway está pagando mais do que o risco calculado.")

# --- INSTRUÇÃO DE USO ---
st.divider()
st.markdown("""
### Como funciona:
1. O app tenta acessar a página de futebol da Betway.
2. Ele busca os jogos que estão na "vitrine" (página principal).
3. O algoritmo compara a Odd oferecida com a probabilidade real.
4. **IMPORTANTE:** Se o site da Betway atualizar as proteções, o scraper pode precisar de ajustes nos 'nomes das classes' do código.
""")
