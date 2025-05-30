import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key")
    
    SECRET_TOKEN_KEY = os.getenv('TOKEN_SECRET_KEY', 'dev_token_secret')

    
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
    
    # Database configuration
    DATABASE_PATH = 'flashcards_normalized.db'
    
    # Application constants
    SESSION_VERSION = 4
    NUMBER_OF_DISTRACTORS = 4
    
    # Security configuration
    SECRET_TOKEN_KEY = os.getenv('TOKEN_SECRET_KEY', 'dev_token_secret')
    TOKEN_EXPIRY_SECONDS = 600  # 10 minutes
    
    # Stripe configuration
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
