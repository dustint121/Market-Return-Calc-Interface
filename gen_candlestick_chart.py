from func import generate_candlestick_chart_sp500, is_market_open_now


if __name__ == "__main__":
    if is_market_open_now():
        generate_candlestick_chart_sp500()
    else:
        print("Market is closed. Candlestick chart generation skipped.")