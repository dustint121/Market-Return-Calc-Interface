from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime
import os
import math
import pandas as pd
import plotly.express as px 
from func import fetch_SP500_index_data_yf, read_all_treemap_metadata  
import boto3
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)



# DATA_SOURCE = "local"  # or "s3" 
DATA_SOURCE = "s3"


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

    first_date = df["Date"].min()
    last_date = df["Date"].max()
    current = first_date

    total_invested = 0.0
    shares_owned = 0.0
    intervals = []  # store each contribution

    while current <= last_date:
        sub = df[df["Date"] >= current]
        if sub.empty:
            break
        row = sub.iloc[0]
        price = float(row["Close"])
        date = row["Date"]

        shares = contribution / price
        shares_owned += shares
        total_invested += contribution

        intervals.append({
            "date": date.strftime("%Y-%m-%d"),
            "buy_price": round(price, 2),
            "contribution": round(contribution, 2),
            "shares": round(shares, 6),  # keep some precision
        })

        current = current + pd.Timedelta(days=step)

    final_price = float(df.iloc[-1]["Close"])
    final_value = shares_owned * final_price
    total_return = final_value - total_invested
    total_return_pct = (total_return / total_invested * 100) if total_invested > 0 else 0.0

    # compute per-interval final value and profit
    for it in intervals:
        it["final_value"] = round(it["shares"] * final_price, 2)
        it["profit"] = round(it["final_value"] - it["contribution"], 2)

    return jsonify({
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "final_price": round(final_price, 2),
        "intervals": intervals,  # NEW
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

TREEMAP_DIR = os.path.join(os.path.dirname(__file__), "treemaps")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "us-west-1")
s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)


@app.route("/page2", methods=["GET"])
def page2():
    use_s3 = (DATA_SOURCE == "s3")

    files = []
    if use_s3:
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
        data_source=DATA_SOURCE,
        aws_bucket=AWS_S3_BUCKET_NAME,
        aws_region=AWS_REGION_NAME,
    )

@app.route("/treemaps/<path:filename>")
def treemap_file(filename):
    if DATA_SOURCE == "s3":
        # proxy file from S3
        key = f"treemaps/{filename}"
        obj = s3_client.get_object(Bucket=AWS_S3_BUCKET_NAME, Key=key)
        # stream raw HTML
        return obj["Body"].read(), 200, {"Content-Type": "text/html"}
    else:
        return send_from_directory(TREEMAP_DIR, filename)

@app.route("/api/set_data_source", methods=["POST"])
def set_data_source():
    global DATA_SOURCE
    data = request.get_json()
    source = data.get("source", "local")
    if source not in ("local", "s3"):
        return jsonify({"error": "Invalid source"}), 400
    DATA_SOURCE = source
    return jsonify({"ok": True, "source": DATA_SOURCE})



# ---------- PAGE 3: Blank for now ----------

@app.route("/page3", methods=["GET"])
def page3():
    return render_template("page3.html")

if __name__ == "__main__":
    #set host toallow for all IPs
    app.run(host="0.0.0.0", debug=True)
