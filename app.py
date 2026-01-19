from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime
import os
import math
import pandas as pd

from func import fetch_SP500_index_data_yf

app = Flask(__name__)

# ---------- PAGE 1: S&P 500 returns ----------

@app.route("/", methods=["GET"])
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
    interval = data["interval"]          # 'weekly', 'monthly', 'quarterly', 'biannual', 'annually', 'custom'
    custom_days = int(data.get("custom_days") or 0)

    # fetch daily SP500 data once for the whole period
    df = fetch_SP500_index_data_yf(start_year=start_year, end_year=end_year)
    # df has columns Date (yyyy-mm-dd string) and Close (float)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    # choose step in days based on interval
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

    # build investing schedule from first to last trading day
    first_date = df["Date"].min()
    last_date = df["Date"].max()
    current = first_date

    total_invested = 0.0
    shares_owned = 0.0

    while current <= last_date:
        # pick the closest trading day on or after current
        sub = df[df["Date"] >= current]
        if sub.empty:
            break
        price = sub.iloc[0]["Close"]
        shares_owned += contribution / price
        total_invested += contribution
        current = current + pd.Timedelta(days=step)

    final_price = df.iloc[-1]["Close"]
    final_value = shares_owned * final_price
    total_return = final_value - total_invested
    total_return_pct = (total_return / total_invested * 100) if total_invested > 0 else 0.0

    return jsonify({
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
    })

# ---------- PAGE 2: Treemaps List ----------

TREEMAP_DIR = os.path.join(os.path.dirname(__file__), "treemaps")

@app.route("/page2", methods=["GET"])
def page2():
    files = []
    if os.path.isdir(TREEMAP_DIR):
        for name in os.listdir(TREEMAP_DIR):
            if name.endswith("_treemap.html"):
                files.append(name)
        files.sort(reverse=True)  # latest first
    return render_template("page2.html", files=files)

@app.route("/treemaps/<path:filename>")
def treemap_file(filename):
    # serves the treemap HTML files
    return send_from_directory(TREEMAP_DIR, filename)

# ---------- PAGE 3: Blank for now ----------

@app.route("/page3", methods=["GET"])
def page3():
    return render_template("page3.html")

if __name__ == "__main__":
    #set host toallow for all IPs
    app.run(host="0.0.0.0", debug=True)
