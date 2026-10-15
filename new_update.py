import os
import sys
import time
from datetime import datetime, timedelta
import subprocess
import undetected_chromedriver as uc
import winsound
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import Select, WebDriverWait

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ---------------- НАСТРОЙКИ ----------------


# https://cologne.pasport.org.ua/solutions/e-queue   Koln

# URL = "https://berlin.pasport.org.ua/solutions/e-queue"  # Berlin
# https://munich.pasport.org.ua/solutions/e-queue

# URL = "https://munich.pasport.org.ua/solutions/e-queue"   #Munich

URL = "https://berlin.pasport.org.ua/solutions/e-queue"


CHECK_INTERVAL = 10 * 60  # 15 минут

SCREENSHOT_PATH = os.path.join(os.getcwd(), "slots_found.png")

UNKNOWN_SCREENSHOT_PATH = os.path.join(os.getcwd(), "unknown_result.png")
UNKNOWN_TEXT_PATH = os.path.join(os.getcwd(), "unknown_result.txt")

SERVICE_VALUE = "4"  # Закордонний паспорт та (або) ID-картка

NO_SLOTS_KEYWORDS = [
    "Наразі всі місця зайняті",
    "на даний момент всі місця зайняті",
    "Спробуйте записатись пізніше",
    "Будь ласка, спробуйте в інший час або день",
    "Кількість талонів обмежена пропускною здатністю центру"
]

def load_dotenv(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Підвантажує KEY=VALUE з .env, не перезаписуючи вже задані змінні середовища."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ------------------------------------------


def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def beep_found():
    for _ in range(5):
        winsound.Beep(2000, 500)
        time.sleep(0.3)


def beep_quiet():
    winsound.Beep(800, 300)

def send_telegram_notification(message, photo_path=None):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        log("❌ Токен Telegram бота не настроен. Уведомление не отправлено.")
        return
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        log("❌ ID чата Telegram не настроен. Уведомление не отправлено.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        if photo_path and os.path.exists(photo_path):
            log(f"Попытка отправить фото в Telegram: {photo_path}")
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                photo_response = requests.post(photo_url, data={"chat_id": TELEGRAM_CHAT_ID}, files=files)
                if photo_response.ok:
                    log("✅ Фото успешно отправлено в Telegram.")
                else:
                    log(f"❌ Ошибка при отправке фото в Telegram: {photo_response.status_code} - {photo_response.text}")
            time.sleep(1) # Задержка, чтобы сообщение пришло после фото

        log(f"Попытка отправить текстовое уведомление в Telegram (чат: {TELEGRAM_CHAT_ID})...")
        response = requests.post(url, json=payload)
        if response.ok:
            log("✅ Уведомление успешно отправлено в Telegram.")
        else:
            log(f"❌ Ошибка при отправке уведомления в Telegram: {response.status_code} - {response.text}")
    except Exception as e:
        log(f"❌ Ошибка отправки в Telegram: {e}")


def check_slots():
    log("Перевіряю наявність місць...")
    # send_telegram_notification(f"<b>Починаю перевірку наявності місць на {URL}...</b>")

    try:
        driver = create_driver()
    except Exception as e:
        log(f"❌ Chrome не запущено: {e}")
        return False

    try:
        # Прогрев (важно для Cloudflare)
        driver.get("https://www.google.com")
        time.sleep(10)

        log(f"Отправляю запрос на {URL}...") # Закомментируйте эту строку, чтобы отключить это сообщение
        driver.get(URL)
        log("Чекаю Cloudflare...")

        WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Ждем, пока на странице появится осмысленный контент
        log("Чекаю завантаження основного контенту...")
        def content_loaded(driver):
            text = driver.find_element(By.TAG_NAME, "body").text
            # Проверяем наличие ключевых слов отсутствия мест или достаточную длину текста
            return any(k in text for k in NO_SLOTS_KEYWORDS) or len(text) > 500

        WebDriverWait(driver, 60).until(content_loaded)

        # Повідомлення про відсутність місць з'являється лише після вибору послуги
        log("Обираю послугу...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "service"))
        )
        Select(driver.find_element(By.ID, "service")).select_by_value(SERVICE_VALUE)

        def result_ready(driver):
            text = driver.find_element(By.TAG_NAME, "body").text
            if any(k in text for k in NO_SLOTS_KEYWORDS):
                return "no_slots"
            dates = driver.find_elements(By.CSS_SELECTOR, "#date option")
            if any(o.get_attribute("value") for o in dates):
                return "slots"
            return False

        try:
            result = WebDriverWait(driver, 40).until(result_ready)
            if result == "slots":
                # Захист від хибного спрацювання: option у #date можуть бути
                # лишками до того, як сайт підвантажив відповідь для обраної послуги.
                # Підтверджуємо, лише якщо стан стабільний кілька перевірок поспіль.
                for _ in range(3):
                    time.sleep(3)
                    recheck = result_ready(driver)
                    if recheck != "slots":
                        result = recheck or "no_slots"
                        log("ℹ️ Початковий «позитив» не підтвердився — місць немає")
                        break
        except TimeoutException:
            log("⚠️ Не вдалося визначити результат після вибору послуги")
            try:
                driver.save_screenshot(UNKNOWN_SCREENSHOT_PATH)
                with open(UNKNOWN_TEXT_PATH, "w", encoding="utf-8") as f:
                    f.write(driver.find_element(By.TAG_NAME, "body").text)
                log(f"Збережено для діагностики: {UNKNOWN_SCREENSHOT_PATH}, {UNKNOWN_TEXT_PATH}")
            except Exception as e:
                log(f"⚠️ Не вдалося зберегти діагностику: {e}")
            return False

        # 🔍 Проверка отсутствия мест
        if result == "no_slots":
            log("❌ Місць немає")
            # send_telegram_notification(f"<b>Місць немає</b>")
            beep_quiet()
            return False

        log("✅ МОЖЛИВО Є ВІЛЬНІ МІСЦЯ!")
        driver.save_screenshot(SCREENSHOT_PATH)
        beep_found()
        send_telegram_notification(f"<b>✅ Знайдено можливі вільні місця на {URL}!</b>\nПеревір негайно!", photo_path=SCREENSHOT_PATH)
        return True

    except Exception as e:
        log(f"⚠️ Помилка: {e}")
        return False

    finally:
        try:
            driver.quit()
        except:
            pass


def countdown(next_check_time):
    while True:
        now = datetime.now()
        remaining = (next_check_time - now).total_seconds()

        if remaining <= 0:
            break

        mins, secs = divmod(int(remaining), 60)
        print(f"\r⏳ До наступної перевірки: {mins:02d}:{secs:02d}", end="", flush=True)

        time.sleep(1)

    print("\r" + " " * 50 + "\r", end="")

def get_chrome_major_version(chrome_path):
    """Мажорна версія встановленого Chrome, щоб uc завантажив сумісний драйвер."""
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Item '{chrome_path}').VersionInfo.ProductVersion"],
            text=True, timeout=15,
        ).strip()
        return int(out.split(".")[0])
    except Exception as e:
        log(f"⚠️ Не вдалося визначити версію Chrome: {e}")
        return None


def create_driver():
    options = uc.ChromeOptions()
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    options.binary_location = chrome_path

    options.add_argument("--window-size=1280,800")
    options.add_argument("--lang=uk-UA")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    return uc.Chrome(options=options, version_main=get_chrome_major_version(chrome_path))

def main():
    print("=" * 60)
    print("ДП Документ Берлин мониторинг — моніторинг")
    print(f"Перевірка кожні {CHECK_INTERVAL // 60} хвилин")
    print(f"URL: {URL}")
    print("=" * 60)

    while True:
        try:
            found = check_slots()

            if found:
                log("🚨 ЗАЙДИ НА САЙТ НЕГАЙНО!")

        except KeyboardInterrupt:
            print("\nЗупинено.")
            sys.exit(0)

        except Exception as e:
            log(f"❗ Критична помилка: {e}")

        # 🔥 вычисляем точное время следующей проверки
        next_check_time = datetime.now() + timedelta(seconds=CHECK_INTERVAL)

        log(f"Наступна перевірка о {next_check_time.strftime('%H:%M:%S')}")
        print("-" * 60)

        # ⏳ таймер с учетом сна ПК
        countdown(next_check_time)


if __name__ == "__main__":
    main()
