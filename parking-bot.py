import asyncio
import requests
import utils
import os
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Get authorized user IDs from environment variable
AUTHORIZED_USER_IDS = os.getenv("AUTHORIZED_USER_IDS", "").split(",")


class CarSearchResult:
    def __init__(self, car_number: str, enter_date: str, park_time: str):
        self.car_number = car_number
        self.enter_date = enter_date
        self.park_time = park_time


class AsyncCarParkingManager:
    def __init__(self):
        self.base_url = os.getenv("PARKING_BASE_URL")
        self.username = os.getenv("PARKING_USERNAME")
        self.password = os.getenv("PARKING_PASSWORD")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.discount_options = {
            0: {"name": "방문권", "time": 75, "description": "1시간15분무료"},
            1: {"name": "15분주차권", "time": 15, "description": "1000원"},
            2: {"name": "30분주차권", "time": 30, "description": "2000원"},
            3: {"name": "1시간주차권", "time": 60, "description": "4000원"},
            4: {"name": "당일권", "time": 1440, "description": "15,000원"},
            5: {"name": "24시간권", "time": 1440, "description": "30,000원"}
        }

    async def login(self):
        try:
            login_url = f"{self.base_url}/User/Login.aspx"
            response = self.session.get(login_url)
            soup = BeautifulSoup(response.text, 'html.parser')

            viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
            viewstategenerator = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value']
            eventvalidation = soup.find('input', {'id': '__EVENTVALIDATION'})['value']

            login_data = {
                '__VIEWSTATE': viewstate,
                '__VIEWSTATEGENERATOR': viewstategenerator,
                '__EVENTVALIDATION': eventvalidation,
                'ctl00$cph_body$userId': self.username,
                'ctl00$cph_body$userPw': self.password,
                'ctl00$cph_body$hiddenPw': '',
                'ctl00$cph_body$btnLogin': ''
            }

            response = self.session.post(login_url, data=login_data)
            return '로그인' not in response.text
        except Exception as e:
            return False

    async def apply_discount(self, car_number, discount_index):
        try:
            url = f"{self.base_url}/Car/SearchDetail.aspx?carno={car_number}"

            # load page
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')

            # get hidden values
            viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
            viewstategenerator = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value']
            eventvalidation = soup.find('input', {'id': '__EVENTVALIDATION'})['value']

            # create post data
            post_data = {
                '__EVENTTARGET': f'ctl00$cph_body$rptList$ctl{discount_index:02d}$btnIns',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': viewstate,
                '__VIEWSTATEGENERATOR': viewstategenerator,
                '__EVENTVALIDATION': eventvalidation,
                'ctl00$cph_body$Text1': ''
            }

            # post
            response = self.session.post(url, data=post_data)
            return response.status_code == 200

        except Exception as e:
            print(f"할인 적용 중 오류 발생: {e}")
            return False

    async def check_already_applied_discount(self, car_number):
        try:
            url = f"{self.base_url}/Car/SearchDetail.aspx?carno={car_number}"
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # find discount table tbody
            discount_table = soup.find('table', {'class': 'table'})
            if not discount_table:
                return False
                
            tbody = discount_table.find('tbody')
            if not tbody:
                return False
                
            # if tbody has tr, then discount is already applied
            discount_rows = tbody.find_all('tr')
            return len(discount_rows) > 0
            
        except Exception as e:
            print(f"할인 내역 확인 중 오류 발생: {e}")
            return False

    async def get_car_info(self, car_number):
        if not await self.login():
            return "주차 정산 시스템에 로그인 할 수 없습니다."

        try:
            # find cars
            url = f"{self.base_url}/Car/SearchResult.aspx?carno={car_number}"
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')

            cars = []
            car_cards = soup.find_all('div', class_='card')

            for card in car_cards:
                try:
                    car_info = {
                        'car_number': card.find('h4', class_='card-title').text.strip(),
                        'enter_date': card.find('span', class_='control-label').text.replace('입차일자: ', ''),
                        'park_time': card.find_all('span', class_='control-label')[1].text.replace('주차시간: ', ''),
                    }
                    cars.append(CarSearchResult(**car_info))
                except Exception as e:
                    print(f"차량 카드 파싱 중 오류: {e}")
                    continue

            # if cars more than 2 or 0
            if len(cars) != 1:
                return "차량이 존재하지 않거나 / 동일한 번호가 존재합니다."

            # access car detail
            car_no = cars[0].car_number
            enter_date = cars[0].enter_date
            park_time = cars[0].park_time

            # check already applied discounts
            if await self.check_already_applied_discount(car_no):
                return f"{car_no}의 차량번호는 이미 할인이 적용되었습니다."

            # calc best discount
            recommended_discounts = utils.get_best_discount(park_time, enter_date)

            info = {
                'car_number': car_no,
                'parking_time': park_time,
                'applied_coupons': [],
            }

            # long time parking case
            if len(recommended_discounts) == 0:
                return "자동으로 주차 정산을 할 수 없는 차량입니다."

            # apply coupons
            for coupon in recommended_discounts:
                try:
                    if await self.apply_discount(car_no, coupon):
                        info['applied_coupons'].append(self.discount_options[coupon]['name'])
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"할인권 적용 실패 - {coupon['name']}: {str(e)}")
            return info
        except Exception as e:
            return f"조회 중 오류 발생: {e}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is authorized
    user_id = str(update.effective_user.id)
    if user_id not in AUTHORIZED_USER_IDS:
        await update.message.reply_text("You do not have permission.")
        return
        
    await update.message.reply_text(
        "/park [차량번호] 로 주차 정산을 할 수 있습니다.\n"
    )

async def parking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is authorized
    user_id = str(update.effective_user.id)
    if user_id not in AUTHORIZED_USER_IDS:
        await update.message.reply_text("You do not have permission.")
        return
        
    if not context.args:
        await update.message.reply_text(
            "/park [차량번호] 로 주차 정산을 할 수 있습니다.\n"
        )
        return

    # get args
    car_number = context.args[0]

    # send reply msg
    msg = await update.message.reply_text(f"{car_number}의 차량번호를 확인 중입니다....")
    info = await parking_manager.get_car_info(car_number)

    if isinstance(info, dict):
        # success
        response = (
            f"차량번호: {info['car_number']}\n"
            f"주차시간: {info['parking_time']}\n"
            f"사용 주차권: {', '.join(info['applied_coupons'])}"
        )
    else:
        # error
        response = info

    # update msg
    await msg.edit_text(response)

# parking management instance
parking_manager = AsyncCarParkingManager()

# telegram init
token = os.getenv("TELEGRAM_BOT_TOKEN")
app = ApplicationBuilder().token(token).build()

# handler
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("park", parking))

# run bot
app.run_polling()
