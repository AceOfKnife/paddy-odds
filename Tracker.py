from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from collections import deque
from datetime import datetime
import csv
import time as t
from telegram import Bot
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import asyncio

def getDriver(url):
    # Set up the Firefox Profile
    profile = FirefoxProfile()

    # Set custom headers from your regular browser
    profile.set_preference("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0")
    profile.set_preference("network.http.accept", "*/*")
    profile.set_preference("network.http.accept-language", "en-US,en;q=0.5")
    profile.set_preference("network.http.accept-encoding", "gzip, deflate, br, zstd")

    # Disable WebDriver flag to avoid detection
    profile.set_preference("dom.webdriver.enabled", False)

    options = Options()
    options.profile = profile
    options.add_argument("--headless")

    service = Service("/usr/local/bin/geckodriver")

    driver = webdriver.Firefox(service=service, options=options)
    driver.get(url)
    return driver

def getUrls():
    driver = getDriver("https://www.paddypower.com/greyhound-racing?tab=meetings")
    urls = {}

    try:
        allRegions = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "region-group__card-item"))
        )
    except Exception as e:
        print("❌ Could not find region group cards:", e)
        driver.quit()
        return []

    regions = {}
    for region in allRegions:
        try:
            location = region.find_element(
                By.CSS_SELECTOR, ".meeting-card-item__title.accordion__title"
            ).text.strip()
            regions[location] = region
        except Exception as e:
            print("⚠️ Error parsing region:", e)

    for location in regions:

        try:
            links = regions[location].find_elements(By.TAG_NAME, "a")
        except Exception as e:
            print(f"⚠️ Couldn't extract links for {location}:", e)
            continue
        for link in links:
            try:
                span = link.find_element(By.TAG_NAME, "span")
                time = span.get_attribute("textContent").replace(" ", "")
                href = link.get_attribute("href").replace(" ", "")
                urls[(location, time)] = href
            except Exception as e:
                continue  # Skip anchor if it doesn't contain a span with time
    driver.quit()
    return urls

async def notifyOddsChange(bot, message, chat_id):
    await bot.send_message(chat_id=chat_id, text=message)

async def main():
    BOT_TOKEN = ""
    CHAT_ID = ""
    bot = Bot(token=BOT_TOKEN)
    dogs = []
    with open('signals.csv', newline='\n') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            dog, location, time_str = row
            dogs.append((dog.strip(), location.strip(), time_str.strip()))
    urls = getUrls()
    curOdds = {}
    drivers = deque([])
    for dog, location, time in dogs:
        try:
            curOdds[dog] = "SP"
            driver = getDriver(urls[(location, time)])
            runners = WebDriverWait(driver, 30).until(EC.presence_of_all_elements_located((By.CLASS_NAME, "card-item__runner-line")))
            odds = None
            for runner in runners:
                dogName = runner.find_element(By.CSS_SELECTOR, ".racing-runner__selection-name").text.strip()
                if dogName == dog:
                    odds = runner.find_element(By.CSS_SELECTOR, ".btn-odds__label")
            if not odds:
                raise Exception("Dog not found")
            drivers.append((dog, location, datetime.strptime(time, "%H:%M").time(), odds, driver))
        except Exception as e:
            print(f"Could not find odds for {dog}, {location}, {time}:", e)

    while True:
        timeNow = datetime.now().time()

        for _ in range(len(drivers)):
            dog, location, time, odds, driver = drivers.popleft()
            try:
                odd = odds.text
                if odd != curOdds[dog]:
                    # print(f"Odds for {dog}: {location} {time.strftime('%H:%M')} changed from {curOdds[dog]} to {odd}")
                    await notifyOddsChange(bot, f"{dog} {location} {time}: {curOdds[dog]} -> {odd}", CHAT_ID)
                    curOdds[dog] = odd
                if time > timeNow and curOdds[dog] == "SP":
                    drivers.append((dog, location, time, odds, driver))
                else:
                    driver.quit()
            except Exception as e:
                print(f"Failed to get the odds for {dog}:", e)
                driver.quit()

        if not drivers:
            break
        t.sleep(60)

    while drivers:
        _, _, _, _, driver = drivers.popleft()
        driver.quit()

if __name__ == "__main__":
    asyncio.run(main())