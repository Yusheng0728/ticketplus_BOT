import logging
import asyncio
import requests
import urllib3
from bs4 import BeautifulSoup
import discord
from discord.ext import commands, tasks
import functools
import json
import os

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)


# --- 設定讀取 config.json ---
CONFIG_PATH = 'config.json'
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError('找不到 config.json，請建立設定檔！')
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

# 檢查 TicketPlus（API 與 HTML）
def sync_check_website(url, identifier_type, identifier_value):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    logging.info(f"正在檢查網址: {url} (類型: {identifier_type}, 值: {identifier_value})")
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()

        # --- TicketPlus JSON API 解析 ---
        if identifier_type == "ticketplus_api" and "application/json" in content_type:
            data = resp.json()
            seats_info = []
            ticket_areas = data.get("result", {}).get("ticketArea", [])
            for area in ticket_areas:
                if "完售" in area.get("status", "") or "soldout" in area.get("status", ""):
                    continue
                seats_info.append({
                    "area": area.get("ticketAreaName", ""),
                    "price": area.get("price", ""),
                    "remaining": area.get("count", 0)
                })
            logging.info(f"TicketPlus API解析結果: 有效票區數={len(seats_info)}")
            return {
                "type": "ticketplus",
                "event_name": "（API）" + url,
                "seats": seats_info
            }

        # --- TicketPlus HTML 解析 ---
        if "ticketplus.com.tw" in url:
            if "html" not in content_type:
                logging.warning(f"TicketPlus 內容非HTML: {url} (Content-Type: {content_type})")
                return False

            soup = BeautifulSoup(resp.text, 'html.parser')
            event_name_element = soup.find('div', class_='text-page-title')
            event_name_for_embed = event_name_element.text.strip() if event_name_element else "未知活動"

            seats_info = []
            for panel in soup.select('div.v-expansion-panel'):
                area_name = ""
                price = ""
                status = ""
                area_div = panel.select_one('div.d-flex.align-center.col.col-8')
                if area_div:
                    area_name_divs = area_div.find_all('div', recursive=False)
                    if len(area_name_divs) >= 2:
                        area_name = area_name_divs[1].get_text(strip=True)
                    else:
                        area_name = area_div.get_text(strip=True)
                price_div = panel.select_one('div.text-right.col.col-4')
                if price_div:
                    price = price_div.get_text(strip=True).replace("NT.", "").replace(",", "").strip()
                chip = panel.select_one('span.v-chip__content')
                if chip:
                    status = chip.get_text(strip=True)
                if "完售" in status or "售完" in status:
                    continue
                if area_name and price:
                    seats_info.append({
                        'area': area_name,
                        'price': price,
                        'remaining': status  # 遠大售票不會顯示剩餘數量，只顯示狀態
                    })
            logging.info(f"TicketPlus 解析結果: 活動='{event_name_for_embed}', 有效票區數={len(seats_info)}")
            return {'type': 'ticketplus', 'event_name': event_name_for_embed, 'seats': seats_info}

        return False

    except requests.exceptions.Timeout:
        logging.error(f"檢查網站超時: {url}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"檢查網站請求失敗 ({type(e).__name__}): {url}，錯誤: {e}")
        return False
    except Exception as e:
        logging.error(f"檢查網站 {url} 時發生非預期錯誤: {e}", exc_info=True)
        return False

# 發送 Discord 通知
async def send_discord_notification(bot, channel_id, message_content=None, embed_to_send=None):
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            if embed_to_send:
                await channel.send(embed=embed_to_send)
            if message_content:
                await channel.send(message_content)
            logging.info(f"已發送通知到頻道 {channel_id}")
        else:
            logging.error(f"找不到頻道 {channel_id}。請檢查頻道ID是否正確以及機器人是否有權限訪問該頻道。")
    except Exception as e:
        logging.error(f"發送 Discord 通知失敗: {e}", exc_info=True)

# Discord Bot 主體（只針對 TicketPlus）
class TicketMonitorBot(commands.Bot):
    def __init__(self, config_data):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config_data = config_data
        self.last_status = {}

    async def on_ready(self):
        logging.info(f"機器人已上線，帳號：{self.user}")
        if not self.monitor_websites.is_running():
            try:
                self.monitor_websites.start()
                logging.info("監控任務已啟動。")
            except Exception as e:
                logging.error(f"啟動監控任務失敗: {e}", exc_info=True)
        try:
            await send_discord_notification(
                self,
                self.config_data['channel_id'],
                message_content=f"TicketPlus 監控通知機器人已開啟！"
            )
        except Exception as e:
            logging.error(f"發送上線通知失敗: {e}", exc_info=True)

    @tasks.loop(seconds=60)
    async def monitor_websites(self):
        event_loop = asyncio.get_event_loop()
        for target in self.config_data['targets']:
            url = target['url']
            id_type_from_config = target.get('identifier_type', 'ticketplus_api')
            id_value_from_config = target.get('identifier_value', '')
            target_name_from_config = target.get('name', url)
            sale_url = target.get('sale_url') or url
            try:
                partial_sync_check = functools.partial(sync_check_website, url, id_type_from_config, id_value_from_config)
                current_result = await event_loop.run_in_executor(None, partial_sync_check)

                prev_available = self.last_status.get(url, False)
                current_is_available = False

                if isinstance(current_result, dict) and current_result['type'] == 'ticketplus':
                    available_seats = [seat for seat in current_result.get('seats', []) if str(seat.get('remaining', '')) not in ['完售', '售完', '0', '', None]]
                    current_is_available = bool(available_seats)
                    if current_is_available and not prev_available:
                        event_name_for_embed = target_name_from_config if target_name_from_config != url else current_result.get('event_name', "未知活動")
                        if len(event_name_for_embed) > 250:
                            event_name_for_embed = event_name_for_embed[:250] + "..."
                        embed = discord.Embed(
                            title=f"TicketPlus釋票通知: {event_name_for_embed}",
                            url=sale_url,
                            color=discord.Color.green()
                        )
                        msg_content = f"<@348193800579186690> 有票釋出！ ({event_name_for_embed})\n"
                        msg_content += f"網址: {sale_url}\n"
                        msg_content += "票區資訊：\n"
                        for seat in available_seats:
                            msg_content += f"{seat['area']} {seat['price']} 剩餘 {seat['remaining']}\n"
                        await send_discord_notification(self, self.config_data['channel_id'], message_content=msg_content, embed_to_send=embed)
                else:
                    logging.warning(f"檢查 {url} 時 sync_check_website 返回非預期結果或錯誤。")
                    current_is_available = False

                self.last_status[url] = current_is_available

            except Exception as e:
                logging.error(f"監控 {url} 迴圈內部發生錯誤: {e}", exc_info=True)
            await asyncio.sleep(self.config_data.get('target_check_delay', 2))

    @monitor_websites.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()
        interval = self.config_data.get('check_interval', 60)
        if self.monitor_websites.seconds != interval:
            self.monitor_websites.change_interval(seconds=interval)
        logging.info(f"監控任務前置作業完成，監控間隔設定為 {interval} 秒。")

if __name__ == "__main__":
    try:
        assert 'discord_token' in CONFIG, "設定缺少 'discord_token'"
        assert 'channel_id' in CONFIG, "設定缺少 'channel_id'"
        assert 'targets' in CONFIG and isinstance(CONFIG['targets'], list), "設定 'targets' 格式錯誤或不存在"
        assert 'check_interval' in CONFIG, "設定缺少 'check_interval'"
        if not isinstance(CONFIG['channel_id'], int):
            try:
                CONFIG['channel_id'] = int(CONFIG['channel_id'])
            except ValueError:
                raise ValueError("'channel_id' 必須是有效的數字。")

        bot = TicketMonitorBot(CONFIG)
        bot.run(CONFIG['discord_token'])
    except AssertionError as e:
        logging.critical(f"CONFIG 設定內容錯誤或缺少必要欄位: {e}")
    except discord.errors.LoginFailure:
        logging.critical("機器人登入失敗：無效的 Discord Token。請檢查您的 token 是否正確。")
    except discord.errors.PrivilegedIntentsRequired:
        logging.critical("機器人登入失敗：缺少必要的特權權限 (Privileged Intents)。")
    except Exception as e:
        logging.critical(f"機器人啟動失敗: {e}", exc_info=True)