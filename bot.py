import asyncio
import time
from collections import defaultdict
from datetime import timedelta, datetime
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatPermissions

from banned_words import BANNED_WORDS
from config import BOT_TOKEN, ADMIN_IDS, LOG_CHAT_ID, MAX_MESSAGES, FLOOD_SECONDS, FLOOD_MUTE_DURATION, WELCOME_MESSAGE
from filters import has_profanity, has_link

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
flood_control = defaultdict(list)

def parse_duration(duration_str):
    units = {"s": 1, "m": 60, "h": 3600}
    import re
    match = re.match(r"(\d+)([smh])", duration_str)
    if not match:
        return None
    value, unit = match.groups()
    return int(value) * units[unit]

async def log_action(text):
    if LOG_CHAT_ID:
        await bot.send_message(LOG_CHAT_ID, text)

@dp.message()
async def message_filter(message: types.Message):
    if not message.text:
        return

    uid = message.from_user.id
    now = time.time()
    flood_control[uid] = [t for t in flood_control[uid] if now - t < FLOOD_SECONDS]
    flood_control[uid].append(now)

    print(f"[Флуд] {message.from_user.full_name} → {len(flood_control[uid])} сообщений за {FLOOD_SECONDS} сек")

    if len(flood_control[uid]) > MAX_MESSAGES:
        print(f"[Мут] {message.from_user.full_name} — мутим за флуд ({len(flood_control[uid])} сообщений)")
        
        until = datetime.now() + timedelta(seconds=FLOOD_MUTE_DURATION)
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=uid,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        await message.reply("⛔ Флуд! Пользователь временно замучен.")
        await log_action(f"Мут за флуд: {message.from_user.full_name}")
        flood_control[uid] = []
        return

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    is_admin = member.status in ("administrator", "creator")

    if has_profanity(message.text):
        await message.delete()
        await log_action(f"Удалено сообщение от {message.from_user.full_name}: мат")

    elif has_link(message.text) and not is_admin:
        await message.delete()
        await log_action(f"Удалено сообщение от {message.from_user.full_name}: ссылка")


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.chat_member()
async def on_user_join(event: types.ChatMemberUpdated):
    if event.new_chat_member.status != ChatMemberStatus.MEMBER:
        return

    user = event.new_chat_member.user
    name = user.full_name.strip().lower()
    username = (user.username or "").lower()

    # 1. Кик за пустое имя
    if not name:
        await bot.kick_chat_member(event.chat.id, user.id)
        await log_action("🚫 Кик при входе: пустое имя")
        return

    # 2. Кик за отсутствие аватарки
    try:
        profile_photos = await bot.get_user_profile_photos(user.id)
        if profile_photos.total_count == 0:
            await bot.kick_chat_member(event.chat.id, user.id)
            await log_action(f"🚫 Кик при входе: без аватарки — {user.full_name}")
            return
    except Exception as e:
        print(f"⚠️ Ошибка при получении аватарки: {e}")

    # 3. Кик за мат в имени
    if any(bad_word in name for bad_word in BANNED_WORDS):
        await bot.kick_chat_member(event.chat.id, user.id)
        await log_action(f"🚫 Кик при входе: имя содержало мат — {user.full_name}")
        return

    # 4. Кик за слово "bot" в имени или username
    if "bot" in name or "bot" in username:
        await bot.kick_chat_member(event.chat.id, user.id)
        await log_action(f"🚫 Кик при входе: подозрение на бота — {user.full_name}")
        return

    # 5. Мут подозрительного "ботоподобного" пользователя
    if not user.username and any(char.isdigit() for char in name):
        until = datetime.now() + timedelta(minutes=30)
        await bot.restrict_chat_member(
            chat_id=event.chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        await log_action(f"🤐 Мут при входе: ботоподобный аккаунт — {user.full_name}")
        return

    # ✅ Приветствие с кнопкой "Правила"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Правила", callback_data="show_rules")]
    ])
    await bot.send_message(
        event.chat.id,
        WELCOME_MESSAGE.format(username=user.full_name),
        reply_markup=keyboard
    )




@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.reply_to_message:
        await message.reply("Нужно ответить на сообщение нарушителя.")
        return
    await message.chat.ban_user(message.reply_to_message.from_user.id)
    await message.reply("Пользователь забанен.")
    await log_action(f"Бан: {message.reply_to_message.from_user.full_name}")

@dp.message(Command("kick"))
async def kick_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(args) == 2:
        user_ref = args[1]
        try:
            if user_ref.startswith("@"):
                member = await bot.get_chat_member(message.chat.id, user_ref)
            else:
                member = await bot.get_chat_member(message.chat.id, int(user_ref))
            target = member.user
        except:
            await message.reply("Не удалось найти пользователя.")
            return
    else:
        await message.reply("Формат: /kick @username или /kick по реплаю")
        return

    await message.chat.kick(target.id)
    await message.reply(f"Пользователь {target.full_name} кикнут.")
    await log_action(f"Кик: {target.full_name}")

@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()

    if len(args) == 2 and message.reply_to_message:
        target = message.reply_to_message.from_user
        duration = parse_duration(args[1])
    elif len(args) == 3:
        user_ref = args[1]
        duration = parse_duration(args[2])
        if not duration:
            await message.reply("Неверный формат времени. Примеры: 10s, 5m, 1h")
            return
        try:
            if user_ref.startswith("@"):
                member = await bot.get_chat_member(message.chat.id, user_ref)
            else:
                member = await bot.get_chat_member(message.chat.id, int(user_ref))
            target = member.user
        except:
            await message.reply("Не удалось найти пользователя.")
            return
    else:
        await message.reply("Формат: /mute @username 5m или /mute 10m (по реплаю)")
        return

    until = datetime.now() + timedelta(seconds=duration)
    await bot.restrict_chat_member(
        chat_id=message.chat.id,
        user_id=target.id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until
    )
    await message.reply(f"Пользователь {target.full_name} замучен на {args[-1]}")
    await log_action(f"Мут: {target.full_name} на {args[-1]}")

@dp.message(Command("rules"))
async def send_rules(message: types.Message):
    with open("rules.txt", "r", encoding="utf-8") as f:
        await message.answer(f.read())

@dp.message(Command("settings"))
async def show_settings(message: types.Message):
    await message.reply(f"Фильтр мата: ВКЛ\nСсылки запрещены: {'Да' if not os.getenv('ALLOW_LINKS', 'False') == 'True' else 'Нет'}")
@dp.callback_query(lambda c: c.data == "show_rules")
async def show_rules_callback(callback: types.CallbackQuery):
    with open("rules.txt", "r", encoding="utf-8") as f:
        rules_text = f.read()
    await callback.message.answer(rules_text)
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔁 Перезапуск через 5 секунд...")
            time.sleep(5)



