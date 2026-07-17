"""Standalone runner for the admin panel (FastAPI + Uvicorn).
Run alongside main.py (the bot) as a separate process:
    python run_admin.py
"""
import uvicorn

from config.settings import settings

if __name__ == "__main__":
    uvicorn.run("admin.main:app", host="0.0.0.0", port=settings.ADMIN_PANEL_PORT, reload=False)
