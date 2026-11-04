import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SYSTEM_PROMPT = """Ты — Блог-Наставник.

Отвечай ясно и структурированно. Используй **жирный текст** для важных моментов.

Для идей Reels:
**Тема:**
**Хук:**
**Структура:**
**Что снимать:**

Для аудита анализируй ответы клиента и давай конкретные рекомендации.
"""

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AskNadia(StatesGroup):
    waiting_for_question = State()

class Audit(StatesGroup):
    niche = State()
    goal = State()
    platforms = State()
    problem = State()

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аудит профиля", callback_data="audit")],
        [InlineKeyboardButton(text="Идея для Reels", callback_data="reels_idea")],
        [InlineKeyboardButton(text="Контент-план на неделю", callback_data="content_plan")],
        [InlineKeyboardButton(text="Спросить у Нади", callback_data="ask_nadia")]
    ])

async def ask_groq(user_message: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.7,
        "max_tokens": 1200
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
            else:
                return f"Ошибка Groq: {resp.status}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я — твой Блог-Наставник.\n\nВыбери действие:",
        reply_markup=main_keyboard()
    )

# ===== Спросить у Нади =====
@dp.callback_query(F.data == "ask_nadia")
async def ask_nadia_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свой вопрос для Нади:")
    await state.set_state(AskNadia.waiting_for_question)
    await callback.answer()

@dp.message(AskNadia.waiting_for_question)
async def process_nadia_question(message: types.Message, state: FSMContext):
    user = message.from_user
    try:
        await bot.send_message(ADMIN_ID, f"Вопрос от {user.full_name} (@{user.username}):\n\n{message.text}")
        await message.answer("Вопрос отправлен Наде.", reply_markup=main_keyboard())
    except:
        await message.answer("Не удалось отправить.", reply_markup=main_keyboard())
    await state.clear()

# ===== Аудит =====
@dp.callback_query(F.data == "audit")
async def start_audit(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("**Аудит профиля**\n\n1. Напиши свою нишу:")
    await state.set_state(Audit.niche)
    await callback.answer()

@dp.message(Audit.niche)
async def audit_niche(message: types.Message, state: FSMContext):
    await state.update_data(niche=message.text)
    await message.answer("2. Какая у тебя главная цель сейчас? (рост, продажи, экспертность и т.д.)")
    await state.set_state(Audit.goal)

@dp.message(Audit.goal)
async def audit_goal(message: types.Message, state: FSMContext):
    await state.update_data(goal=message.text)
    await message.answer("3. На каких платформах ведёшь блог? (Telegram, Instagram, VK, YouTube и т.д.)")
    await state.set_state(Audit.platforms)

@dp.message(Audit.platforms)
async def audit_platforms(message: types.Message, state: FSMContext):
    await state.update_data(platforms=message.text)
    await message.answer("4. Что сейчас больше всего не получается или беспокоит в блоге?")
    await state.set_state(Audit.problem)

@dp.message(Audit.problem)
async def audit_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prompt = f"""Сделай аудит блога на основе ответов клиента:

Ниша: {data.get('niche')}
Цель: {data.get('goal')}
Платформы: {data.get('platforms')}
Проблема: {message.text}

Напиши:
**Сильные стороны**
**Что улучшить**
**3 главные рекомендации**
"""
    answer = await ask_groq(prompt)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")
    await state.clear()

# ===== Идея для Reels =====
@dp.callback_query(F.data == "reels_idea")
async def reels_idea(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свою нишу для идеи Reels:")
    await state.set_state(Audit.niche)  # переиспользуем
    await state.update_data(mode="reels")
    await callback.answer()

# ===== Контент-план =====
@dp.callback_query(F.data == "content_plan")
async def content_plan(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свою нишу для контент-плана:")
    await state.set_state(Audit.niche)
    await state.update_data(mode="plan")
    await callback.answer()

@dp.message(Audit.niche)
async def process_niche_for_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("mode") not in ["reels", "plan"]:
        return  # это часть аудита, пропускаем

    niche = message.text
    mode = data.get("mode")

    if mode == "reels":
        prompt = f"Ниша: {niche}\n\nДай идею для Reels:\n**Тема:**\n**Хук:**\n**Структура:**\n**Что снимать:**"
    else:
        prompt = f"Ниша: {niche}\n\nСоставь контент-план на 7 дней. Пиши по дням, используй **жирный** для дней и тем."

    answer = await ask_groq(prompt)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text)
async def handle_message(message: types.Message):
    answer = await ask_groq(message.text)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
