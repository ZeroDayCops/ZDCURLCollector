import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.utils.date_parser import is_recent_post

def run_tests():
    now = datetime.now(timezone.utc).date()
    
    # 1. Today
    today_str = now.isoformat()
    assert is_recent_post(today_str) is True, f"Today ({today_str}) should be recent"
    
    # 2. Yesterday
    yesterday_str = (now - timedelta(days=1)).isoformat()
    assert is_recent_post(yesterday_str) is True, f"Yesterday ({yesterday_str}) should be recent"
    
    # 3. Two days ago
    two_days_ago_str = (now - timedelta(days=2)).isoformat()
    assert is_recent_post(two_days_ago_str) is True, f"2 days ago ({two_days_ago_str}) should be recent"
    
    # 4. Three days ago (should be True now)
    three_days_ago_str = (now - timedelta(days=3)).isoformat()
    assert is_recent_post(three_days_ago_str) is True, f"3 days ago ({three_days_ago_str}) should be recent"
    
    # 5. Four days ago (should be True now)
    four_days_ago_str = (now - timedelta(days=4)).isoformat()
    assert is_recent_post(four_days_ago_str) is True, f"4 days ago ({four_days_ago_str}) should be recent"
    
    # 6. Five days ago (should be False)
    five_days_ago_str = (now - timedelta(days=5)).isoformat()
    assert is_recent_post(five_days_ago_str) is False, f"5 days ago ({five_days_ago_str}) should NOT be recent"
    
    # 7. One week ago (should be False)
    one_week_ago_str = (now - timedelta(days=7)).isoformat()
    assert is_recent_post(one_week_ago_str) is False, f"1 week ago ({one_week_ago_str}) should NOT be recent"
    
    # 8. Missing/None dates (should be True)
    assert is_recent_post(None) is True, "None date should default to recent"
    assert is_recent_post("") is True, "Empty date should default to recent"
    
    print("✅ All date parser recency tests passed successfully!")


if __name__ == "__main__":
    run_tests()
