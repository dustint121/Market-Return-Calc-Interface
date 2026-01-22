# About
My project repo for creating an application to simplifying the process of calculating potential returns in the market (S&P 500) using the python yfinance API.

**Page 1**: Interface to calculate returns from the market in any period between 1975-2025. Has options for:
* Contribution per interval
* Contribution per interval
* Investing strategy: Dollar-cost averaging or 'Buying the Dip' 
* Interval Section : weekly, monthly, biannual, etc.

**Page 2**: Has daily treemaps for the composition of the entire S&P 500. Components are size-based on market caps and colored (green/red) based on daily return compared to previous close.  [Example here](https://market-return-calc-project1.s3.us-west-1.amazonaws.com/treemaps/2026-01-20_treemap.html) 
Treemaps can be stored locally in directory or with AWS S3.

Charts are inspired by the visualizations in the daily StockTwits newsletter made by FinViz found [here](https://finviz.com/map.ashx?t=sec&utm_source=dailyrip&utm_medium=newsletter&utm_campaign=email&_bhlid=cbb28bc82581f0f05f301a711c8c9b20a670e957)


**Page 3**: Has live candle-stick chart of S&P 500 that updates every minute while the market is open. Shows opening, low, high, and closing price per minute.



# Instructions for Running Code Repo on Local Machine

## In Project File after git cloning

1. [Optional] Add **.env** file for functionality to allow an AWS S3 bucket to store treemaps. 

> AWS_ACCESS_KEY_ID=

> AWS_SECRET_ACCESS_KEY =

> AWS_S3_BUCKET_NAME=

> AWS_REGION_NAME=

2. Run
>`pip install -r requirements.txt`

3. Run
>`python app.py `


## Updated treemaps and candlestick charts
The treemap charts on Page2 and candlestick chart on Page 3 are meant to be updated externally.

### Updating manually
Run this to get new treemaps
> python gen_daily_treemap.py [yyyy-mm-dd] [local]

* The second argument is if you want to make a treemap that is not the current date.
* The third argument is to decide if you want to store the file locally rather than with AWS S3. It is stored on AWS S3 by default otherwise.

Run this to update candlestick chart
> `gen_candlestick_chart.py`

### Updating with crontab (Linux OS only)
with crontab, you can set the OS to run scripts automatically at specified times and/or intervals

Use this to access crontab to edit
> `crontab -e`

Add these lines or the equivalent for your setup in the cron file.
>`CRON_TZ=America/New_York`

>`1 16 * * * /usr/bin/python path/gen_daily_treemap.py`

> `* * * * * /usr/bin/python path/gen_candlestick_chart.py`

This will have the OS run the treemap script at 4:01 p.m. New York time everyday and the candlestick script every minute.


### Python Prefect


### Apache Airflow
