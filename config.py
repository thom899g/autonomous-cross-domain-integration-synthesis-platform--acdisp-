"""
Configuration management for ACDISP with robust validation.
Centralizes all configuration and ensures proper initialization before use.
"""
import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
import firebase_admin
from firebase_admin import credentials, firestore
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DomainConfig(BaseModel):
    """Configuration for individual domain modules."""
    domain_name: str = Field(..., description="Unique identifier for the domain")
    adapter_class: str = Field(..., description="Python class for domain adapter")
    resource_quota: Dict[str, float] = Field(
        default_factory=lambda: {"cpu": 1.0, "memory": 1.0, "gpu": 0.0},
        description="Resource allocation for this domain"
    )
    enabled: bool = Field(default=True, description="Whether domain is active")
    
    @validator('domain_name')
    def validate_domain_name(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Domain name must be a non-empty string")
        return v.lower().replace(' ', '_')

class HubConfig(BaseModel):
    """Configuration for central orchestration hub."""
    polling_interval: float = Field(default=5.0, ge=1.0, description="Polling interval in seconds")
    max_retries: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    timeout: float = Field(default=30.0, ge=5.0, description="Default timeout in seconds")
    log_level: str = Field(default="INFO", description="Logging level")

@dataclass
class FirebaseConfig:
    """Firebase configuration with validation."""
    project_id: str = field(default_factory=lambda: os.getenv("FIREBASE_PROJECT_ID", ""))
    private_key_id: str = field(default_factory=lambda: os.getenv("FIREBASE_PRIVATE_KEY_ID", ""))
    private_key: str = field(default_factory=lambda: os.getenv("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'))
    client_email: str = field(default_factory=lambda: os.getenv("FIREBASE_CLIENT_EMAIL", ""))
    client_id: str = field(default_factory=lambda: os.getenv("FIREBASE_CLIENT_ID", ""))
    
    def validate(self) -> bool:
        """Validate Firebase configuration."""
        required_fields = ['project_id', 'private_key', 'client_email']
        for field in required_fields:
            if not getattr(self, field):
                logger.error(f"Missing required Firebase configuration: {field}")
                return False
        
        # Validate key format
        if not self.private_key.startswith('-----BEGIN PRIVATE KEY-----'):
            logger.error("Firebase private key format is invalid")
            return False
        
        return True

class SystemConfig:
    """Singleton configuration manager for ACDISP."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._config_path = Path("config/acdisp_config.json")
            self.domains: Dict[str, DomainConfig] = {}
            self.hub_config = HubConfig()
            self.firebase_config = FirebaseConfig()
            self._load_configuration()
            self._initialized = True
    
    def _load_configuration(self) -> None:
        """Load configuration from file or create defaults."""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r') as f:
                    config_data = json.load(f)
                
                # Load domain configurations
                if 'domains' in config_data:
                    for domain_data in config_data['domains']:
                        domain = DomainConfig(**domain_data)
                        self.domains[domain.domain_name] = domain
                
                # Load hub configuration
                if 'hub' in config_data:
                    self.hub_config = HubConfig(**config_data['hub'])
                
                logger.info(f"Configuration loaded from {self._config_path}")
            else:
                self._create_default_config()
                logger.warning(f"No configuration file found. Created defaults at {self._config_path}")
                
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _create_default_config(self) -> None:
        """Create default configuration file."""
        default_config = {
            "domains": [
                {
                    "domain_name": "financial_analysis",
                    "adapter_class": "FinancialAdapter",
                    "resource_quota": {"cpu": 2.0, "memory": 4.0, "gpu": 0.0}
                },
                {
                    "domain_name": "healthcare_analytics",
                    "adapter_class": "HealthcareAdapter", 
                    "resource_quota": {"cpu": 3.0, "memory": 8.0, "gpu": 1.0}
                }
            ],
            "hub": {
                "polling_interval": 5.0,
                "max_retries": 3,
                "timeout": 30.0,
                "log_level": "INFO"
            }
        }
        
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        # Load the defaults