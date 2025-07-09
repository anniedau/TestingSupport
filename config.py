from pydantic_settings import BaseSettings
from typing import Optional, List
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Flask Configuration
    flask_debug: bool = False
    flask_host: str = "0.0.0.0"
    flask_port: int = 5000
    flask_secret_key: str = "your-secret-key-change-in-production"
    
    # HTTP Configuration
    request_timeout: int = 10
    max_redirects: int = 5
    user_agent: str = "TestingTool/1.0"
    
    # PDF Processing
    max_pdf_size_mb: int = 50
    supported_pdf_extensions: List[str] = [".pdf"]
    
    # Link Validation
    valid_status_codes: List[int] = [200, 201, 202, 203, 204, 205, 206]
    invalid_status_codes: List[int] = [400, 401, 403, 404, 500, 502, 503, 504]
    timeout_status_code: int = 408
    
    # Performance
    max_concurrent_requests: int = 10
    request_delay_seconds: float = 0.1
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Reporting
    report_retention_days: int = 30
    enable_email_notifications: bool = False
    email_smtp_server: Optional[str] = None
    email_smtp_port: int = 587
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    
    # Security
    allowed_file_types: List[str] = ["pdf"]
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings() 