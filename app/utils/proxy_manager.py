import os
import re
import random
import logging
from pathlib import Path

logger = logging.getLogger("proxy_manager")

class ProxyManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProxyManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
            
        self.proxies = []
        self.current_idx = 0
        self.load_proxies()
        self.initialized = True

    def load_proxies(self):
        """Loads and parses proxies from proxy/proxies_live1.txt."""
        proxy_file = Path("proxy/proxies_live1.txt")
        if not proxy_file.exists():
            # Try parent directory or env configuration
            proxy_file = Path(__file__).resolve().parent.parent.parent / "proxy" / "proxies_live1.txt"

        if not proxy_file.exists():
            logger.warning(f"⚠️ Proxy file not found at {proxy_file}. Fallback to env PROXY_SERVER.")
            return

        try:
            with open(proxy_file, "r") as f:
                content = f.read()
            
            # Extract IP:Port entries
            ip_ports = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+", content)
            
            # De-duplicate
            ip_ports = list(dict.fromkeys(ip_ports))
            
            # Known verified working proxies from testing (prioritize these at the front!)
            priority_proxies = [
                "http://84.47.150.125:1080",
                "socks5://84.47.150.125:1080",
                "http://4.221.164.109:443",
            ]
            
            # Build full list with both http and socks5 protocols
            all_generated = []
            for ip_port in ip_ports:
                all_generated.append(f"http://{ip_port}")
                all_generated.append(f"socks5://{ip_port}")
                
            # Filter out duplicates of priority proxies
            other_proxies = [p for p in all_generated if p not in priority_proxies]
            
            # Shuffle remaining to distribute load
            random.shuffle(other_proxies)
            
            self.proxies = priority_proxies + other_proxies
            logger.info(f"💾 Loaded {len(self.proxies)} proxy configurations (prioritized: {len(priority_proxies)})")
        except Exception as e:
            logger.error(f"❌ Failed to load proxies: {e}")

    def get_proxy(self) -> str | None:
        """Returns the next proxy in rotation, or env fallback if none loaded."""
        if not self.proxies:
            env_proxy = os.getenv("PROXY_SERVER", "").strip()
            return env_proxy if env_proxy else None
            
        proxy = self.proxies[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.proxies)
        return proxy

    def get_all_proxies(self) -> list[str]:
        return self.proxies

# Global helper function
def get_next_proxy() -> str | None:
    return ProxyManager().get_proxy()
