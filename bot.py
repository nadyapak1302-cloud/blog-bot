import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp
import os
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SYSTEM_PROMPT = """Ты — Блог-Наставник.

Отвечай структурированно, используй **жирный текст** для заголовков и важных мыслей.

При аудите всегда выделяй:
**Сильные стороны**
**Слабые стороны**
**Что улучшить**
**Рекомендации**

Если человек не знает нишу — помоги её определить.
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
    link = State()
    problem = State()

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аудит профиля", callback_data="audit")],
        [InlineKeyboardButton(text="Идея для Reels", callback_data="reels_idea")],
        [InlineKeyboardButton(text="Контент-план на неделю", callback_data="content_plan")],
        [InlineKeyboardButton(text="Спросить у Нади", callback_data="ask_nadia")]
    ])

def get_page_text(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for s in soup(["script", "style", "nav", "footer"]):
            s.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:3500]
    except Exception as e:
        return f"Не удалось открыть ссылку: {str(e)}"

async def ask_groq(text: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        "temperature": 0.7,
        "max_tokens": 1500
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status == 200:
                res = await resp.json()
                return res["choices"][0]["message"]["content"]
            return "Ошибка при обращении к ИИ. Попробуй позже."

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Я Блог-Наставник.\n\nВыбери действие:", reply_markup=main_keyboard())

@dp.callback_query(F.data == "ask_nadia")
async def ask_nadia(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши вопрос для Нади:")
    await state.set_state(AskNadia.waiting_for_question)
    await callback.answer()

@dp.message(AskNadia.waiting_for_question)
async def send_to_nadia(message: types.Message, state: FSMContext):
    user = message.from_user
    try:
        await bot.send_message(ADMIN_ID, f"Вопрос от {user.full_name} (@{user.username}):\n\n{message.text}")
        await message.answer("Отправлено Наде.", reply_markup=main_keyboard())
    except:
        await message.answer("Не удалось отправить.", reply_markup=main_keyboard())
    await state.clear()

# ===== АУДИТ =====
@dp.callback_query(F.data == "audit")
async def audit_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "**Аудит профиля**\n\n"
        "1. Напиши свою нишу.\n"
        "Если не знаешь — напиши «не знаю»."
    )
    await state.set_state(Audit.niche)
    await callback.answer()

@dp.message(Audit.niche)
async def audit_niche(message: types.Message, state: FSMContext):
    text = message.text.lower()
    if any(w in text for w in ["не знаю", "незнаю", "хз", "не определилась"]):
        await message.answer(
            "Давай определим нишу.\nНапиши:\n"
            "— Чем занимаешься / что умеешь?\n"
            "— Кому хочешь помогать?\n"
            "— О чём тебе интересно рассказывать?"
        )
        await state.update_data(niche="не определена")
        await state.set_state(Audit.goal)
        return

    await state.update_data(niche=message.text)
    await message.answer("2. Какая главная цель блога сейчас?")
    await state.set_state(Audit.goal)

@dp.message(Audit.goal)
async def audit_goal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("niche") == "не определена":
        prompt = f"Человек не знает нишу. Вот информация:\n{message.text}\n\nПредложи 2–3 подходящие ниши с коротким объяснением."
        answer = await ask_groq(prompt)
        await message.answer(answer + "\n\nНапиши нишу, которая ближе, или свою формулировку.")
        await state.update_data(niche="уточняется")
        return

    await state.update_data(goal=message.text)
    await message.answer("3. На каких платформах ведёшь блог?")
    await state.set_state(Audit.platforms)

@dp.message(Audit.platforms)
async def audit_platforms(message: types.Message, state: FSMContext):
    await state.update_data(platforms=message.text)
    await message.answer(
        "4. Скинь ссылку на профиль (если есть) и кратко опиши, что там сейчас "
        "(подписчики, частота постов, тип контента)."
    )
    await state.set_state(Audit.link)

@dp.message(Audit.link)
async def audit_link(message: types.Message, state: FSMContext):
    text = message.text
    page_text = ""
    if "http" in text:
        url = text.split()[0]
        page_text = get_page_text(url)
    
    await state.update_data(link_info=text, page_content=page_text)
    await message.answer("5. Что сейчас больше всего не устраивает в блоге?")
    await state.set_state(Audit.problem)

@dp.message(Audit.problem)
async def audit_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    page = data.get("page_content", "")
    prompt = f"""Сделай подробный аудит блога.

Ниша: {data.get('niche')}
Цель: {data.get('goal')}
Платформы: {data.get('platforms')}
Информация о профиле: {data.get('link_info')}
Текст со страницы (если удалось получить): {page}
Проблема клиента: {message.text}

Дай ответ в структуре:
**Сильные стороны**
**Слабые стороны**
**Что улучшить в первую очередь**
**Конкретные рекомендации**
"""
    answer = await ask_groq(prompt)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")
    await state.clear()

# Идеи и контент-план
@dp.callback_query(F.data.in_({"reels_idea", "content_plan"}))
async def ask_niche(callback: types.CallbackQuery, state: FSMContext):
    mode = "reels" if callback.data == "reels_idea" else "plan"
    await state.update_data(content_mode=mode)
    await callback.message.answer("Напиши свою нишу:")
    await state.set_state(Audit.niche)
    await callback.answer()

@dp.message(Audit.niche)
async def niche_for_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if "content_mode" not in data:
        return
    
    niche = message.text
    if data["content_mode"] == "reels":
        prompt = f"Ниша: {niche}\n\nДай идею для Reels:\n**Тема:**\n**Хук:**\n**Структура:**\n**Что снимать:**"
    else:
        prompt = f"Ниша: {niche}\n\nКонтент-план на 7 дней. Пиши по дням, выделяй **жирным** дни и темы."
    
    answer = await ask_groq(prompt)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text)
async def fallback(message: types.Message):
    answer = await ask_groq(message.text)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
