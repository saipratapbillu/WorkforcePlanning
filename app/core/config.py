from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_server: str = "localhost"
    db_name: str = "AICompany"
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_trusted_connection: str = "yes"
    db_encrypt: str = "no"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
