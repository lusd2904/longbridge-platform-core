import os
import sys

sys.path.insert(0, os.path.abspath("backend-server/src"))

from app import create_app
from extensions import db
from models.user import AppConfig

app = create_app()
with app.app_context():
    configs = AppConfig.query.filter(AppConfig.key.in_(["AI_BASE_URL", "AI_URL"])).all()
    for config in configs:
        if "lucen.cc" in config.value:
            config.value = config.value.replace("lucen.cc", "integrate.api.nvidia.com")
            print(f"Updated {config.key} to {config.value}")
    db.session.commit()
    print("DB AI settings updated successfully.")
