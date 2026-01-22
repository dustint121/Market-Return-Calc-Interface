from func import generate_sp500_treemap, is_trading_day, get_market_data_of_sp500, generate_sp500_treemap
import sys
import os
from datetime import datetime

if __name__ == "__main__":
    # Generate the daily treemap

    # get argument from command line for date
        # using s3 by default
    if len(sys.argv) > 1:
        date_arg = sys.argv[1]
        use_S3_arg = True
        if len(sys.argv) > 2:
            if  sys.argv[2].lower() not in ['s3', 'local']:
                print("Second argument must be 's3' or 'local'. Exiting.")
                sys.exit(1)
            use_S3_arg = sys.argv[2].lower() == 's3'
            print(f"Using second argument. Using S3: {use_S3_arg}")
        #check date_arg format is valid: yyyy-mm-dd
        try:
            is_valid_date = bool(datetime.strptime(date_arg, '%Y-%m-%d'))

            BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder of this file
            # check if trading day
            if is_valid_date and is_trading_day(date_arg):
                # check if date_arg is pass the current date
                if date_arg > datetime.now().strftime('%Y-%m-%d'):
                    print(f"{date_arg} is in the future. Please provide a valid trading day.")
                    status_str = f"Invalid date provided to script: {date_arg} is in the future."
                    os.makedirs(f"{BASE_DIR}/status_logs", exist_ok=True)
                    current_date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    with open(f"{BASE_DIR}/status_logs/{current_date_str}_future_not_exist.txt", "w") as f:
                        f.write(status_str)
                    sys.exit(1)
                get_market_data_of_sp500(current_date=date_arg, use_S3=use_S3_arg)
                generate_sp500_treemap(date_arg, use_S3=use_S3_arg)

                status_str = f"Successfully generated treemap for {date_arg}." 
                current_date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                os.makedirs(f"{BASE_DIR}/status_logs", exist_ok=True)
                # check if date_arg is current date
                if date_arg == datetime.now().strftime('%Y-%m-%d'):
                    with open(f"{BASE_DIR}/status_logs/{current_date_str}_success_current_date.txt", "w") as f:
                        f.write(status_str)
                else:
                    with open(f"{BASE_DIR}/status_logs/{current_date_str}_success.txt", "w") as f:
                        f.write(status_str)
                sys.exit(1)
            else:
                print(f"{date_arg} is not a trading day.")
                status_str = f"No issue with script: {date_arg} not a trading day."
                os.makedirs(f"{BASE_DIR}/status_logs", exist_ok=True)
                current_date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                with open(f"{BASE_DIR}/status_logs/{current_date_str}_valid_nontrading_day.txt", "w") as f:
                    f.write(status_str)
                sys.exit(1)
        except ValueError:
            print(f"Invalid date format: {date_arg}. Use yyyy-mm-dd format.")
            status_str = f"Invalid date format provided to script: {date_arg}. Use yyyy-mm-dd format."
            os.makedirs(f"{BASE_DIR}/status_logs", exist_ok=True)
            current_date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            with open(f"{BASE_DIR}/status_logs/{current_date_str}_value_error.txt", "w") as f:
                f.write(status_str)
            sys.exit(1)
    else:
        print("Please provide a date argument in yyyy-mm-dd format.")