import pandas as pd
import numpy as np
import datetime
import logging
import talib
import backtrader as bt

# Configuration du logger
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MyStrategy(bt.Strategy):
    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.rsi = bt.indicators.RSI(self.data.close)
        self.stochastic = bt.indicators.Stochastic(self.data)
        self.macd = bt.indicators.MACD(self.data)
        self.ema_short = bt.indicators.EMA(self.data, period=12)
        self.ema_long = bt.indicators.EMA(self.data, period=26)
        self.atr = bt.indicators.ATR(self.data)
        self.bollinger = bt.indicators.BollingerBands(self.data)
        self.adx = bt.indicators.ADX(self.data)
        self.cci = bt.indicators.CCI(self.data)

    def next(self):
        if self.order:
            return

        buy_score = 0
        sell_score = 0

        # Calculer les scores d'achat et de vente
        if self.rsi < 30:
            buy_score += 1
        if self.stochastic.percK < 20 and self.stochastic.percD < 20:
            buy_score += 1
        if self.dataclose[0] <= self.bollinger.lines.bot:
            buy_score += 1
        if self.cci < -100:
            buy_score += 1
        if self.macd.macd > self.macd.signal:
            buy_score += 1
        if self.ema_short > self.ema_long:
            buy_score += 1
        if self.adx > 25:
            buy_score += 1

        if self.rsi > 70:
            sell_score += 1
        if self.stochastic.percK > 80 and self.stochastic.percD > 80:
            sell_score += 1
        if self.dataclose[0] >= self.bollinger.lines.top:
            sell_score += 1
        if self.cci > 100:
            sell_score += 1
        if self.macd.macd < self.macd.signal:
            sell_score += 1
        if self.ema_short < self.ema_long:
            sell_score += 1
        if self.adx > 25:
            sell_score += 1

        # Prendre des décisions de trading
        if buy_score >= 4:
            self.order = self.buy()
        elif sell_score >= 4:
            self.order = self.sell()

# Fonction de backtest
def run_backtest():
    # Charger les données historiques dans un DataFrame en ignorant les lignes incorrectes
    data = pd.read_csv('historical_data.csv', on_bad_lines='warn')
    
    # Afficher les premières lignes pour vérifier les données
    print(data.head())

    # Si la colonne 'Date' est présente, la définir comme index
    if 'Date' in data.columns:
        data.set_index('Date', inplace=True)
        data.index = pd.to_datetime(data.index)

    # Créer un Feed de données pour Backtrader
    data_feed = bt.feeds.PandasData(dataname=data)

    # Initialiser le cerebro (moteur de backtesting)
    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.addstrategy(MyStrategy)

    # Définir le capital initial
    cerebro.broker.set_cash(10000)

    # Définir la taille de la position
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Exécuter le backtest
    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    # Afficher les graphiques
    cerebro.plot()

if __name__ == "__main__":
    run_backtest()
