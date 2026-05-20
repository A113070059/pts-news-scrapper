import os
import requests
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

# ==========================================
# 1. 設定參數區
# ==========================================
AIVEN_DB_URI = os.environ.get("DATABASE_URL")

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
    """初始化資料庫並處理欄位更新"""
    with conn.cursor() as cur:
        # 1. 建立包含 publish_date 欄位的新資料表 (針對全新安裝)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pts_news (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                url TEXT UNIQUE NOT NULL,
                publish_date VARCHAR(50), 
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. ⚠️ 神奇魔法：針對你已經建好的「舊資料表」，這行會自動幫你補上新欄位！
        cur.execute("""
            ALTER TABLE pts_news 
            ADD COLUMN IF NOT EXISTS publish_date VARCHAR(50);
        """)
    conn.commit()

def scrape_pts():
    """抓取公視新聞網的標題、連結與發布時間"""
    print(f"開始抓取: {TARGET_URL}")
    response = requests.get(TARGET_URL, headers=HEADERS)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    news_data = []

    # 針對公視新聞的結構：先找到新聞標題的 <h2>
    articles = soup.find_all("h2") 
    for article in articles:
        link_tag = article.find("a")
        
        if link_tag and link_tag.get("href"):
            title = link_tag.text.strip()
            url = link_tag.get("href")
            if not url.startswith("http"):
                url = "https://news.pts.org.tw" + url
            
            # --- 新增的抓取時間邏輯 ---
            # 新聞時間通常包在與標題同一區塊的 <time> 標籤內
            # 我們從標題 (h2) 往上找父層容器，再往下找時間標籤
            parent_div = article.find_parent()
            time_tag = parent_div.find("time") if parent_div else None
            
            # 取得時間文字，如果網頁改版導致沒抓到，則預設存成 "未標示"
            publish_date = time_tag.text.strip() if time_tag else "未標示"
            
            news_data.append((title, url, publish_date))
            
    return news_data

def save_to_aiven(conn, news_data):
    """將資料寫入資料庫，重複的網址會自動略過"""
    if not news_data:
        print("本次沒有抓到任何資料。")
        return

    # SQL 語法加入 publish_date，注意 VALUES 變成三個 %s
    insert_query = """
        INSERT INTO pts_news (title, url, publish_date) 
        VALUES %s 
        ON CONFLICT (url) DO NOTHING;
    """
    
    with conn.cursor() as cur:
        execute_values(cur, insert_query, news_data)
    conn.commit()
    print(f"資料庫寫入完成！成功抓取並檢查了 {len(news_data)} 筆新聞。")

# ==========================================
# 3. 主程式執行區塊
# ==========================================
def main():
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

if __name__ == "__main__":
    main()
