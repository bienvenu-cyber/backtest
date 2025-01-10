import requests
import pandas as pd
import numpy as np
import datetime
import backtrader as bt
import matplotlib
matplotlib.use('TkAgg')  # Try different backend
pd.set_option('display.max_rows', None)

def fetch_historical_data(crypto_symbol, currency="USD", limit=365):  # Increased to 1 year of data
    base_url = "https://min-api.cryptocompare.com/data/v2/"
    endpoint = "histoday"
    url = f"{base_url}{endpoint}"
    params = {
        "fsym": crypto_symbol.upper(),
        "tsym": currency.upper(),
        "limit": limit,
        "api_key": "7f915fdfdf395420911c4e294f807d61a0a1b3ff10f0db14fd08b5e10c2da790"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("Response") == "Success" and "Data" in data:
            prices = []
            for item in data["Data"]["Data"]:
                if item["volumeto"] > 0:  # Filter out zero volume periods
                    prices.append({
                        "Date": datetime.datetime.fromtimestamp(item["time"]),
                        "Open": float(item["open"]),
                        "High": float(item["high"]),
                        "Low": float(item["low"]),
                        "Close": float(item["close"]),
                        "Volume": float(item["volumeto"])
                    })
            df = pd.DataFrame(prices)
            df.set_index('Date', inplace=True)
            print(f"Fetched {len(df)} days of data")
            return df
        else:
            print(f"API Error: {data.get('Message')}")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        return pd.DataFrame()

class MyStrategy(bt.Strategy):
    params = (
        ('rsi_period', 14),
        ('rsi_oversold', 35),    # Made less strict
        ('rsi_overbought', 65),  # Made less strict
        ('stoch_period', 14),
        ('stoch_oversold', 25),  # Made less strict
        ('stoch_overbought', 75),# Made less strict
        ('macd1', 12),
        ('macd2', 26),
        ('macdsig', 9),
        ('required_score', 3),   # Reduced from 4 to 3
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}')

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.trades = 0
        self.in_position = False
        
        # Initialize indicators
        self.rsi = bt.indicators.RSI(
            self.data.close, 
            period=self.params.rsi_period
        )
        self.stochastic = bt.indicators.Stochastic(
            self.data,
            period=self.params.stoch_period
        )
        self.macd = bt.indicators.MACD(
            self.data, 
            period_me1=self.params.macd1,
            period_me2=self.params.macd2,
            period_signal=self.params.macdsig
        )
        self.ema_short = bt.indicators.EMA(self.data, period=12)
        self.ema_long = bt.indicators.EMA(self.data, period=26)
        self.atr = bt.indicators.ATR(self.data)
        self.bollinger = bt.indicators.BollingerBands(self.data, period=20)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.in_position = True
            else:
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.in_position = False
            self.trades += 1

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:  # Not in the market
            buy_score = 0
            
            # RSI oversold
            if self.rsi[0] < self.params.rsi_oversold:
                buy_score += 1
                self.log(f'RSI oversold: {self.rsi[0]:.2f}')
            
            # Stochastic oversold
            if (self.stochastic.percK[0] < self.params.stoch_oversold and 
                self.stochastic.percD[0] < self.params.stoch_oversold):
                buy_score += 1
                self.log(f'Stochastic oversold: K={self.stochastic.percK[0]:.2f}, D={self.stochastic.percD[0]:.2f}')
            
            # Price below lower Bollinger
            if self.dataclose[0] <= self.bollinger.lines.bot[0]:
                buy_score += 1
                self.log('Price below lower Bollinger')
            
            # MACD crossing above signal
            if (self.macd.macd[-1] <= self.macd.signal[-1] and 
                self.macd.macd[0] > self.macd.signal[0]):
                buy_score += 1
                self.log('MACD crossing above signal')
            
            # EMA cross
            if (self.ema_short[-1] <= self.ema_long[-1] and 
                self.ema_short[0] > self.ema_long[0]):
                buy_score += 1
                self.log('EMA short crossing above long')

            if buy_score >= self.params.required_score:
                self.log(f'BUY CREATE, {self.dataclose[0]:.2f}')
                self.order = self.buy()

        else:  # In the market
            sell_score = 0
            
            # RSI overbought
            if self.rsi[0] > self.params.rsi_overbought:
                sell_score += 1
            
            # Stochastic overbought
            if (self.stochastic.percK[0] > self.params.stoch_overbought and 
                self.stochastic.percD[0] > self.params.stoch_overbought):
                sell_score += 1
            
            # Price above upper Bollinger
            if self.dataclose[0] >= self.bollinger.lines.top[0]:
                sell_score += 1
            
            # MACD crossing below signal
            if (self.macd.macd[-1] >= self.macd.signal[-1] and 
                self.macd.macd[0] < self.macd.signal[0]):
                sell_score += 1
            
            # EMA cross
            if (self.ema_short[-1] >= self.ema_long[-1] and 
                self.ema_short[0] < self.ema_long[0]):
                sell_score += 1

            if sell_score >= self.params.required_score:
                self.log(f'SELL CREATE, {self.dataclose[0]:.2f}')
                self.order = self.sell()

def run_backtest():
    crypto_symbol = "BTC"
    print(f"Fetching data for {crypto_symbol}...")
    data = fetch_historical_data(crypto_symbol, limit=365)  # Increased to 1 year
    
    if data.empty:
        print("No data available for backtest.")
        return

    cerebro = bt.Cerebro()
    
    # Add the data feed
    data_feed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(data_feed)

    # Add strategy
    cerebro.addstrategy(MyStrategy)

    # Set initial capital
    initial_cash = 200
    cerebro.broker.set_cash(initial_cash)

    # Add position sizer
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)  # Use 95% of portfolio for each trade

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    print(f'Starting Portfolio Value: ${initial_cash:.2f}')

    try:
        results = cerebro.run()
        strat = results[0]
        
        final_value = cerebro.broker.getvalue()
        print(f'\nFinal Portfolio Value: ${final_value:.2f}')
        print(f'Total Return: {((final_value - initial_cash) / initial_cash * 100):.2f}%')
        print(f'Total Number of Trades: {strat.trades}')
        
        # Try to plot without volume to avoid the array error
        try:
            cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
        except Exception as e:
            print(f"\nWarning: Could not generate plot: {str(e)}")
            print("Consider using a different plotting backend or matplotlib version.")
            
    except Exception as e:
        print(f"Error during backtest execution: {str(e)}")

if __name__ == "__main__":
    run_backtest()
