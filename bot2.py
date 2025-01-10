import requests
import pandas as pd
import datetime
import backtrader as bt

def fetch_historical_data(crypto_symbol, currency="USD", limit=10):
    base_url = "https://min-api.cryptocompare.com/data/v2/"
    endpoint = "histoday"
    url = f"{base_url}{endpoint}"
    params = {
        "fsym": crypto_symbol.upper(),
        "tsym": currency.upper(),
        "limit": limit,
        "api_key": "7f915fdfdf395420911c4e294f807d61a0a1b3ff10f0db14fd08b5e10c2da790"
    }
    response = requests.get(url, params=params)
    data = response.json()

    if data.get("Response") == "Success" and "Data" in data:
        prices = []
        for item in data["Data"]["Data"]:
            prices.append({
                "Date": datetime.datetime.fromtimestamp(item["time"]),
                "Open": item["open"],
                "High": item["high"],
                "Low": item["low"],
                "Close": item["close"],
                "Volume": item["volumeto"]
            })
        df = pd.DataFrame(prices)
        df.set_index('Date', inplace=True)
        return df
    else:
        print("Erreur de l'API:", data.get("Message"))
        return pd.DataFrame()

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

        if buy_score >= 4:
            self.order = self.buy()
        elif sell_score >= 4:
            self.order = self.sell()

def run_backtest():
    crypto_symbol = "BTC"
    data = fetch_historical_data(crypto_symbol, limit=100)

    if data.empty:
        print("Aucune donnée disponible pour le backtest.")
        return

    # Vérifier et nettoyer les données de volume
    data['Volume'] = pd.to_numeric(data['Volume'], errors='coerce')
    data.dropna(subset=['Volume'], inplace=True)

    data_feed = bt.feeds.PandasData(dataname=data)

    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.addstrategy(MyStrategy)

    cerebro.broker.set_cash(10000)
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())

    cerebro.plot()

if __name__ == "__main__":
    run_backtest()
