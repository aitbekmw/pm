import asyncio
import aiohttp
import time

# Настройки
API_URL = "http://localhost:8000/transcribe" # Замените на ваш роут
FILE_PATH = "test_audio.mp3"                 # Тестовый файл
CONCURRENT_REQUESTS = 10                     # Сколько файлов отправить одновременно

async def send_request(session, request_id):
    start_time = time.time()
    try:
        with open(FILE_PATH, 'rb') as f:
            # Адаптируйте payload под то, как ваш API ожидает файл
            form = aiohttp.FormData()
            form.add_field('file', f, filename='test_audio.mp3', content_type='audio/mpeg')
            
            async with session.post(API_URL, data=form) as response:
                result = await response.json()
                elapsed = time.time() - start_time
                print(f"[{request_id}] Завершено за {elapsed:.2f} сек. Статус: {response.status}")
                return elapsed
    except Exception as e:
        print(f"[{request_id}] Ошибка: {e}")
        return None

async def main():
    print(f"🚀 Запуск {CONCURRENT_REQUESTS} конкурентных запросов...")
    start_total = time.time()
    
    # Чтобы не упереться в лимиты коннектов aiohttp, можно использовать TCPConnector
    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [send_request(session, i) for i in range(CONCURRENT_REQUESTS)]
        results = await asyncio.gather(*tasks)
    
    successful = [r for r in results if r is not None]
    total_time = time.time() - start_total
    
    print("\n📊 Итоги:")
    print(f"Всего времени заняло: {total_time:.2f} сек")
    if successful:
        print(f"Успешных запросов: {len(successful)}")
        print(f"Среднее время ответа: {sum(successful)/len(successful):.2f} сек")
        print(f"Мин. время ответа: {min(successful):.2f} сек")
        print(f"Макс. время ответа: {max(successful):.2f} сек")

if __name__ == "__main__":
    asyncio.run(main())

'''
nvidia-smi --query-gpu=timestamp,utilization.gpu,utilization.memory,memory.total,memory.free,memory.used,temperature.gpu --format=csv -l 1 > gpu_metrics.csv
'''