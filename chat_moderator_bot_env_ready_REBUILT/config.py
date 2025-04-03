import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [123456789]
LOG_CHAT_ID = None

ALLOW_LINKS = False
MAX_MESSAGES = 5
FLOOD_SECONDS = 10
FLOOD_MUTE_DURATION = 60

WELCOME_MESSAGE = "Привет, {username}! Добро пожаловать. Ознакомься с правилами чата."

from banned_words import BANNED_WORDS
