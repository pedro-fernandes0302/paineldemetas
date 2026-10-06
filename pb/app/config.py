from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    digisac_base_url: str = ""
    digisac_token: str = ""
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_key: str = ""
    google_sheets_spreadsheet_id: str = ""
    google_sheets_aba_produtividade: str = "P&P"
    bq_project_id: str = ""
    bq_dataset: str = "rh"
    bq_table_colaboradores: str = "colaboradores"
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()