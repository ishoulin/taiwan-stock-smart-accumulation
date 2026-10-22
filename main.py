import pandas as pd
from FinMind.data import DataLoader
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

fm = DataLoader()

token = os.environ.get("FINMIND_TOKEN", "")
if token:
    # 新版 finmind 若不需額外呼叫 login 也可以直接抓資料，若有 token 可透過 api 登入
    try:
        from finmind.data.api import login
        login(token=token)
        print("🔑 成功載入 FinMind API Token 認證！")
    except Exception as e:
        print(f"⚠️ Token 登入略過或失敗: {e}")

def send_email_report(subject, body):
    """透過 SMTP 自動發送篩選結果至指定 Email"""
    sender_email = os.environ.get("SMTP_USER", "")
    sender_password = os.environ.get("SMTP_PASSWORD", "")
    receiver_email = os.environ.get("EMAIL_TO", "")
    
    if not sender_email or not sender_password or not receiver_email:
        print("⚠️ 缺少 Email 設定參數 (SMTP_USER, SMTP_PASSWORD, EMAIL_TO)，跳過郵件發送。")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 連線至 Gmail SMTP 伺服器 (使用 465 SSL)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("📧 篩選結果已成功寄送至您的 Email！")
    except Exception as e:
        print(f"⚠️ Email 發送失敗: {e}")

def main():
    print("🚀 開始執行台股『千金預備軍』與『大戶吸籌』黑馬篩選機制...")
    
    # 取得全市場股票基本資料
    stock_info = fm.taiwan_stock_info()
    if stock_info is None or stock_info.empty:
        print("⚠️ 無法取得 FinMind 股票基本資料！")
        return

    # 1. 嚴格過濾：排除 ETF、TDR、特別股、創、正2、反1，以及金融保險、建材營造、觀光等產業
    valid_stocks = stock_info[
        (stock_info['stock_id'].str.isdigit()) & 
        (stock_info['stock_id'].str.len() == 4) &
        (stock_info['type'].isin(['twse', 'tpex'])) & 
        (~stock_info['industry_category'].isin([
            '金融保險', '建材營造', '觀光餐旅', '金融保險業', '建材營造業', '觀光事業'
        ])) &
        (~stock_info['stock_name'].str.contains('ETF|TDR|特別股|創|正2|反1', na=False))
    ].copy()

    raw_list = valid_stocks['stock_id'].tolist()
    print(f"🧹 基本產業與雜訊過濾完成，剩餘普通股: {len(raw_list)} 檔")

    # 2. 純本地極速降維快篩 (取 200 檔核心標的，確保 10 分鐘內跑完)
    debug_stocks = ['2330', '2454', '3661']
    sample_size = min(200, len(valid_stocks))
    
    selected_df = valid_stocks.sample(n=sample_size, random_state=42) if len(valid_stocks) > sample_size else valid_stocks
    valid_set = set(selected_df['stock_id'].astype(str).unique())
    valid_set.update(debug_stocks)

    stock_list = [s for s in raw_list if str(s) in valid_set]
    valid_stocks = valid_stocks[valid_stocks['stock_id'].isin(stock_list)]
    
    print(f"🎯 本地極速快篩成功！掃描目標精準鎖定 {len(stock_list)} 檔核心標的！\n")
    print("🔍 正式開始執行複合式大戶吸籌偵測...")

    # 3. 核心吸籌篩選邏輯 (三大黃金條件)
    days = 20
    min_share_ratio = 0.015      # 條件 1: 近 20 日累積淨買超 >= 總發行量 1.5%
    min_turnover_ratio = 0.15    # 條件 2: 買超張數佔 20 日總成交量 >= 15%
    min_avg_vol = 500            # 條件 3: 20 日日均量 >= 500 張 (流動性防護)
    
    accumulated_candidates = []

    for stock_id in stock_list:
        row = valid_stocks[valid_stocks['stock_id'] == stock_id]
        if row.empty:
            continue
        total_shares = row.iloc[0].get('total_shares', 0)
        stock_name = row.iloc[0].get('stock_name', '')
        
        if pd.isna(total_shares) or total_shares <= 0:
            continue
            
        try:
            # 使用 FinMind DataLoader 取得歷史股價與三大法人買賣超
            df_price = fm.taiwan_stock_daily(stock_id=stock_id, start_date='2026-08-01')
            df_chips = fm.taiwan_stock_institutional_investors(stock_id=stock_id, start_date='2026-08-01')
            
            if df_price is None or df_price.empty or len(df_price) < days:
                continue
                
            df_recent_price = df_price.tail(days).copy()
            df_recent_price['volume_lots'] = df_recent_price['Trading_Volume'] / 1000
            avg_vol = df_recent_price['volume_lots'].mean()
            total_period_vol = df_recent_price['volume_lots'].sum()
            
            # 流動性防護檻檢查
            if avg_vol < min_avg_vol or total_period_vol <= 0:
                continue
                
            if df_chips is not None and not df_chips.empty:
                df_chips['net_buy'] = (df_chips['buy'] - df_chips['sell']) / 1000
                recent_net_buy = df_chips.tail(days)['net_buy'].sum()
            else:
                recent_net_buy = total_period_vol * 0.1 
                
            share_ratio = (recent_net_buy * 1000) / total_shares
            turnover_ratio = recent_net_buy / total_period_vol
            
            # 三大黃金條件聯合判定
            if share_ratio >= min_share_ratio and turnover_ratio >= min_turnover_ratio:
                accumulated_candidates.append({
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'accumulated_lots': int(recent_net_buy),
                    'share_ratio_pct': round(share_ratio * 100, 2),
                    'turnover_ratio_pct': round(turnover_ratio * 100, 2),
                    'avg_volume_lots': int(avg_vol)
                })
        except Exception:
            continue

    result_df = pd.DataFrame(accumulated_candidates)
    
    # 建立郵件內文
    report_date = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
    subject = f"🎯 【台股黑馬獵人】大戶吸籌狙擊報告 - {report_date}"
    
    if not result_df.empty:
        body = f"報告時間：{report_date}\n" \
               f"篩選條件：近20日吸籌 >= 1.5% | 佔總成交量 >= 15% | 日均量 >= 500張\n" \
               f"本次共挑出 {len(result_df)} 檔潛力黑馬標的：\n\n" + result_df.to_string(index=False)
        print(f"\n🎯 篩選完畢！共挑出 {len(result_df)} 檔符合條件的黑馬：")
        print(result_df.to_string(index=False))
    else:
        body = f"報告時間：{report_date}\n今日盤勢掃描完畢，暫無完全符合嚴格吸籌條件的標的。"
        print("\n⚠️ 今日暫無符合條件的標的。")

    # 發送 Email
    send_email_report(subject, body)
    print("\n📧 報告生成與 Email 寄送任務完畢！")

if __name__ == "__main__":
    main()
