import asyncio
import httpx
import re
from pathlib import Path

# Use the user's actual bot token
BOT_TOKEN = "8808103773:AAGvQv0Dcyk8uyRVkydR9jEHDBEnKqpwVFw"
TEST_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

async def test_tg_proxy(ip_port: str, proto: str) -> str | None:
    proxy_url = f"{proto}://{ip_port}"
    try:
        # We use a short timeout of 3.0 seconds to find the fastest one
        async with httpx.AsyncClient(proxy=proxy_url, timeout=3.0) as client:
            resp = await client.post(TEST_URL)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    username = data["result"]["username"]
                    print(f"🔥 WORKING FAST PROXY: {proxy_url} (Bot: @{username})")
                    return proxy_url
    except Exception:
        pass
    return None

async def main():
    proxy_file = Path("proxy/proxies_live1.txt")
    if not proxy_file.exists():
        print("proxy/proxies_live1.txt not found!")
        return
        
    with open(proxy_file) as f:
        content = f.read()
        
    # Extract IP:Port using regex
    ip_ports = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+", content)
    print(f"Testing {len(ip_ports)} proxies against getMe API...")
    
    # We run them in batches of 50 to avoid file descriptor limits or high concurrency issues
    batch_size = 50
    for i in range(0, len(ip_ports), batch_size):
        batch = ip_ports[i:i+batch_size]
        print(f"Testing batch {i // batch_size + 1}...")
        tasks = []
        for ip_port in batch:
            tasks.append(test_tg_proxy(ip_port, "socks5"))
            tasks.append(test_tg_proxy(ip_port, "http"))
            
        results = await asyncio.gather(*tasks)
        # Filter out None results
        working = [r for r in results if r]
        if working:
            print(f"\n🎉 Found working proxies: {working}")
            break

if __name__ == "__main__":
    asyncio.run(main())
