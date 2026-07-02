"""
Simple entry point: python run.py
Starts the FastAPI server with uvicorn.
"""

import uvicorn
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

if __name__ == "__main__":
    import os
    should_reload = os.getenv("RELOAD", "false").lower() == "true"
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=should_reload,
        reload_dirs=["app"] if should_reload else None,
        log_level="info",
    )
