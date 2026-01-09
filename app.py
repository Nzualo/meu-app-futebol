import streamlit as st
import requests
from openai import OpenAI
from datetime import datetime
import pytz

# Configurações de API
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
FOOTBALL_API_KEY = "2f3bc9f0346c3803720553cecbdbb6bd"

def buscar_h2h_oficial(id_home, id_away):
    """Busca dados REAIS para a IA não pedir informações"""
    url = f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={id_home}-{id_away}&last=5"
    headers = {'x-rapidapi-key': FOOTBALL_API_KEY}
    try:
        res = requests.get(url, headers=headers).json()
        return res.get("response", [])
    except:
        return []

def analise_com_dados_reais(home, away, h2h_lista, mercado):
    """Envia os dados da API para dentro da IA"""
    # Transformando os dados da API em texto para a IA ler
    texto_h2h = "\n".join([
        f"- {m['fixture']['date'][:10]}: {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}" 
        for m in h2h_lista
    ])
    
    prompt = f"""
    ANALISTA: Analise {home} vs {away} para o mercado {mercado}.
    DADOS REAIS FORNECIDOS (2023-2026):
    {texto_h2h if texto_h2h else "Sem confrontos recentes registrados."}
    
    REGRAS: Use APENAS os dados acima. Dê um veredito matemático seco com confiança > 75%.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Erro na comunicação com a IA."

# Interface
st.title("🛡️ Elite Intelligence Scanner 2.5")
# ... restante da lógica de carregar jogos ...
