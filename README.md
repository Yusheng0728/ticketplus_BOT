# tix_dcbot

一個自動監控 TicketPlus（遠大）售票網站，並於 Discord 頻道發送票券釋出通知的機器人。

## 功能特色

- 定時檢查指定售票頁面是否有票券釋出
- 解析票區、價格、剩餘數量等資訊
- 於 Discord 頻道自動發送嵌入訊息通知
- 支援多個監控目標

## 安裝步驟

1. **安裝 Python 3.8+**
   - 建議使用 Python 3.8 以上版本

2. **安裝必要套件**
   ```bash
   pip install -r requirements.txt
   ```
   > 若無 requirements.txt，請安裝：
   > ```
   > pip install requests beautifulsoup4 discord.py
   > ```

3. **設定 config.json**
    詳見下方設定說明
   

4. **啟動機器人**
   - Windows 用戶可直接執行：
     ```
     run_tixbot.bat
     ```
   - 或用命令列執行：
     ```
     python tixbot.py
     ```

## 設定說明

- `discord_token`：你的 Discord Bot Token
- `channel_id`：要發送通知的頻道 ID
- `check_interval`：每幾秒檢查一次所有目標
- `target_check_delay`：每個目標檢查間隔（秒）
- `targets`：
  - `name`：活動名稱（可自訂）
  - `url`：售票頁面網址
  - `identifier_type`：票務平台類型（TicketPlus 請用 `ticketplus_api`）
  - `sale_url`：售票連結（可留空，預設同 `url`）

## 常見問題

- **403 Forbidden？**
  - 已自動加上 headers，若仍失敗可能是網站防爬蟲機制升級。
- **Discord 沒有收到通知？**
  - 請確認 Bot 已加入伺服器且有發訊息權限，`channel_id` 是否正確。

## 注意事項

- 請勿過於頻繁檢查，避免對票務網站造成壓力或被封鎖
- 僅供學術研究與個人用途，請勿用於商業或違法用途

---