import requests
import pandas as pd
import numpy as np
import datetime
import backtrader as bt
import os
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set environment variables and matplotlib configuration
os.environ['MPLBACKEND'] = 'Agg'
os.environ['PYTHONHASHSEED'] = '0'
matplotlib.use('Agg')
plt.style.use('seaborn')

def fetch_historical_data(crypto_symbol, currency="USD", limit=365):
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
                if item["volumeto"] > 0:
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
        ('rsi_oversold', 40),     # Even less strict
        ('rsi_overbought', 60),   # Even less strict
        ('stoch_period', 14),
        ('stoch_oversold', 30),   # Less strict
        ('stoch_overbought', 70), # Less strict
        ('macd1', 12),
        ('macd2', 26),
        ('macdsig', 9),
        ('required_score', 2),    # Only require 2 conditions now
        ('trail_percent', 0.02)   # 2% trailing stop
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}')

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.trades = 0
        self.trailing_stop = None
        
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
        
        # Track highest price since entry
        self.highest_price = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.highest_price = order.executed.price
            else:
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.highest_price = 0
            self.trades += 1

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
            if (self.stochastic.percK[0] < self.params.stoch_oversold):
                buy_score += 1
                self.log(f'Stochastic oversold: K={self.stochastic.percK[0]:.2f}, D={self.stochastic.percD[0]:.2f}')
            
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
            # Update trailing stop
            if self.dataclose[0] > self.highest_price:
                self.highest_price = self.dataclose[0]
            
            # Check if price has fallen below trailing stop
            stop_price = self.highest_price * (1 - self.params.trail_percent)
            if self.dataclose[0] < stop_price:
                self.log(f'SELL CREATE (Trailing Stop), {self.dataclose[0]:.2f}')
                self.order = self.sell()
                return
            
            # Regular sell conditions
            sell_score = 0
            
            if self.rsi[0] > self.params.rsi_overbought:
                sell_score += 1
            
            if (self.stochastic.percK[0] > self.params.stoch_overbought):
                sell_score += 1
            
            if (self.macd.macd[-1] >= self.macd.signal[-1] and 
                self.macd.macd[0] < self.macd.signal[0]):
                sell_score += 1
            
            if (self.ema_short[-1] >= self.ema_long[-1] and 
                self.ema_short[0] < self.ema_long[0]):
                sell_score += 1

            if sell_score >= self.params.required_score:
                self.log(f'SELL CREATE, {self.dataclose[0]:.2f}')
                self.order = self.sell()


def run_backtest():
    # Create output directory for plots
    output_dir = Path('backtest_results')
    output_dir.mkdir(exist_ok=True)
    
    crypto_symbol = "BTC"
    print(f"Fetching data for {crypto_symbol}...")
    data = fetch_historical_data(crypto_symbol, limit=365)
    
    if data.empty:
        print("No data available for backtest.")
        return

    cerebro = bt.Cerebro()
    cerebro.broker.setcommission(commission=0.001)  # 0.1% commission
    
    data_feed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(data_feed)
    cerebro.addstrategy(MyStrategy)
    
    initial_cash = 200
    cerebro.broker.set_cash(initial_cash)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    print(f'Starting Portfolio Value: ${initial_cash:.2f}')

    try:
        results = cerebro.run()
        strat = results[0]
        
        # Get trade analysis
        trade_analysis = strat.analyzers.trades.get_analysis()
        
        final_value = cerebro.broker.getvalue()
        print(f'\nFinal Portfolio Value: ${final_value:.2f}')
        print(f'Total Return: {((final_value - initial_cash) / initial_cash * 100):.2f}%')
        print(f'Total Number of Trades: {strat.trades}')
        
        if strat.trades > 0:
            try:
                won = trade_analysis.won.total if hasattr(trade_analysis, 'won') else 0
                lost = trade_analysis.lost.total if hasattr(trade_analysis, 'lost') else 0
                print(f'Win Rate: {(won/(won+lost)*100 if (won+lost)>0 else 0):.1f}%')
            except:
                pass

        # New plotting code
        try:
            # Set the figure size and DPI
            plt.rcParams['figure.figsize'] = [15, 10]
            plt.rcParams['figure.dpi'] = 300
            
            # Generate the plots
            figs = cerebro.plot(style='candlestick',
                              barup='green',
                              bardown='red',
                              volume=False,
                              figsize=(15, 10))
            
            # Save each figure
            for idx, fig in enumerate(figs):
                for fidx, f in enumerate(fig):
                    # Adjust layout
                    f.tight_layout()
                    
                    # Save plot with timestamp
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = output_dir / f'backtest_plot_{timestamp}_{idx}_{fidx}.png'
                    
                    # Save with high quality settings
                    f.savefig(
                        filename,
                        dpi=300,
                        bbox_inches='tight',
                        pad_inches=0.2,
                        facecolor='white',
                        edgecolor='none'
                    )
                    plt.close(f)  # Close the figure to free memory
            
            print(f"\nPlots saved successfully in {output_dir}/ directory")
            
        except Exception as e:
            print(f"\nNote: Unable to generate plot. Error: {str(e)}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"Error during backtest execution: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up matplotlib resources
        plt.close('all')

if __name__ == "__main__":
    run_backtest()
