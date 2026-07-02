import sys
from pathlib import Path

# Add root directory to sys.path to allow imports from app
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.tools.check_sessions import check_all_sessions

if __name__ == "__main__":
    check_all_sessions()


