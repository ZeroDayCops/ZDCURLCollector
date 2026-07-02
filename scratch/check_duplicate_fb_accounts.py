import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def get_facebook_user_id(profile_path: Path) -> str:
    async with async_playwright() as pw:
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            cookies = await context.cookies()
            try:
                await context.close()
            except Exception:
                pass
            
            for c in cookies:
                if c["name"] == "c_user":
                    return c["value"]
            return "No c_user cookie"
        except Exception as e:
            return f"Error: {e}"

async def main():
    profiles_dir = Path("sessions/profiles/facebook")
    if not profiles_dir.exists():
        print(f"❌ Profiles directory not found: {profiles_dir}")
        return

    profiles = [d for d in profiles_dir.iterdir() if d.is_dir()]
    profiles.sort()

    print("\n🕵️‍♂️  Analyzing Facebook profiles for duplicate accounts...")
    print("=" * 60)
    
    results = {}
    for p in profiles:
        print(f"   ⏳ Auditing '{p.name}'...")
        user_id = await get_facebook_user_id(p)
        results[p.name] = user_id
        print(f"      👤 Facebook User ID: {user_id}")
    
    print("\n📊 SUMMARY:")
    print("=" * 60)
    
    # Check duplicates
    id_to_profiles = {}
    for name, uid in results.items():
        if uid.startswith("Error") or uid == "No c_user cookie":
            continue
        if uid not in id_to_profiles:
            id_to_profiles[uid] = []
        id_to_profiles[uid].append(name)
        
    has_duplicates = False
    for uid, names in id_to_profiles.items():
        if len(names) > 1:
            has_duplicates = True
            print(f"   ⚠️  Duplicate Account detected! User ID {uid} is used by profiles: {names}")
            
    if not has_duplicates:
        print("   ✅ All checked profiles point to unique Facebook accounts!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
