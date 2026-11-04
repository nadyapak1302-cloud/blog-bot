    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            error_text = await resp.text()
            if resp.status == 200:
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
            else:
                return f"Ошибка Groq: {resp.status}\n{error_text}"
