import httpx
import asyncio

async def test():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://localhost:8001/terminology/resolve", json={"terms": ["weight loss", "blood pressure"]}, timeout=10)
            print("Resolve:", resp.status_code, resp.json())
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
