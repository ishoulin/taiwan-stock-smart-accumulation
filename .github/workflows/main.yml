name: Thousand-Dollar Blackhorse Scanner

on:
  workflow_dispatch: # 支援手動一鍵觸發
  schedule:
    - cron: '30 7 * * 1-5' # UTC 07:30 = 台北時間平日 15:30 (收盤後自動執行)

jobs:
  run-scanner:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Stock Scanner & Send Email
        env:
          FINMIND_TOKEN: ${{ secrets.FINMIND_TOKEN }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
        run: |
          python main.py
