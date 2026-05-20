import os
import requests
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

# ==========================================
# 1. 設定參數區 (修改為讀取環境變數)
# ==========================================
# 這裡不再寫死密碼，而是從作業系統（或 GitHub Actions）的環境變數讀取
AIVEN_DB_URI = os.environ.get("DATABASE_URL")

# 加上檢查機制：如果 GitHub 那邊忘記設定 Secret，程式會立刻停止並印出錯誤
if not AIVEN_DB_URI:
    raise ValueError("找不到 DATABASE_URL 環境變數，請確認是否已在 GitHub Secrets 中設定！")

TARGET_URL = "https://news.pts.org.tw/category/1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ==========================================
# 2. 資料庫與爬蟲函數
# ==========================================
def init_db(conn):
    """建立新聞資料表（如果還不存在的話）"""
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
    """抓取公視新聞網的標題與連結"""
    print(f"開始抓取: {TARGET_URL}")
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
    """將資料寫入資料庫，重複的網址會自動略過"""
    if not news_data:
        print("本次沒有抓到任何資料。")
        return

    insert_query = """
        INSERT INTO pts_news (title, url) 
        VALUES %s 
        ON CONFLICT (url) DO NOTHING;
    """
    
    with conn.cursor() as cur:
        execute_values(cur, insert_query, news_data)
    conn.commit()
    print(f"資料庫寫入完成！成功抓取並檢查了 {len(news_data)} 筆新聞。")

# ==========================================
# 3. 主程式執行區塊 (單次執行)
# ==========================================
def main():
    # 紀錄執行當下的時間，方便在 GitHub Actions 的 Log 裡面查看
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{current_time}] 開始執行爬蟲任務...")
    
    try:
        connection = psycopg2.connect(AIVEN_DB_URI)
        init_db(connection)
        
        scraped_data = scrape_pts()
        save_to_aiven(connection, scraped_data)
        
    except Exception as e:
        print(f"發生錯誤: {e}")
    finally:
        if 'connection' in locals() and connection:
            connection.close()
            print("任務結束，資料庫連線已關閉。")

# 當程式被執行時，只會呼叫 main() 跑一次就結束
if __name__ == "__main__":
    main()