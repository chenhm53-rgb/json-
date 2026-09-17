# Cookie Credit API Checker

This tool sends each cookie to the configured credit API, reads the returned credit field, and counts how many records have each credit value.

The static HTML page is used to import and inspect files and export `credit_api_config.json`. Run `credit_stats_scraper.py` locally for real requests because browser CORS and cookie security rules prevent reliable arbitrary Cookie headers.

Run on macOS or Linux:

    python3 credit_stats_scraper.py --config credit_api_config.json --input cookies.json

Run on Windows:

    python credit_stats_scraper.py --config credit_api_config.json --input cookies.json

Configure the real API URL, GET or POST method, and response JSON path such as `data.credits`. The script supports `{identifier}`, `{index}`, and `{cookie}` templates, retries, delay, timeout, JSON/CSV details, and sorted credit summary output.

Never share full cookies, passwords, verification codes, or tokens. Use this only with accounts and APIs you are authorized to access.
