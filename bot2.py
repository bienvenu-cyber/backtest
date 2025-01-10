import requests
import pandas as pd
import numpy as np
import datetime
import backtrader as bt
import matplotlib
matplotlib.use('TkAgg')

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
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("Response") == "Success" and "Data" in data:
            prices = []
            for item in data["Data"]["Data"]:
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
        ('stoch_period', 14),
        ('macd1', 12),
        ('macd2', 26),
        ('macdsig', 9),
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}')

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.trades = 0
        
        # Initialize indicators
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.stochastic = bt.indicators.Stochastic(self.data, period=self.params.stoch_period)
        self.macd = bt.indicators.MACD(
            self.data, 
            period_me1=self.params.macd1,
            period_me2=self.params.macd2,
            period_signal=self.params.macdsig
        )
        self.ema_short = bt.indicators.EMA(self.data, period=12)
        self.ema_long = bt.indicators.EMA(self.data, period=26)
        self.atr = bt.indicators.ATR(self.data)
        self.bollinger = bt.indicators.BollingerBands(self.data)
        self.adx = bt.indicators.ADX(self.data)
        self.cci = bt.indicators.CCI(self.data)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
            else:
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
            self.trades += 1

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def next(self):
        if self.order:
            return

        buy_score = 0
        sell_score = 0

        # Buy conditions
        if self.rsi[0] < 30:
            buy_score += 1
        if self.stochastic.percK[0] < 20 and self.stochastic.percD[0] < 20:
            buy_score += 1
        if self.dataclose[0] <= self.bollinger.lines.bot[0]:
            buy_score += 1
        if self.cci[0] < -100:
            buy_score += 1
        if self.macd.macd[0] > self.macd.signal[0]:
            buy_score += 1
        if self.ema_short[0] > self.ema_long[0]:
            buy_score += 1
        if self.adx[0] > 25:
            buy_score += 1

        # Sell conditions
        if self.rsi[0] > 70:
            sell_score += 1
        if self.stochastic.percK[0] > 80 and self.stochastic.percD[0] > 80:
            sell_score += 1
        if self.dataclose[0] >= self.bollinger.lines.top[0]:
            sell_score += 1
        if self.cci[0] > 100:
            sell_score += 1
        if self.macd.macd[0] < self.macd.signal[0]:
            sell_score += 1
        if self.ema_short[0] < self.ema_long[0]:
            sell_score += 1
        if self.adx[0] > 25:
            sell_score += 1

        if buy_score >= 4 and not self.position:
            self.log(f'BUY CREATE, {self.dataclose[0]:.2f}')
            self.order = self.buy()
        elif sell_score >= 4 and self.position:
            self.log(f'SELL CREATE, {self.dataclose[0]:.2f}')
            self.order = self.sell()

def run_backtest():
    crypto_symbol = "BTC"
    print(f"Fetching data for {crypto_symbol}...")
    data = fetch_historical_data(crypto_symbol, limit=100)
    
    if data.empty:
        print("No data available for backtest.")
        return

    # Create a cerebro instance
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
    cerebro.addsizer(bt.sizers.FixedSize, stake=0.1)  # Reduced position size

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    print(f'Starting Portfolio Value: ${initial_cash:,.2f}')

    # Run the backtest
    try:
        results = cerebro.run()
        strat = results[0]
        
        # Get trade analysis
        trade_analysis = strat.analyzers.trades.get_analysis()
        
        # Print results
        print(f'\nFinal Portfolio Value: ${cerebro.broker.getvalue():,.2f}')
        print(f'Total Number of Trades: {strat.trades}')
        
        # Only print these if we have trades
        if strat.trades > 0:
            try:
                sharpe = strat.analyzers.sharpe.get_analysis()['sharperatio']
                if sharpe is not None:
                    print(f'Sharpe Ratio: {sharpe:.2f}')
            except:
                print('Sharpe Ratio: N/A')

            try:
                drawdown = strat.analyzers.drawdown.get_analysis()['max']['drawdown']
                print(f'Max Drawdown: {drawdown:.2f}%')
            except:
                print('Max Drawdown: N/A')

            try:
                returns = strat.analyzers.returns.get_analysis()['rtot']
                print(f'Total Return: {returns*100:.2f}%')
            except:
                print('Total Return: N/A')

        else:
            print("\nNo trades were executed during the backtest period.")
            print("Consider adjusting the strategy parameters or increasing the data period.")

        # Plot results
        try:
            cerebro.plot(style='candlestick', barup='green', bardown='red', volume=True)
        except Exception as e:
            print(f"\nWarning: Could not generate plot: {str(e)}")
            print("Consider using a different plotting backend or matplotlib version.")
            
    except Exception as e:
        print(f"Error during backtest execution: {str(e)}")

if __name__ == "__main__":
    run_backtest()
