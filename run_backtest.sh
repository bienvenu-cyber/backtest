#!/bin/bash

# Ensure DISPLAY is unset to force Agg backend
unset DISPLAY

# Run the backtest
python3 bot2.py
