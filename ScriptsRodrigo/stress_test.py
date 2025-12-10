import asyncio
import aiohttp
import time

URL = "https://simuladorls.onrender.com/"
#URL = "#https://simuladoropcoes.onrender.com/"
#URL = "http://simuladoropcoes.onrender.com/?ativo=PETR4"


USERS = 8000    # quantidade de acessos simultâneos
REQUESTS_PER_USER = 3  # quantas vezes cada “usuário” acessa


async def hit_session(session, user_id):
    for _ in range(REQUESTS_PER_USER):
        #async with session.get(URL) as resp:
        async with session.get(URL, ssl=False) as resp:
            status = resp.status
            await resp.text()
    return status


async def run_stress():
    start = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = [
            hit_session(session, uid)
            for uid in range(USERS)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

    end = time.time()

    print("---- RESULTADOS ----")
    print(f"Usuários simultâneos: {USERS}")
    print(f"Requests totais: {USERS * REQUESTS_PER_USER}")
    print(f"Tempo total: {end - start:.2f} segundos")
    print(f"Tempo médio por request: {(end - start) / (USERS * REQUESTS_PER_USER):.4f}s")

    print("\nStatus diferentes de 200:")
    errors = [r for r in results if r != 200]
    print(errors if errors else "Nenhum erro")


if __name__ == "__main__":
    asyncio.run(run_stress())
