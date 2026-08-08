from overtone.composition.config import AppConfig
from overtone.web.app import create_app

app = create_app(AppConfig.from_env())
