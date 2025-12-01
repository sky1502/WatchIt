from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # DB
    db_path: str = Field(default="child_monitor.db", alias="WATCHIT_DB_PATH")
    db_key: str = Field(default="change_this_strong_key", alias="WATCHIT_DB_KEY")

    # Policy
    policy_version: str = Field(default="1.0.0", alias="WATCHIT_POLICY_VERSION")

    # Schedule
    sched_name: str = Field(default="schoolnights", alias="WATCHIT_SCHEDULE_NAME")
    sched_days: str = Field(default="Mon,Tue,Wed,Thu", alias="WATCHIT_SCHEDULE_DAYS")
    sched_quiet: str = Field(default="21:00-07:00", alias="WATCHIT_SCHEDULE_QUIET")

    # Parent PIN
    parent_pin: str = Field(default="123456", alias="WATCHIT_PARENT_PIN")

    # Ollama
    ollama_model: str = Field(default="qwen2.5:7b-instruct-q4_K_M", alias="WATCHIT_OLLAMA_MODEL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="WATCHIT_OLLAMA_BASE_URL")

    # Server
    bind_host: str = Field(default="127.0.0.1", alias="WATCHIT_BIND_HOST")
    bind_port: int = Field(default=4849, alias="WATCHIT_BIND_PORT")

    # Postgres mirror (optional)
    pg_dsn: str | None = Field(default=None, alias="WATCHIT_PG_DSN")

    # Features
    enable_ocr: bool = Field(default=True, alias="WATCHIT_ENABLE_OCR")
    ocr_confidence_threshold: float = Field(default=0.7, alias="WATCHIT_OCR_CONFIDENCE_THRESHOLD")
    save_screenshots: bool = Field(default=False, alias="WATCHIT_SAVE_SCREENSHOTS")
    screenshots_dir: str = Field(default="screenshots", alias="WATCHIT_SCREENSHOT_DIR")

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
