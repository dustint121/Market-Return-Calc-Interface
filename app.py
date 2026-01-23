from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
from datetime import datetime
import os
import math
import pandas as pd
import plotly.express as px 
from func import (fetch_SP500_index_data_yf, read_all_treemap_metadata, is_market_open_now,
                    get_time_until_next_market_open)
import boto3
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)



# ---------- PAGE 1: S&P 500 returns ----------
GRAPH_DIR = os.path.join(os.path.dirname(__file__), "")
os.makedirs(GRAPH_DIR, exist_ok=True)


@app.route("/", methods=["GET"]) #if commented out: it gives 404 error, but /page1 still works
@app.route("/page1", methods=["GET"])
def page1():
    start_year = 1975
    end_year = 2025
    return render_template("page1.html",
                           start_year=start_year,
                           end_year=end_year)


@app.route("/api/returns", methods=["POST"])
def api_returns():
    data = request.get_json()
    start_year = int(data["start_year"])
    end_year = int(data["end_year"])
    contribution = float(data["contribution"])
    interval = data["interval"]
    custom_days = int(data.get("custom_days") or 0)

    # strategy and dip threshold
    strategy = data.get("strategy", "dca")  # "dca", "buy_the_dip", "buy_the_dip_non_immediate"
    dip_threshold_pct = float(data.get("dip_threshold_pct") or 0.0)  # e.g. 2 for -2%

    df = fetch_SP500_index_data_yf(start_year=start_year, end_year=end_year)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    if interval == "weekly":
        step = 7
    elif interval == "monthly":
        step = 30
    elif interval == "quarterly":
        step = 91
    elif interval == "biannual":
        step = 182
    elif interval == "annually":
        step = 365
    elif interval == "custom" and custom_days > 0:
        step = custom_days
    else:
        return jsonify({"error": "Invalid interval"}), 400

    total_invested = 0.0
    shares_owned = 0.0
    intervals = []

    # Start at first trading day
    if df.empty:
        return jsonify({
            "total_invested": 0.0,
            "final_value": 0.0,
            "total_return": 0.0,
            "total_return_pct": 0.0,
            "final_price": 0.0,
            "intervals": [],
            "strategy": strategy,
            "dip_threshold_pct": dip_threshold_pct,
        })

    next_contribution_date = df["Date"].iloc[0]

    # For dip strategies: accumulated cash not yet invested
    accumulated_cash = 0.0
    prev_close = None  # previous trading day's close, for “immediate” dip detection

    # Precompute a Series for easier date-based lookup
    df = df.reset_index(drop=True)

    for _, row in df.iterrows():
        date = row["Date"]
        price = float(row["Close"])

        # 1) Contribution becomes available on/after next_contribution_date
        if date >= next_contribution_date:
            if strategy == "dca":
                invest_amount = contribution
                shares = invest_amount / price
                shares_owned += shares
                total_invested += invest_amount

                intervals.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "buy_price": round(price, 2),
                    "contribution": round(invest_amount, 2),
                    "shares": round(shares, 6),
                    "strategy": "dca",
                })
            else:
                # both dip strategies: accumulate cash at each interval
                accumulated_cash += contribution
                total_invested += contribution
            # schedule next contribution
            next_contribution_date = next_contribution_date + pd.Timedelta(days=step)

        # 2A) Immediate buy-the-dip: check only vs previous trading day's close
        if strategy == "buy_the_dip":
            if prev_close is not None and dip_threshold_pct > 0 and accumulated_cash > 0:
                change_pct = (price - prev_close) / prev_close * 100.0
                dip_level = -abs(dip_threshold_pct)
                if change_pct <= dip_level:
                    invest_amount = accumulated_cash
                    shares = invest_amount / price
                    shares_owned += shares
                    accumulated_cash = 0.0

                    intervals.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "buy_price": round(price, 2),
                        "contribution": round(invest_amount, 2),
                        "shares": round(shares, 6),
                        "strategy": "buy_the_dip",
                        "percent_change_vs_prev": round(change_pct, 2),
                    })

        # 2B) Non-immediate buy-the-dip: look back over the interval window
        if strategy == "buy_the_dip_non_immediate":
            if dip_threshold_pct > 0 and accumulated_cash > 0:
                # Look back up to 'step' calendar days before current date
                window_start = date - pd.Timedelta(days=step)
                mask = (df["Date"] >= window_start) & (df["Date"] < date)
                window = df.loc[mask]

                dipped = False
                worst_change = None

                # If there aren't enough days, this window will just be shorter; that's fine.
                for _, prev_row in window.iterrows():
                    prev_price = float(prev_row["Close"])
                    if prev_price == 0:
                        continue
                    change_pct = (price - prev_price) / prev_price * 100.0
                    if worst_change is None or change_pct < worst_change:
                        worst_change = change_pct

                if worst_change is not None:
                    dip_level = -abs(dip_threshold_pct)
                    if worst_change <= dip_level:
                        invest_amount = accumulated_cash
                        shares = invest_amount / price
                        shares_owned += shares
                        accumulated_cash = 0.0
                        dipped = True

                        intervals.append({
                            "date": date.strftime("%Y-%m-%d"),
                            "buy_price": round(price, 2),
                            "contribution": round(invest_amount, 2),
                            "shares": round(shares, 6),
                            "strategy": "buy_the_dip_non_immediate",
                            "worst_change_in_window": round(worst_change, 2),
                            "window_days": step,
                        })

        # 3) update prev_close for “immediate” dip strategy
        prev_close = price

    final_price = float(df.iloc[-1]["Close"])

    # If using a dip strategy and there is leftover cash, add a final “uninvested” interval
    if strategy in ("buy_the_dip", "buy_the_dip_non_immediate") and accumulated_cash > 0:
        intervals.append({
            "date": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
            "buy_price": None,
            "contribution": round(accumulated_cash, 2),
            "shares": 0.0,
            "strategy": f"{strategy}_uninvested",
            "percent_change_vs_prev": None,
        })

    if strategy == "dca":
        final_value = shares_owned * final_price
    else:
        # invested shares + any leftover accumulated_cash
        final_value = shares_owned * final_price + accumulated_cash

    total_return = final_value - total_invested
    total_return_pct = (total_return / total_invested * 100) if total_invested > 0 else 0.0

    for it in intervals:
        if it["shares"] > 0:
            it["final_value"] = round(it["shares"] * final_price, 2)
            it["profit"] = round(it["final_value"] - it["contribution"], 2)
        else:
            it["final_value"] = round(it["contribution"], 2)
            it["profit"] = 0.0

    return jsonify({
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "final_price": round(final_price, 2),
        "intervals": intervals,
        "strategy": strategy,
        "dip_threshold_pct": dip_threshold_pct,
    })




@app.route("/api/sp500_chart", methods=["POST"])
def api_sp500_chart():
    data = request.get_json()
    start_year = int(data["start_year"])
    end_year = int(data["end_year"])

    df = fetch_SP500_index_data_yf(start_year=start_year, end_year=end_year)

    fig = px.line(
        df,
        x="Date",
        y="Close",
        title=f"S&P 500 Index ({start_year}-{end_year})",
        markers=True,
    )
    fig.update_traces(marker=dict(size=4))
    fig.update_layout(xaxis_title="Date", yaxis_title="Index Value")
    fig.update_xaxes(tickangle=45)
    fig.update_traces(
        hovertemplate="Date: %{x}<br>Index Value: %{y:.2f}<extra></extra>"
    )

    filename = "sp500_chart_to_display.html"  # or any name you like
    filepath = os.path.join(GRAPH_DIR, filename)
    fig.write_html(filepath)

    return jsonify({"chart_url": f"/graphs/{filename}"})



@app.route("/graphs/<path:filename>")
def serve_graph(filename):
    return send_from_directory(GRAPH_DIR, filename) 


# ---------- PAGE 2: Treemaps List ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
TREEMAP_DIR = os.path.join(BASE_DIR, "treemaps")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "us-west-1")


def s3_config_valid():
    """Return True only if all required S3 env vars are non-empty."""
    return all([
        AWS_ACCESS_KEY_ID,
        AWS_SECRET_ACCESS_KEY,
        AWS_S3_BUCKET_NAME,
        AWS_REGION_NAME,
    ])


s3_client = None
if s3_config_valid():
    s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

 
@app.route("/page2", methods=["GET"])
def page2():
    s3_ok = s3_config_valid()

    # read requested source from query string: ?source=local or ?source=s3
    requested = request.args.get("source", "").lower()
    if requested not in ("local", "s3"):
        requested = "s3" if s3_ok else "local"

    # effective source: only use s3 if requested AND available
    data_source = "s3" if (requested == "s3" and s3_ok) else "local"
    use_s3 = (data_source == "s3")

    files = []
    if use_s3 and s3_client is not None:
        resp = s3_client.list_objects_v2(Bucket=AWS_S3_BUCKET_NAME, Prefix="treemaps/")
        if "Contents" in resp:
            for obj in resp["Contents"]:
                key = obj["Key"]
                if key.endswith("_treemap.html"):
                    files.append(os.path.basename(key))
    else:
        if os.path.isdir(TREEMAP_DIR):
            for name in os.listdir(TREEMAP_DIR):
                if name.endswith("_treemap.html"):
                    files.append(name)

    files.sort(reverse=True)

    meta_df = read_all_treemap_metadata(use_S3=use_s3)
    meta_by_date = {}
    for _, row in meta_df.iterrows():
        meta_by_date[row["date"]] = {
            "sp500_percent_change": row["sp500_percent_change"],
            "total_market_cap": row["total_market_cap"],
        }

    return render_template(
        "page2.html",
        files=files,
        meta_by_date=meta_by_date,
        data_source=data_source,   # drives UI state
        aws_bucket=AWS_S3_BUCKET_NAME,
        aws_region=AWS_REGION_NAME,
        s3_enabled=s3_ok,
    )



@app.route("/treemaps/<path:filename>")
def treemap_file(filename):
    s3_ok = s3_config_valid()
    requested = request.args.get("source", "").lower()
    data_source = "s3" if (requested == "s3" and s3_ok) else "local"

    if data_source == "s3" and s3_ok and s3_client is not None:
        key = f"treemaps/{filename}"
        obj = s3_client.get_object(Bucket=AWS_S3_BUCKET_NAME, Key=key)
        return obj["Body"].read(), 200, {"Content-Type": "text/html"}
    else:
        return send_from_directory(TREEMAP_DIR, filename)



@app.route("/api/set_data_source", methods=["POST"])
def set_data_source():
    data = request.get_json()
    source = data.get("source", "local")
    if source not in ("local", "s3"):
        return jsonify({"error": "Invalid source"}), 400

    # if S3 requested but not available, force local
    s3_ok = s3_config_valid()
    effective = "s3" if (source == "s3" and s3_ok) else "local"
    if source == "s3" and not s3_ok:
        resp = make_response(jsonify({"ok": False, "source": effective, "reason": "s3_unavailable"}), 400)
    else:
        resp = make_response(jsonify({"ok": True, "source": effective}))

    #using http, not https; so secure must be False
    resp.set_cookie("data_source", effective, max_age=30*24*3600,
                    httponly=True,       # Prevents JS access (Security best practice)
                    secure=False,        # MUST be False for HTTP
                    samesite='Lax'       # Standard for modern browsers over HTTP
    )
    return resp




# ---------- PAGE 3: Market Status ----------

@app.route("/page3", methods=["GET"])
def page3():
    open_now = is_market_open_now()
    next_open_dt = None
    days = hours = minutes = seconds = 0

    if not open_now:
        next_open, time_until, days, hours, minutes, seconds = get_time_until_next_market_open()
        # next_open is a tz-aware Timestamp in America/New_York
        next_open_dt = next_open.isoformat()  # for JS, keeps timezone

    return render_template(
        "page3.html",
        market_open=open_now,
        next_open_iso=next_open_dt,
        rem_days=days,
        rem_hours=hours,
        rem_minutes=minutes,
        rem_seconds=seconds,
    )

if __name__ == "__main__":
    #set host toallow for all IPs
    app.run(host="0.0.0.0", debug=True)
