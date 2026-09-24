from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — local SQLite file, no server to run. Override in .env if needed.
    database_url: str = "sqlite:///./kt_dashboard.db"

    # Vector store — ChromaDB, persisted to a local folder, no server to run either.
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "chunks"

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    google_scopes: list[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ]

    # Local LLM (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"

    # App
    secret_key: str
    frontend_url: str = "http://localhost:3000"


settings = Settings()
