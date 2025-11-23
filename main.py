import asyncio
from datetime import datetime
import requests
import json
import os
import logging
import sqlite3
from lm_types import ModelResponse, UserData
from dotenv import load_dotenv
from telebot.types import Message
from telebot.async_telebot import AsyncTeleBot

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(module)s - %(levelname)s - %(message)s"
)

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")

if API_TOKEN is None:
    raise ValueError("API_TOKEN не установлен. Пожалуйста, установите его в файле .env")

bot = AsyncTeleBot(API_TOKEN)

conn = sqlite3.connect("bot_database.db")
cursor = conn.cursor()


# Команды
@bot.message_handler(commands=["start"])
async def send_welcome(message: Message):
    logging.debug("Использована команда /start")

    welcome_text = (
        "Привет! Я ваш Telegram бот.\n"
        "Доступные команды:\n"
        "/start - вывод всех доступных команд\n"
        "/model - выводит название используемой языковой модели\n"
        "/clear - очищает контекст диалога\n\n"
        "Отправьте любое сообщение, и я отвечу с помощью LLM модели."
    )
    await bot.reply_to(message, welcome_text)

    user_data: UserData = {
        "user_id": message.from_user.id if message.from_user else 0,
        "registration_date": datetime.now().isoformat(),
        "last_active_date": datetime.now().isoformat(),
    }
    insert_result = cursor.execute(
        """
            INSERT OR IGNORE 
            INTO users (user_id, registration_date, last_active_date, context) 
            VALUES (?, ?, ?, ?)
        """,
        (
            user_data["user_id"],
            user_data["registration_date"],
            user_data["last_active_date"],
            None,
        ),
    )

    if insert_result.rowcount > 0:
        logging.info("Новый пользователь зарегистрирован: %s", user_data["user_id"])

    conn.commit()


@bot.message_handler(commands=["model"])
async def send_model_name(message: Message):
    logging.debug("Использована команда /model")
    # Отправляем запрос к LM Studio для получения информации о модели
    response = requests.get("http://localhost:1234/v1/models")

    if response.status_code == 200:
        model_info = response.json()
        model_name = model_info["data"][0]["id"]
        await bot.reply_to(
            message, f"Используемая модель: `{model_name}`", parse_mode="Markdown"
        )
        logging.info("Отправлено название модели: %s", model_name)
    else:
        await bot.reply_to(message, "Не удалось получить информацию о модели.")
        logging.error(
            "Не удалось получить информацию о модели. Код ошибки: %s",
            response.status_code,
        )


@bot.message_handler(commands=["clear"])
async def clear_context(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    logging.debug("Использована команда /clear пользователем: %s", user_id)

    cursor.execute(
        """
            UPDATE users
            SET context = ?
            WHERE user_id = ?
        """, (None, user_id)
    )
    conn.commit()
    await bot.reply_to(message, "Контекст диалога очищен.")
    logging.info("Контекст диалога очищен для пользователя: %s", user_id)


@bot.message_handler()
async def handle_message(message: Message):
    user_id = message.from_user.id if message.from_user else 0

    logging.debug("Получено сообщение от пользователя (%s): %s", user_id, message.text)

    select_result = cursor.execute(
        """
            SELECT user_id 
            FROM users 
            WHERE user_id = ?
        """, (user_id,)
    )
    if select_result.fetchone() is not None:
        cursor.execute(
            """
                UPDATE users 
                SET last_active_date = ? 
                WHERE user_id = ?
            """,
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()
        logging.debug("Обновлена дата последней активности для пользователя: %s", user_id)

    else:
        logging.warning("Пользователь не найден в базе данных: %s", user_id)
        await bot.reply_to(
            message,
            "Пожалуйста, используйте команду /start для регистрации перед использованием бота.",
        )
        return

    user_query = message.text or ""

    row = cursor.execute(
        """
            SELECT context FROM users WHERE user_id = ?
        """, (user_id,)
    ).fetchone()
    context: str | None = row[0] if row is not None else None

    request = {
        "messages": [
            {
                "role": "system",
                "content":
                    """
                        You are a helpful assistant.
                        Do not use backslashes in your responses.
                    """.join("\n").strip(),
            },
            *(json.loads(context) if context else []),
            {"role": "user", "content": user_query},
        ]
    }

    await bot.send_chat_action(message.chat.id, "typing")
    response = requests.post("http://localhost:1234/v1/chat/completions", json=request)

    if response.status_code == 200:
        model_response: ModelResponse = json.loads(response.text)
        assistant_reply = model_response.get("choices")[0].get("message").get("content")
        await bot.reply_to(message, assistant_reply, parse_mode="HTML")
        logging.info("Ответ отправлен пользователю (%s)", user_id)
        logging.debug(
            "Ответ модели: %s",
            model_response.get("choices")[0].get("message").get("content"),
        )

        user_context = {"role": "user", "content": user_query}
        assistant_context = {"role": "assistant", "content": assistant_reply}

        cursor.execute(
            """
                UPDATE users
                SET context = ?
                WHERE user_id = ?
            """,
            (json.dumps([user_context, assistant_context]), user_id),
        )
        conn.commit()
    else:
        await bot.reply_to(message, "Произошла ошибка при обращении к модели.")
        logging.error(
            "Произошла ошибка при обращении к модели. Код ошибки: %s",
            response.status_code,
        )


def create_tables():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                registration_date TEXT,
                last_active_date TEXT,
                context TEXT
            )
        """
    )
    conn.commit()


# Запуск бота
if __name__ == "__main__":
    create_tables()
    logging.info("Бот запущен...")
    asyncio.run(bot.polling())
