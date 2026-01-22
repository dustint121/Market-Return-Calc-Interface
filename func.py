import pandas as pd
from datetime import datetime
import numpy as np
import pandas_market_calendars as mcal
import os
import yfinance as yf
import requests 
import json
import bs4
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
import sys
import boto3
from dotenv import load_dotenv


load_dotenv()
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")


# Function to check if date is a trading day
    #date_str format: 'yyyy-mm-dd'
def is_trading_day(date_str): 
    exchange_calendar = mcal.get_calendar('NYSE')
    valid_days = exchange_calendar.valid_days(start_date=date_str, end_date=date_str)
    return date_str in valid_days.strftime('%Y-%m-%d').tolist()

def is_market_open_now():
    nyse = mcal.get_calendar('NYSE')
    current_time = pd.Timestamp.now(tz='America/New_York')
    start_range = current_time - pd.Timedelta(days=6) # look back 6 days to ensure we cover weekends/holidays
    end_range = current_time + pd.Timedelta(days=6) # look ahead 6 days
    schedule = nyse.schedule(start_date=start_range, end_date=end_range, tz='America/New_York')

    # Check if the current time falls within the open market hours in the schedule
    is_open = nyse.open_at_time(schedule, current_time) 
    return is_open

def get_time_until_next_market_open():
    nyse = mcal.get_calendar('NYSE')
    start_date = pd.Timestamp.now(tz='America/New_York')
    end_date = start_date + pd.Timedelta(days=7)
    schedule = nyse.schedule(start_date=start_date, end_date=end_date, tz='America/New_York')
    next_open = schedule.iloc[0]['market_open']
    # check if next_open is in the past, if so get the next one
    if next_open < start_date:
        next_open = schedule.iloc[1]['market_open']
    # print("Next market open:", next_open)
    #time until next open
    time_until_open = next_open - start_date
    days = time_until_open.days
    hours = time_until_open.seconds // 3600
    minutes = (time_until_open.seconds % 3600) // 60
    seconds = time_until_open.seconds % 60
    # print("Time until next market open:", time_until_open)
    # print(f"Which is: {days} days, {hours} hours, {minutes} minutes, {seconds} seconds")
    return next_open, time_until_open, days, hours, minutes, seconds


# Function to fetch S&P 500 index values using yfinance
def fetch_SP500_index_data_yf(start_year=None, end_year=None):
    """
    Fetches the historical data for the S&P 500 index from Yahoo Finance
    and returns it as a pandas DataFrame.
    """
    if start_year is None:
        start_year = 1975
    if end_year is None:
        end_year = datetime.now().year

    start_date = f"{start_year}-01-01"
    sp500 = yf.Ticker("^GSPC")
    df = sp500.history(start=start_date, end=f"{end_year}-12-31", interval="1d")

    # index is date, reset it and make a 'date' column
    df["Date"] = df.index
    # reset index to have 'Date' as a column
    df = df.reset_index(drop=True)
    df = df[['Date', 'Close']]
    # only need yyyy-mm-dd format for Date
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    # round the 'Close' column to 2 decimal places
    df['Close'] = df['Close'].round(2)
    return df

# Function to read https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
def get_current_sp500_companies(current_date=None, save_to_csv=False):
    """
    Reads the list of S&P 500 companies from Wikipedia and returns it as a pandas DataFrame.
    """
    if current_date is None:
        current_date = datetime.now().strftime('%Y-%m-%d')

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    email = "anon72@gmail.com"
    header = { 'User-Agent': email }
    request = requests.get(url, headers=header)
    soup = bs4.BeautifulSoup(request.text, 'html.parser')


    # get table with 'id' of 'constituents'
    table_current_constituents = soup.find('table', {'id': 'constituents'})
    df = pd.read_html(StringIO(str(table_current_constituents)))[0]
    df = df[['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry', 'Founded', 'Date added']]


    #go through changes table to: 
        #  remove companies that were removed before current_date 
        #  add those that were added before current_date
    #get table with 'id' of 'changes'
    table_changes = soup.find('table', {'id': 'changes'})
    df_changes = pd.read_html(StringIO(str(table_changes)))[0]
    list_of_dates = df_changes["Effective Date"]["Effective Date"].tolist()
    #convert 'month_name day, year' to 'yyyy-mm-dd'
    list_of_dates = [pd.to_datetime(date).strftime('%Y-%m-%d') for date in list_of_dates]
    list_of_added_tickers = df_changes["Added"]["Ticker"].tolist()
    list_of_added_securities = df_changes["Added"]["Security"].tolist()
    list_of_removed_tickers = df_changes["Removed"]["Ticker"].tolist()
    list_of_removed_securities = df_changes["Removed"]["Security"].tolist()
    #make df from lists
    df_changes_final = pd.DataFrame({
        "Effective Date": list_of_dates,
        "Added Ticker": list_of_added_tickers,
        "Added Security": list_of_added_securities,
        "Removed Ticker": list_of_removed_tickers,
        "Removed Security": list_of_removed_securities
    })
    # filter changes after current_date
    df_changes_final = df_changes_final[pd.to_datetime(df_changes_final["Effective Date"]) >= pd.to_datetime(current_date)]
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
    company_df = pd.read_csv(f"{BASE_DIR}/sp500_companies_2023-2025.csv")
    for index, row in df_changes_final.iterrows():
        #remove the company in the "Added Ticker" from df if it exists
        if pd.notna(row["Added Ticker"]):
            df = df[df["Symbol"] != row["Added Ticker"]] # remove added companies
        if pd.notna(row["Removed Ticker"]):
            #read company info from company_df
            company_info = company_df[company_df["Symbol"] == row["Removed Ticker"]]
            if not company_info.empty:
                df = pd.concat([df, company_info], ignore_index=True) # add removed companies back

    if save_to_csv:
        df.to_csv(f"sp500_companies_as_of_{current_date}.csv", index=False)
    return df


#NOTE: market cap is of current date at time of running code, will not reflect historical market cap
def get_market_data_of_sp500(current_date="2025-12-31", use_S3=False):
    df = None
    if current_date < "2026-02-01" and current_date >= "2025-12-23":
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
        df = pd.read_csv(f"{BASE_DIR}/sp500_companies_eoy2025.csv")
    else:
        df = get_current_sp500_companies()

    df["Symbol"] = df["Symbol"].str.replace(r'\.', '-', regex=True) #debugging for BRK-B and BF-B
    df['market_cap'] = None # market capitalization
    df['percent_change'] = None # percent change from previous close
    list_of_tickers = df['Symbol'].tolist()

    # use yfinance for each ticker in one call
    tickers = yf.Tickers(' '.join(list_of_tickers))

    # access info for each ticker to see if it exists
    index = 0
    total_market_cap = 0
    for ticker_symbol in list_of_tickers:
        try:
            print(f"Processing {index+1}/{len(list_of_tickers)}: {ticker_symbol}")

            # if ticker symbol is "MRSH" and current_date is before 2026-01-06,  switch to "MMC"
                # ticker symbol change; no data under "MRSH" before 2026-01-06 
            if ticker_symbol == "MRSH" and current_date < "2026-01-06":
                ticker_symbol = "MMC"
 
            # get ticker info
            ticker_info = None
            if ticker_symbol != "MMC":
                ticker_info = tickers.tickers[ticker_symbol].info
            else:
                ticker_info = yf.Ticker(ticker_symbol).info
            
            market_cap = ticker_info.get('marketCap')
            # #adjust market cap based on price change if not using current date
            if current_date != datetime.now().strftime('%Y-%m-%d'):
                # print(f"Adjusting market cap for {ticker_symbol} based on price change...")
                current_price = ticker_info.get('currentPrice')
                price_history = yf.Ticker(ticker_symbol).history(start=current_date, period="2d")
                old_price = price_history['Close'].iloc[0]
                market_cap = market_cap * (old_price / current_price) if old_price != 0 else market_cap

            df.at[index, 'market_cap'] = market_cap
            total_market_cap += market_cap

            # use mcal to get previous trading day
            nyse = mcal.get_calendar('NYSE')
            schedule = nyse.schedule(start_date='2025-12-20', end_date=current_date)
            trading_days = mcal.date_range(schedule, frequency='1D').strftime('%Y-%m-%d').tolist()
            previous_trading_day = trading_days[-2]

            # get percent change from previous close
                #NOTE: period does not account for non-trading days, so a larger period is needed
            price_history = yf.Ticker(ticker_symbol).history(start=previous_trading_day, period="10d")
 
            # get percent change from current_date and previous trading day
            if not price_history.empty:
                previous_close = price_history['Close'].iloc[0]
                current_price = price_history['Close'].iloc[1]
                percent_change = ((current_price - previous_close) / previous_close * 100) if previous_close != 0 else 0
                df.at[index, 'percent_change'] = percent_change
            index += 1
        except Exception as e:
            print(f"{ticker_symbol}: Not Found - {e}")

    # print(f"Total Market Capitalization of S&P 500: {total_market_cap}")
    df['%_of_total_market_cap'] = df['market_cap'] / total_market_cap * 100


    if use_S3:
        # write to S3
        s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        s3_client.put_object(
                                Bucket=AWS_S3_BUCKET_NAME,
                                Key=f"data/{current_date}.csv",
                                Body=csv_buffer.getvalue(),
                                ContentType="text/csv"
                            )
    else:
    # write to csv
        os.makedirs("data", exist_ok=True)
        df.to_csv(f"data/{current_date}.csv", index=False)
        return df, total_market_cap



def generate_sp500_treemap(current_date="2025-12-31", test_mode=False, use_industry=False, use_S3=False):
    df = None
    if test_mode:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
        df = pd.read_csv(f"{BASE_DIR}/sp500_companies_market_cap_eoy2025.csv")
    else:
        if use_S3:
            # read from S3
            s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
            obj = s3_client.get_object(Bucket=AWS_S3_BUCKET_NAME, Key=f"data/{current_date}.csv")
            df = pd.read_csv(obj['Body'])
        else:
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
            df = pd.read_csv(f"{BASE_DIR}/data/{current_date}.csv") #run get_market_data_of_sp500 first to generate this file

    # percent_change,%_of_total_market_cap
    # have color based on percent_change divided by 100 to get -1 to 1 range
    df['proportion_change'] = df['percent_change'] / 100
    # test color
    df['color'] = df['proportion_change']


    # get absolute max of color for scaling
    max_color = max(abs(df['color'].min()), abs(df['color'].max()))
    # range_color = [-max_color, max_color]
    
    range_color = [-0.03, 0.03] # fixed range for better comparison


    # convert market_cap to "B" for billions in hover
    # if 4 digits after decimal, convert to trillions
    df['market_cap_billions'] = df['market_cap'].apply(lambda x: f"${x/1_000_000_000_000:.2f}T" if x >= 1_000_000_000_000 else f"${x/1_000_000_000:.2f}B")


    # reverse above scale so that negative is red and positive is green
    custom_color_scale = [
        (0.0, "rgb(180,0,0)"),      # strong red for lowest (e.g. -5%)
        (0.25, "rgb(255,160,122)"), # light red
        (0.5, "rgb(230,230,230)"),  # dark grey/black around 0
        (0.75, "rgb(144,238,144)"), # light green
        (1.0, "rgb(0,150,0)")       # strong green for highest (e.g. +5%)
    ]

    # set color range for treemap
    path = None
    if use_industry:
        path = [px.Constant("S&P 500"), "GICS Sector", "GICS Sub-Industry", "Symbol"]
    else:
        path = [px.Constant("S&P 500"), "GICS Sector", "Symbol"]

    fig = px.treemap( 
        df,
        path=path,          # hierarchy
        values="%_of_total_market_cap",                 # box size
        color="color",                     # red/green
        color_continuous_scale=custom_color_scale,
        color_continuous_midpoint=0,
        range_color=range_color,  
        hover_data={
            "Symbol": True,
            "market_cap": True,
            "percent_change": ':.2f',
            "%_of_total_market_cap": ':.3f'
        },
        custom_data=["Security", "market_cap", "%_of_total_market_cap", 
                    "percent_change", "color", "market_cap_billions"
                    ,"GICS Sub-Industry"],
        title=f"{current_date} : S&P 500 Treemap: Constituents by Market Cap and Percent Change"

    )

    # convert market_cap to string with commas for hover
    df['market_cap'] = df['market_cap'].apply(lambda x: f"{x:,}")



    parents = fig.data[0]["parents"]
    # make empty hovertemplates array
    levels = np.empty(len(fig.data[0]["parents"]), dtype=object)

    # 0=root, 1=sector, 2=security for this path
    if use_industry == False:
    # if parent is '', level 0
        levels[np.array(parents) == ''] = 0
        # if parent is 'S&P 500', level 1
        levels[np.array(parents) == 'S&P 500'] = 1
        # if parent is not 'S&P 500' and not '', level 2
        levels[(np.array(parents) != 'S&P 500') & (np.array(parents) != '')] = 2
    else:
    # do str split on '/' and get length to determine if level 2 or 3
        for i in range(len(parents)):
            if parents[i] == '':
                levels[i] = 0  # root level
            elif parents[i] == 'S&P 500':
                levels[i] = 1  # GICS Sector  
            else:  # if parents[i] != '' and parents[i] != 'S&P 500':
                if len(str(parents[i]).split('/')) == 2:
                    levels[i] = 2  # GICS Sub-Industry
                if len(str(parents[i]).split('/')) == 3:
                    levels[i] = 3  # Constituent

    
    # use mcal to get previous trading day
    nyse = mcal.get_calendar('NYSE')
    schedule = nyse.schedule(start_date='2025-12-20', end_date=current_date)
    trading_days = mcal.date_range(schedule, frequency='1D').strftime('%Y-%m-%d').tolist()
    previous_trading_day = trading_days[-2]

    # use yfinance to get overall % change of S&P 500 for root level
    sp500 = yf.Ticker("^GSPC")
    sp500_history = sp500.history(start=previous_trading_day, period="10d")
    sp500_percent_change = None
    if not sp500_history.empty:
        sp500_previous_close = sp500_history['Close'].iloc[0]
        sp500_current_price = sp500_history['Close'].iloc[1]
        sp500_percent_change = ((sp500_current_price - sp500_previous_close) / sp500_previous_close * 100) if sp500_previous_close != 0 else 0


    total_market_cap = df['market_cap'].str.replace('$','').str.replace(',','').astype(float).sum()
    # convert to trillions for display
    total_market_cap_str = f"${total_market_cap/1_000_000_000_000:.2f}T"
    print(f"S&P 500 Percent Change: {sp500_percent_change:.2f}%")
    print(f"Total Market Capitalization of S&P 500: {total_market_cap_str}")


    # --- templates for each level ---
    root_tmpl = (
        "<b>%{label}</b><br>"             # S&P 500
        "Total Market Cap: " + total_market_cap_str + "<br>"
        "Overall Percent Change: " + f"{sp500_percent_change:.2f}%" +
        "<extra></extra>"
    )

    sector_tmpl = (
        "<b>%{label}</b><br>"             # GICS Sector name
        "Sector Share of S&P 500: %{value:.2f}%"
        "<extra></extra>"
    )

    industry_tmpl = (
        "<b>%{label}</b><br>"             # GICS Sub-Industry name
        "Industry Share of S&P 500: %{value:.2f}%"
        "<extra></extra>"
    )

    security_tmpl = (
        "<b>%{customdata[0]}</b><br>"     # Symbol
        "Company: %{label}<br>"          # Security
        "Industry: %{customdata[6]}<br>" # GICS Sub-Industry
        # "Market cap: %{customdata[1]}<br>"   # raw market_cap 
        "Market Cap: %{customdata[5]}<br>" # market_cap in billions/trillions
        "% of S&P 500: %{customdata[2]:.2f}%<br>" # % of total market cap
        "Percent Change: %{customdata[3]:.2f}%<br>" # percent_change from previous close
        "<extra></extra>"
    )

    hovertemplates = np.empty(len(levels), dtype=object)

    if use_industry == False:
        hovertemplates[levels == 0] = root_tmpl
        hovertemplates[levels == 1] = sector_tmpl 
        hovertemplates[levels == 2] = security_tmpl  # leaf level    
    else:
        hovertemplates[levels == 0] = root_tmpl
        hovertemplates[levels == 1] = sector_tmpl
        hovertemplates[levels == 2] = industry_tmpl
        hovertemplates[levels == 3] = security_tmpl  # leaf level

    fig.update_traces(hovertemplate=hovertemplates)

    fig.update_coloraxes(showscale=False) # hide color scale bar



    # set specific color for sector level boxes (dark grey)
    colors = np.array(fig.data[0].marker.colors, dtype=object)
    sector_color = "rgb(40,40,40)"   # dark grey for sectors
    colors[levels == 1] = sector_color    # level 1 = GICS Sector
    fig.update_traces(marker_colors=colors)

    # fig.show()
    # save to html
    if use_S3:
        # write to S3
        s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        html_buffer = StringIO()
        fig.write_html(html_buffer)
        s3_client.put_object(
                                Bucket=AWS_S3_BUCKET_NAME,
                                Key=f"treemaps/{current_date}_treemap.html",
                                Body=html_buffer.getvalue(),
                                ContentType="text/html"
                            )
        # store sp500_percent_change and total_market_cap_str to json
        metadata_buffer = StringIO()
        json.dump({
            "date": current_date,
            "sp500_percent_change": sp500_percent_change,
            "total_market_cap": total_market_cap_str
        }, metadata_buffer)
        s3_client.put_object(
                                Bucket=AWS_S3_BUCKET_NAME,
                                Key=f"treemap_metadata/{current_date}.json",
                                Body=metadata_buffer.getvalue(),
                                ContentType="application/json"
                            )
    else:
        os.makedirs("treemaps", exist_ok=True)
        fig.write_html(f"treemaps/{current_date}_treemap.html")

        #store sp500_percent_change and total_market_cap_str to json
        os.makedirs(f"{BASE_DIR}/treemap_metadata", exist_ok=True)
        with open(f"{BASE_DIR}/treemap_metadata/{current_date}.json", "w") as json_file:
            json.dump({
                "date": current_date,
                "sp500_percent_change": sp500_percent_change,
                "total_market_cap": total_market_cap_str
            }, json_file)




def read_all_treemap_metadata(use_S3=False):
    metadata = []
    if use_S3:
        # read from S3
        s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        response = s3_client.list_objects_v2(Bucket=AWS_S3_BUCKET_NAME, Prefix="treemap_metadata/")
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                if key.endswith(".json"):
                    json_obj = s3_client.get_object(Bucket=AWS_S3_BUCKET_NAME, Key=key)
                    data = json.load(json_obj['Body'])
                    metadata.append(data)
    else:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
        for json_file in os.listdir(f"{BASE_DIR}/treemap_metadata"):
            if json_file.endswith(".json"):
                with open(f"{BASE_DIR}/treemap_metadata/{json_file}", "r") as f:
                    data = json.load(f)
                    metadata.append(data)
    metadata_df = pd.DataFrame(metadata)
    metadata_df = metadata_df.sort_values(by="date", ascending=True).reset_index(drop=True)
    metadata_df['sp500_percent_change'] = metadata_df['sp500_percent_change'].round(2)
    return metadata_df

# Function to generate candlestick chart of S&P 500 index for today with 1-minute intervals
    # store locally in sp500_candlestick_daily_1m.html
def generate_candlestick_chart_sp500():
    nyse = mcal.get_calendar('NYSE')
    current_date = pd.Timestamp.now(tz='America/New_York').normalize()
    schedule = nyse.schedule(start_date=current_date, end_date=current_date, tz='America/New_York')
    market_open = schedule.iloc[0]['market_open']
    market_close = schedule.iloc[0]['market_close']
    print(f"Market open: {market_open}, Market close: {market_close}")
    interval = pd.date_range(start=market_open, end=market_close, freq='1min')
    df_intervals = pd.DataFrame(interval, columns=['Datetime'])
    df_intervals['Datetime'] = df_intervals['Datetime'].dt.tz_convert('America/New_York')


    current_date = datetime.now().strftime('%Y-%m-%d')
    start_time = pd.to_datetime(f"{current_date} 09:30:00").tz_localize('America/New_York')
    end_time = pd.to_datetime(f"{current_date} 16:00:00").tz_localize('America/New_York')
    price_history = yf.download("^GSPC", start=start_time, end=end_time, interval="1m", 
                                prepost=True, ignore_tz=False)
    # print(price_history.head())

    
    # convert DateTime index to America/New_York timezone
    price_history.index = price_history.index.tz_convert('America/New_York')
    price_history["Datetime"] = price_history.index
    # reset index to make Datetime a column
    price_history = price_history.reset_index(drop=True)
    price_history = price_history[['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume']]
    price_history.columns = price_history.columns.droplevel(1) # drop the extra level from multi-index columns


    # merge price_history into df_intervals on Datetime
    df_intervals = df_intervals.merge(price_history, left_on='Datetime', right_on='Datetime', how='left')

    # graph candlestick chart of SP500 index for today with plotly
    fig = go.Figure(data=[go.Candlestick(x=df_intervals['Datetime'],
                open=df_intervals['Open'],
                high=df_intervals['High'],
                low=df_intervals['Low'],
                close=df_intervals['Close'])])
    fig.update_layout(title='S&P 500 Index Candlestick Chart',
                      xaxis_title='Time',
                      yaxis_title='S&P 500 Index Value')
    fig.update_xaxes(tickangle=45)
    fig.update_layout(plot_bgcolor='black')
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)

    # fig.show()
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
    output_path = os.path.join(BASE_DIR, "sp500_candlestick_daily_1m.html")
    print(f"Saving candlestick chart to {output_path}...")
    fig.write_html(output_path)






if __name__ == "__main__":
    #use mcal to get trading days between 2026-01-01 to 2026-01-17 in yyyy-mm-dd format
    # nyse = mcal.get_calendar('NYSE')
    # schedule = nyse.schedule(start_date='2026-01-01', end_date='2026-01-03')
    # trading_days = mcal.date_range(schedule, frequency='1D').strftime('%Y-%m-%d').tolist()

    # for current_date in trading_days:
    #     print(f"Generating treemap for {current_date}...")
    #     # generate market data
    #     # get_market_data_of_sp500(current_date)
    #     get_market_data_of_sp500(current_date, use_S3=True)
    #     # generate treemap
    #     # generate_sp500_treemap(current_date)
    #     generate_sp500_treemap(current_date, use_S3=True)




    # get argument from command line for date
        # using s3 by default
    x = 1

