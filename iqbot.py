import os
import sys
import time
import requests
import numpy as np
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
import ta  # Biblioteca para indicadores técnicos
from datetime import datetime

# ====================== CONFIGURAÇÕES ====================== #

IQ_OPTION_EMAIL = "seuemail"
IQ_OPTION_PASSWORD = "suasenha"
TELEGRAM_BOT_TOKEN = "8116645944:AAFOMpIK6_lN7twK9d3zkBiVA5eAGbUqeME"
TELEGRAM_CHAT_ID = "7559999177"

# Variável global para conexão com a IQ Option
Iq = None  
ativos_ignorados = set()  # Lista de ativos problemáticos

# ====================== FUNÇÃO PARA REINICIAR O BOT ====================== #

def reiniciar_bot():
    print("\n🔄 Reiniciando o bot completamente...\n")
    os.execv(sys.executable, [sys.executable] + sys.argv)  # Reinicia o script do zero

# ====================== FUNÇÃO PARA CONECTAR À IQ OPTION ====================== #

def conectar_iq():
    global Iq
    while True:
        try:
            print("🔗 Tentando conectar à IQ Option...")
            Iq = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
            Iq.connect()

            if Iq.check_connect():
                print("✅ Conectado à IQ Option com sucesso!\n")
                return
            else:
                print("❌ Falha na conexão. Tentando novamente em 15 segundos...")
                time.sleep(15)
        except Exception as e:
            print(f"⚠️ Erro ao conectar: {e}. Tentando novamente em 15 segundos...")
            time.sleep(15)

# ====================== OBTENDO ATIVOS DISPONÍVEIS ====================== #

def obter_ativos():
    global Iq
    while True:
        try:
            if Iq is None or not Iq.check_connect():
                conectar_iq()

            ativos = Iq.get_all_ACTIVES_OPCODE()
            if not ativos:
                raise Exception("Nenhum ativo disponível no momento.")

            # Filtrando apenas 10 ativos para evitar sobrecarga
            ativos_filtrados = [ativo for ativo in ativos if ativos[ativo] not in [0, 1] and ativo not in ativos_ignorados][:10]
            
            print(f"📊 Analisando {len(ativos_filtrados)} ativos para evitar sobrecarga.")

            if len(ativos_filtrados) == 0:
                print("⚠️ Nenhum ativo disponível para análise. Tentando novamente em 10 segundos...")
                time.sleep(10)
                ativos_ignorados.clear()  # Limpa a lista de ignorados para tentar novamente
                return obter_ativos()

            return ativos_filtrados
        except Exception as e:
            print(f"⚠️ Erro ao obter ativos: {e}. Tentando novamente em 15 segundos...")
            time.sleep(15)
            conectar_iq()

# ====================== FUNÇÃO PARA ENVIAR SINAIS NO TELEGRAM ====================== #

def send_signal(ativo, tipo, explicacao, tempo_recomendado, assertividade):
    horario_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    mensagem = f"""📉 📈 {tipo} {ativo}

Explicação: {explicacao}

📅 Data e Hora: {horario_atual}

⏳ Tempo Recomendado: {tempo_recomendado} min

✅ Assertividade: {assertividade}%
"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print(f"\n📩 Mensagem enviada:\n{mensagem}")
        else:
            print(f"❌ Erro ao enviar mensagem para o Telegram: {response.text}")
    except Exception as e:
        print(f"⚠️ Erro ao enviar mensagem para o Telegram: {e}")

# ====================== FUNÇÃO PARA ANALISAR ATIVOS ====================== #

def analisar_ativo(ativo):
    global Iq

    try:
        print(f"🔍 Analisando {ativo}...")

        # Se a conexão cair, reconecta antes de continuar
        if Iq is None or not Iq.check_connect():
            print(f"⚠️ Conexão perdida. Reconectando antes de analisar {ativo}...")
            conectar_iq()

        # Obtendo os candles do ativo
        velas = Iq.get_candles(ativo, 60, 100, time.time())

        # Se os dados forem inválidos, pula o ativo
        if not velas or len(velas) == 0:
            print(f"⚠️ Erro ao obter dados do ativo {ativo}. Pulando para o próximo...\n")
            ativos_ignorados.add(ativo)  # Adiciona à lista de ativos problemáticos
            return

        df = pd.DataFrame(velas)
        df['timestamp'] = pd.to_datetime(df['from'], unit='s')
        df.set_index('timestamp', inplace=True)

        # Calculando Indicadores Técnicos
        df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        df['MACD'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12).macd()
        df['Sinal_MACD'] = ta.trend.MACD(df['close'], window_slow=26, window_fast=12).macd_signal()
        df['Média_Móvel'] = ta.trend.SMAIndicator(df['close'], window=20).sma_indicator()
        df['Bollinger_High'] = ta.volatility.BollingerBands(df['close'], window=20).bollinger_hband()
        df['Bollinger_Low'] = ta.volatility.BollingerBands(df['close'], window=20).bollinger_lband()

        # Pegando os últimos valores dos indicadores
        rsi_atual = df['RSI'].iloc[-1]
        macd_atual = df['MACD'].iloc[-1]
        sinal_macd_atual = df['Sinal_MACD'].iloc[-1]
        preco_atual = df['close'].iloc[-1]

        # Lógica para sinais de compra e venda
        sinais = []

        if rsi_atual < 30 and macd_atual > sinal_macd_atual:
            sinais.append(("📈 POSSÍVEL COMPRA", "RSI abaixo de 30 e MACD cruzou para cima", 5, 82))
        if rsi_atual > 70 and macd_atual < sinal_macd_atual:
            sinais.append(("📉 POSSÍVEL VENDA", "RSI acima de 70 e MACD cruzou para baixo", 5, 78))
        if preco_atual <= df['Bollinger_Low'].iloc[-1]:
            sinais.append(("📈 POSSÍVEL REVERSÃO", "Preço tocou a banda inferior de Bollinger", 3, 80))
        if preco_atual >= df['Bollinger_High'].iloc[-1]:
            sinais.append(("📉 POSSÍVEL VENDA", "Preço tocou a banda superior de Bollinger", 3, 79))

        # Enviar os sinais encontrados
        for tipo, explicacao, tempo_recomendado, assertividade in sinais:
            send_signal(ativo, tipo, explicacao, tempo_recomendado, assertividade)

    except Exception as e:
        print(f"⚠️ Erro ao analisar {ativo}: {e}. Pulando ativo...\n")
        ativos_ignorados.add(ativo)

# ====================== LOOP CONTÍNUO ====================== #

while True:
    try:
        ativos = obter_ativos()
        for ativo in ativos:
            analisar_ativo(ativo)
            time.sleep(3)  # Reduz a frequência das solicitações
        print("\n🔁 Finalizou todos os ativos! Reiniciando a análise...\n")
    except Exception as e:
        print(f"⚠️ Erro geral: {e}\n🔄 Reiniciando bot em 15 segundos...")
        time.sleep(15)
        reiniciar_bot()
