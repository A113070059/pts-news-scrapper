import requests
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import execute_values
import time
import schedule

# ==========================================
# 1. 設定參數區
# ==========================================
AIVEN_DB_URI = "postgres://avnadmin:AVNS_mAltEjJJkalIiJLiWbz@pg-e265b25-databas-class-1.h.aivencloud.com:24297/defaultdb?sslmode=require"
TARGET_URL = "https://news.pts.org.tw/category/1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ==========================================
# 2. 資料庫與爬蟲函數 (維持不變)
# ==========================================
def init_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pts_news (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                url TEXT UNIQUE NOT NULL,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.commit()

def scrape_pts():
    response = requests.get(TARGET_URL, headers=HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    news_data = []

    articles = soup.find_all("h2") 
    for article in articles:
        link_tag = article.find("a")
        if link_tag and link_tag.get("href"):
            title = link_tag.text.strip()
            url = link_tag.get("href")
            if not url.startswith("http"):
                url = "https://news.pts.org.tw" + url
            news_data.append((title, url))
            
    return news_data

def save_to_aiven(conn, news_data):
    if not news_data:
        return
    insert_query = """
        INSERT INTO pts_news (title, url) 
        VALUES %s 
        ON CONFLICT (url) DO NOTHING;
    """
    with conn.cursor() as cur:
        execute_values(cur, insert_query, news_data)
    conn.commit()
    print(f"成功抓取並檢查了 {len(news_data)} 筆新聞。")

# ==========================================
# 3. 定義排程任務
# ==========================================
def job():
    """每次排程時間到，就會執行這個任務"""
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{current_time}] 開始執行自動爬蟲...")
    
    try:
        # 每次執行都建立新的連線，確保穩定度
        connection = psycopg2.connect(AIVEN_DB_URI)
        init_db(connection)
        
        scraped_data = scrape_pts()
        save_to_aiven(connection, scraped_data)
        
    except Exception as e:
        print(f"發生錯誤: {e}")
    finally:
        if 'connection' in locals() and connection:
            connection.close()
            print("任務結束，資料庫連線已關閉。等待下一次執行...\n" + "-"*40)

# ==========================================
# 4. 啟動排程器
# ==========================================
if __name__ == "__main__":
    # 程式一啟動先強制執行一次，不用乾等
    job()
    
    # 設定排程：這裡設定每 30 分鐘執行一次
    # 你也可以改成 schedule.every(1).hours.do(job) 變成每小時一次
    schedule.every(30).minutes.do(job)
    
    print("排程已啟動！請保持這個終端機開啟，按下 Ctrl+C 可強制停止程式。")
    
    # 建立一個無窮迴圈，讓程式永遠不會結束，並持續檢查時間
    while True:
        schedule.run_pending()
        time.sleep(1)