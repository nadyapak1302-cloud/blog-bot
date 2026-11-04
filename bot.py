import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp
import os

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ==================== ПРОМПТ ====================
SYSTEM_PROMPT = """Ты — Блог-Наставник.

Отвечай ясно, структурированно и без лишней воды.

Для идей Reels всегда используй формат:
Тема:
Хук:
Структура:
Что снимать:

Для контент-плана пиши по дням, коротко и понятно.
Для аудита — конкретные наблюдения и рекомендации.
"""

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class UserData(StatesGroup):
    waiting_niche = State()
    audit_step = State()

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
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    data = {
        "model": "openai/gpt-oss-20b",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
            else:
                error = await resp.text()
                return f"Ошибка Groq: {resp.status}\n{error}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я — твой Блог-Наставник.\n\n"
        "Могу помочь с идеями для Reels, контент-планом и ответить на вопросы по блогу.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "ask_nadia")
async def ask_nadia_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свой вопрос. Я передам его Наде.")
    await state.set_state(AskNadia.waiting_for_question)
    await callback.answer()

@dp.message(AskNadia.waiting_for_question)
async def process_nadia_question(message: types.Message, state: FSMContext):
    user = message.from_user
    await bot.send_message(
        ADMIN_ID,
        f"Новый вопрос от {user.full_name} (@{user.username}):\n\n{message.text}"
    )
    await message.answer("Вопрос отправлен Наде.", reply_markup=main_keyboard())
    await state.clear()

@dp.callback_query(F.data == "reels_idea")
async def reels_idea(callback: types.CallbackQuery):
    answer = await ask_groq("Дай одну сильную идею для Reels: тема, хук, структура и визуал.")
    await callback.message.answer(answer, reply_markup=main_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "content_plan")
async def content_plan(callback: types.CallbackQuery):
    answer = await ask_groq("Составь контент-план на 7 дней в виде таблицы с акцентом на Reels.")
    await callback.message.answer(answer, reply_markup=main_keyboard())
    await callback.answer()

@dp.message(F.text)
async def handle_message(message: types.Message):
    answer = await ask_groq(message.text)
    await message.answer(answer, reply_markup=main_keyboard())
@dp.callback_query(F.data == "audit")
async def start_audit(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Давай сделаем короткий аудит.\n\n"
        "Напиши свою нишу (например: психология, фитнес, финансы, бьюти и т.д.)"
    )
    await state.set_state(UserData.waiting_niche)
    await state.update_data(mode="audit")
    await callback.answer()

@dp.callback_query(F.data == "reels_idea")
async def reels_idea(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свою нишу, и я дам идею для Reels именно под неё.")
    await state.set_state(UserData.waiting_niche)
    await state.update_data(mode="reels")
    await callback.answer()

@dp.callback_query(F.data == "content_plan")
async def content_plan(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свою нишу, и я составлю контент-план.")
    await state.set_state(UserData.waiting_niche)
    await state.update_data(mode="plan")
    await callback.answer()

@dp.message(UserData.waiting_niche)
async def process_niche(message: types.Message, state: FSMContext):
    data = await state.get_data()
    niche = message.text
    mode = data.get("mode")

    if mode == "reels":
        prompt = f"Ниша клиента: {niche}. Дай одну чёткую идею для Reels. Формат:\nТема:\nХук:\nСтруктура:\nЧто снимать:"
        answer = await ask_groq(prompt)
    elif mode == "plan":
        prompt = f"Ниша клиента: {niche}. Составь контент-план на 7 дней. Пиши структурированно, по дням, без сложных таблиц. Акцент на Reels."
        answer = await ask_groq(prompt)
    else:  # audit
        prompt = f"Ниша клиента: {niche}. Сделай короткий аудит блога. Напиши сильные стороны, что улучшить и 3 главных рекомендации."
        answer = await ask_groq(prompt)

    await message.answer(answer, reply_markup=main_keyboard())
    await state.clear()
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
