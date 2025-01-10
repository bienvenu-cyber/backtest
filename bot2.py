import requests
import pandas as pd
import numpy as np
import datetime
import backtrader as bt
import matplotlib
matplotlib.use('Agg')

class CustomCSVWriter(bt.Analyzer):
    def __init__(self):
        self.trades = []
        
    def notify_trade(self, trade):
        if trade.isclosed:
            self.trades.append({
                'Entry Date': bt.num2date(trade.dtopen),
                'Exit Date': bt.num2date(trade.dtclose),
                'Entry Price': trade.price,
                'Exit Price': trade.pnlcomm / trade.size + trade.price,
                'Profit/Loss': trade.pnlcomm,
                'Return %': (trade.pnlcomm / trade.value) * 100
            })
    
    def get_analysis(self):
        return pd.DataFrame(self.trades)

class MyStrategy(bt.Strategy):
    params = (
        ('rsi_period', 14),
        ('rsi_oversold', 35),      # More selective
        ('rsi_overbought', 65),
        ('stoch_period', 14),
        ('stoch_oversold', 25),    # More selective
        ('stoch_overbought', 75),
        ('macd1', 12),
        ('macd2', 26),
        ('macdsig', 9),
        ('required_score', 3),     # More selective
        ('trail_percent', 0.015),  # Tighter trailing stop
        ('atr_periods', 14),
        ('atr_multiplier', 2)
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}')

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.trades = 0
        self.trailing_stop = None
        self.highest_price = 0
        self.lowest_price = float('inf')
        
        # Core indicators
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.stochastic = bt.indicators.Stochastic(self.data, period=self.params.stoch_period)
        self.macd = bt.indicators.MACD(
            self.data, 
            period_me1=self.params.macd1,
            period_me2=self.params.macd2,
            period_signal=self.params.macdsig
        )
        
        # Trend indicators
        self.ema_short = bt.indicators.EMA(self.data, period=12)
        self.ema_long = bt.indicators.EMA(self.data, period=26)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_periods)
        self.bollinger = bt.indicators.BollingerBands(self.data, period=20)
        
        # Volatility and trend strength
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_periods)
        self.adx = bt.indicators.ADX(self.data)

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
            
            # Core momentum signals
            if self.rsi[0] < self.params.rsi_oversold:
                buy_score += 1
                self.log(f'RSI oversold: {self.rsi[0]:.2f}')
            
            if (self.stochastic.percK[0] < self.params.stoch_oversold and 
                self.stochastic.percD[0] < self.params.stoch_oversold):
                buy_score += 1
                self.log(f'Stochastic oversold: K={self.stochastic.percK[0]:.2f}, D={self.stochastic.percD[0]:.2f}')
            
            # Trend confirmation
            if (self.macd.macd[-1] <= self.macd.signal[-1] and 
                self.macd.macd[0] > self.macd.signal[0]):
                buy_score += 1
                self.log('MACD crossing above signal')
            
            if (self.ema_short[0] > self.ema_long[0] and
                self.adx[0] > 25):  # Strong trend
                buy_score += 1
                self.log('Strong uptrend confirmed')

            # Volatility check
            if (self.atr[0] > self.atr[-5]):  # Increasing volatility
                buy_score += 1
                self.log('Increasing volatility')

            if buy_score >= self.params.required_score:
                self.log(f'BUY CREATE, {self.dataclose[0]:.2f}')
                self.order = self.buy()

        else:  # In the market
            # Update trailing stop
            if self.dataclose[0] > self.highest_price:
                self.highest_price = self.dataclose[0]
            
            # Dynamic trailing stop based on ATR
            stop_price = self.highest_price - (self.atr[0] * self.params.atr_multiplier)
            
            if self.dataclose[0] < stop_price:
                self.log(f'SELL CREATE (Dynamic Stop), {self.dataclose[0]:.2f}')
                self.order = self.sell()
                return
            
            # Regular sell signals
            sell_score = 0
            
            if self.rsi[0] > self.params.rsi_overbought:
                sell_score += 1
            
            if (self.stochastic.percK[0] > self.params.stoch_overbought and
                self.stochastic.percD[0] > self.params.stoch_overbought):
                sell_score += 1
            
            if (self.macd.macd[0] < self.macd.signal[0] and
                self.macd.macd[-1] >= self.macd.signal[-1]):
                sell_score += 1
            
            if (self.ema_short[0] < self.ema_long[0] and
                self.adx[0] > 25):
                sell_score += 1

            if sell_score >= self.params.required_score:
                self.log(f'SELL CREATE (Signal), {self.dataclose[0]:.2f}')
                self.order = self.sell()

def run_backtest():
    crypto_symbol = "BTC"
    print(f"Fetching data for {crypto_symbol}...")
    data = fetch_historical_data(crypto_symbol, limit=365)
    
    if data.empty:
        print("No data available for backtest.")
        return

    cerebro = bt.Cerebro()
    cerebro.broker.setcommission(commission=0.001)
    
    data_feed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(data_feed)
    cerebro.addstrategy(MyStrategy)
    
    initial_cash = 200
    cerebro.broker.set_cash(initial_cash)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(CustomCSVWriter, _name='csvwriter')

    print(f'Starting Portfolio Value: ${initial_cash:.2f}')

    try:
        results = cerebro.run()
        strat = results[0]
        
        final_value = cerebro.broker.getvalue()
        print(f'\nPerformance Summary:')
        print(f'Final Portfolio Value: ${final_value:.2f}')
        print(f'Total Return: {((final_value - initial_cash) / initial_cash * 100):.2f}%')
        print(f'Total Number of Trades: {strat.trades}')
        
        # Get detailed trade analysis
        trade_analysis = strat.analyzers.trades.get_analysis()
        if strat.trades > 0:
            won = trade_analysis.won.total if hasattr(trade_analysis, 'won') else 0
            lost = trade_analysis.lost.total if hasattr(trade_analysis, 'lost') else 0
            win_rate = (won/(won+lost)*100 if (won+lost)>0 else 0)
            print(f'Win Rate: {win_rate:.1f}%')
            
            # Get trade details
            trade_df = strat.analyzers.csvwriter.get_analysis()
            if not trade_df.empty:
                print("\nTop 5 Trades by Return %:")
                print(trade_df.sort_values('Return %', ascending=False).head().to_string())
            
    except Exception as e:
        print(f"Error during backtest execution: {str(e)}")

if __name__ == "__main__":
    run_backtest()
