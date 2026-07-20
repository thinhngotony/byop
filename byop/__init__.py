"""byop: interactive setup of custom LLM providers for the Zed editor."""

from .core.apply import apply_provider, default_model_capabilities
from .core.config import ModelConfig, ProviderConfig

__all__ = [
    "ProviderConfig",
    "ModelConfig",
    "apply_provider",
    "default_model_capabilities",
]
__version__ = "1.0.0"
