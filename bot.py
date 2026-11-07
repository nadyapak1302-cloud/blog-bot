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

Отвечай красиво, живо и понятно. Используй эмодзи и **жирный текст**.

Формат идеи для Reels:
🎯 **Тема:**
🔥 **Хук:**
📋 **Структура:**
🎥 **Что снимать:**
💡 **Совет:**

Для контент-плана пиши по дням с эмодзи.
Для аудита используй блоки:
💪 **Сильные стороны**
⚠️ **Слабые стороны**
🚀 **Что улучшить**
✅ **Рекомендации**

Будь конкретным и полезным.
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

class Content(StatesGroup):
    waiting_niche = State()

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аудит профиля", callback_data="audit")],
        [InlineKeyboardButton(text="🎬 Идея для Reels", callback_data="reels_idea")],
        [InlineKeyboardButton(text="📅 Контент-план", callback_data="content_plan")],
        [InlineKeyboardButton(text="✨ Ежедневные идеи", callback_data="daily_ideas")],
        [InlineKeyboardButton(text="👩‍💻 Спросить у Нади", callback_data="ask_nadia")]
    ])

def get_page_text(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:3000]
    except:
        return "Не удалось получить содержимое страницы."

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
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
            return "😔 Не получилось получить ответ. Попробуй ещё раз."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! 👋 Я твой **Блог-Наставник**.\n\n"
        "Помогу с идеями, планом и аудитом блога.\n\n"
        "Выбирай, что нужно:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

# ===== Спросить у Нади =====
@dp.callback_query(F.data == "ask_nadia")
async def ask_nadia(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свой вопрос — я передам его Наде 👩‍💻")
    await state.set_state(AskNadia.waiting_for_question)
    await callback.answer()

@dp.message(AskNadia.waiting_for_question)
async def process_question(message: types.Message, state: FSMContext):
    user = message.from_user
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 Новый вопрос от {user.full_name} (@{user.username}):\n\n{message.text}"
        )
        await message.answer("✅ Вопрос отправлен Наде!", reply_markup=main_keyboard())
    except:
        await message.answer("Не удалось отправить. Попробуй позже.", reply_markup=main_keyboard())
    await state.clear()

# ===== Ежедневные идеи =====
@dp.callback_query(F.data == "daily_ideas")
async def daily_ideas(callback: types.CallbackQuery):
    await callback.message.answer(
        "✨ **Ежедневные идеи**\n\n"
        "Напиши свою нишу в любой момент через кнопку «🎬 Идея для Reels», "
        "и я дам свежую идею именно под тебя.\n\n"
        "Автоматическая рассылка каждый день — в разработке 😊",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await callback.answer()

# ===== АУДИТ =====
@dp.callback_query(F.data == "audit")
async def audit_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📊 **Аудит профиля**\n\n"
        "1. Напиши свою нишу.\n"
        "Если не знаешь — напиши «не знаю», помогу определиться 😊"
    )
    await state.set_state(Audit.niche)
    await callback.answer()

@dp.message(Audit.niche)
async def audit_niche(message: types.Message, state: FSMContext):
    if any(word in message.text.lower() for word in ["не знаю", "незнаю", "хз"]):
        await message.answer(
            "Давай найдём нишу 💡\n\n"
            "Напиши коротко:\n"
            "• Чем ты занимаешься?\n"
            "• Кому хочешь помогать?\n"
            "• О чём тебе интересно говорить?"
        )
        await state.update_data(niche="не определена")
        await state.set_state(Audit.goal)
        return

    await state.update_data(niche=message.text)
    await message.answer("2. Какая главная цель блога сейчас? 🎯")
    await state.set_state(Audit.goal)

@dp.message(Audit.goal)
async def audit_goal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("niche") == "не определена":
        prompt = f"Помоги определить нишу. Человек написал:\n{message.text}\n\nПредложи 2-3 варианта ниши с коротким объяснением. Используй эмодзи."
        answer = await ask_groq(prompt)
        await message.answer(answer + "\n\nНапиши нишу, которая откликается 💫")
        await state.update_data(niche="уточняется")
        return

    await state.update_data(goal=message.text)
    await message.answer("3. На каких платформах ведёшь блог? 📱")
    await state.set_state(Audit.platforms)

@dp.message(Audit.platforms)
async def audit_platforms(message: types.Message, state: FSMContext):
    await state.update_data(platforms=message.text)
    await message.answer(
        "4. Скинь ссылку на профиль (если есть) и коротко опиши, что там сейчас 📈\n"
        "(примерно подписчики, как часто постишь, какой контент)"
    )
    await state.set_state(Audit.link)

@dp.message(Audit.link)
async def audit_link(message: types.Message, state: FSMContext):
    page_content = ""
    if "http" in message.text:
        url = next((w for w in message.text.split() if w.startswith("http")), None)
        if url:
            page_content = get_page_text(url)
    await state.update_data(link_info=message.text, page_content=page_content)
    await message.answer("5. Что сейчас больше всего не устраивает в блоге? 😟")
    await state.set_state(Audit.problem)

@dp.message(Audit.problem)
async def audit_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prompt = f"""Сделай подробный и красивый аудит блога.

Ниша: {data.get('niche')}
Цель: {data.get('goal')}
Платформы: {data.get('platforms')}
О профиле: {data.get('link_info')}
Текст со страницы: {data.get('page_content', 'нет')}
Проблема: {message.text}

Используй эмодзи и **жирный текст**. Структура:
💪 **Сильные стороны**
⚠️ **Слабые стороны**
🚀 **Что улучшить**
✅ **Рекомендации**
"""
    answer = await ask_groq(prompt)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")
    await state.clear()

# ===== ИДЕИ И КОНТЕНТ-ПЛАН (отдельное состояние) =====
@dp.callback_query(F.data == "reels_idea")
async def reels_idea(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎬 Напиши свою нишу, и я дам идею для Reels:")
    await state.set_state(Content.waiting_niche)
    await state.update_data(mode="reels")
    await callback.answer()

@dp.callback_query(F.data == "content_plan")
async def content_plan(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📅 Напиши свою нишу для контент-плана:")
    await state.set_state(Content.waiting_niche)
    await state.update_data(mode="plan")
    await callback.answer()

@dp.message(Content.waiting_niche)
async def process_content_niche(message: types.Message, state: FSMContext):
    data = await state.get_data()
    niche = message.text
    mode = data.get("mode")

    if mode == "reels":
        prompt = f"Ниша: {niche}\n\nДай красивую идею для Reels:\n🎯 **Тема:**\n🔥 **Хук:**\n📋 **Структура:**\n🎥 **Что снимать:**\n💡 **Совет:**"
    else:
        prompt = f"Ниша: {niche}\n\nСоставь контент-план на 7 дней. Пиши по дням с эмодзи и **жирным текстом**."

    answer = await ask_groq(prompt)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")
    await state.clear()

# Обычные сообщения
@dp.message(F.text)
async def handle_text(message: types.Message):
    answer = await ask_groq(message.text)
    await message.answer(answer, reply_markup=main_keyboard(), parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
