"""
Configuration management for CanopyWave Model Tester.

Load settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

# Load .env file if exists
load_dotenv()


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    name: str
    endpoint: str = ""  # Full endpoint URL
    display_name: str = ""
    max_tokens: int = 1000
    temperature: float = 0.7
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name.split("/")[-1]


# Model endpoint registry - maps model path to its API endpoint
MODEL_ENDPOINTS = {
    "zai/glm-5": "https://inference.canopywave.io/v1/chat/completions",
    "deepseek/deepseek-chat-v3.2": "https://inference.canopywave.io/v1/chat/completions",
    "moonshotai/kimi-k2.5": "https://inference.canopywave.io/v1/chat/completions",
    "zai/glm-4.7": "https://inference.canopywave.io/v1/chat/completions",
    "xiaomimimo/mimo-v2-flash": "https://api.canopywave.io/v1/chat/completions",
    "minimax/minimax-m2.5": "https://inference.canopywave.io/v1/chat/completions",
    "minimax/minimax-m2.1": "https://inference.canopywave.io/v1/chat/completions",
    "qwen/qwen-3.5": "https://inference.canopywave.io/v1/chat/completions",
}


def get_model_endpoint(model_name: str) -> str:
    """Get the API endpoint for a given model."""
    return MODEL_ENDPOINTS.get(model_name, "https://inference.canopywave.io/v1/chat/completions")


@dataclass
class Config:
    """Main configuration class."""
    
    # API Settings
    api_key: str = field(default_factory=lambda: os.getenv("CANOPYWAVE_API_KEY", ""))
    
    # Request Settings
    timeout: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "60")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    
    # Default Model
    default_model: str = field(default_factory=lambda: os.getenv("DEFAULT_MODEL", "deepseek/deepseek-chat-v3.2"))
    
    # Semantic Similarity
    embedder_model: str = field(default_factory=lambda: os.getenv("EMBEDDER_MODEL", "all-mpnet-base-v2"))
    
    # Available models for testing
    available_models: List[ModelConfig] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.available_models:
            self.available_models = [
                ModelConfig(name="zai/glm-5", endpoint=MODEL_ENDPOINTS["zai/glm-5"]),
                ModelConfig(name="deepseek/deepseek-chat-v3.2", endpoint=MODEL_ENDPOINTS["deepseek/deepseek-chat-v3.2"]),
                ModelConfig(name="moonshotai/kimi-k2.5", endpoint=MODEL_ENDPOINTS["moonshotai/kimi-k2.5"]),
                ModelConfig(name="zai/glm-4.7", endpoint=MODEL_ENDPOINTS["zai/glm-4.7"]),
                ModelConfig(name="xiaomimimo/mimo-v2-flash", endpoint=MODEL_ENDPOINTS["xiaomimimo/mimo-v2-flash"]),
                ModelConfig(name="minimax/minimax-m2.5", endpoint=MODEL_ENDPOINTS["minimax/minimax-m2.5"]),
                ModelConfig(name="minimax/minimax-m2.1", endpoint=MODEL_ENDPOINTS["minimax/minimax-m2.1"]),
                ModelConfig(name="qwen/qwen-3.5", endpoint=MODEL_ENDPOINTS["qwen/qwen-3.5"]),
            ]
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if not self.api_key:
            errors.append("CANOPYWAVE_API_KEY is required")
        return errors


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Reload configuration from environment."""
    global _config
    load_dotenv(override=True)
    _config = Config()
    return _config
