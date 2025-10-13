import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key")
    
    
    # Testing/Production Discord App Selection
    IS_TESTING = os.getenv("IS_TESTING", "no").lower() in ("yes", "true", "1")
    
    # Discord OAuth configuration
    if IS_TESTING:
        DISCORD_CLIENT_ID = os.getenv("TEST_CLIENT_ID")
        DISCORD_CLIENT_SECRET = os.getenv("TEST_SECRET")
        DISCORD_REDIRECT_URI = os.getenv("TEST_REDIRECT_URI", "http://127.0.0.1:2456/callback")
    else:
        DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
        DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
        DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
    
    DISCORD_OAUTH2_SCOPE = ["identify, guilds"]
    
    # Supabase database configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Application constants
    SESSION_VERSION = 4
    NUMBER_OF_DISTRACTORS = 4
    
    # Security configuration
    SECRET_TOKEN_KEY = os.getenv('TOKEN_SECRET_KEY', 'dev_token_secret')
    TOKEN_EXPIRY_SECONDS = 600  # 10 minutes
    
    # GitHub configuration for sponsors
    GITHUB_SPONSORS_URL = "https://github.com/sponsors/Joshua-Wilcox?o=esb"
    GITHUB_REPO_URL = "https://github.com/Joshua-Wilcox/Flashcards"

    # n8n ingestion configuration
    N8N_INGEST_TOKEN = os.getenv("N8N_INGEST_TOKEN")
    N8N_DEFAULT_USER_ID = os.getenv("N8N_DEFAULT_USER_ID", "n8n-ingest")
    N8N_DEFAULT_USERNAME = os.getenv("N8N_DEFAULT_USERNAME", "n8n-bot")
