import asyncio
import httpx
import re
from pathlib import Path

async def test_proxy(ip_port: str, proto: str) -> bool:
    proxy_url = f"{proto}://{ip_port}"
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0) as client:
            resp = await client.get("https://api.telegram.org", follow_redirects=True)
            if resp.status_code == 200 or "bots" in resp.text.lower():
                print(f"✅ SUCCESS: {proxy_url}")
                return True
    except Exception:
        pass
    return False

async def main():
    proxy_file = Path("proxy/proxies_live1.txt")
    if not proxy_file.exists():
        print("proxy/proxies_live1.txt not found!")
        return
        
    with open(proxy_file) as f:
        content = f.read()
        
    # Extract IP:Port using regex
    ip_ports = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+", content)
    print(f"Found {len(ip_ports)} proxy IP:port entries.")
    
    # Let's test the first 40 entries with both http and socks5
    tasks = []
    for ip_port in ip_ports[:40]:
        tasks.append(test_proxy(ip_port, "socks5"))
        tasks.append(test_proxy(ip_port, "http"))
        
    results = await asyncio.gather(*tasks)
    
if __name__ == "__main__":
    asyncio.run(main())
