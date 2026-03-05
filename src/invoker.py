"""
API Invoker for CanopyWave Model API.

Handles HTTP requests with retry logic, timeout handling, and latency measurement.
"""

import time
import httpx
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from .config import get_config, get_model_endpoint


@dataclass
class InvokeResult:
    """Result of a model API invocation."""
    success: bool
    latency: float  # seconds
    response: Optional[Dict[str, Any]] = None
    content: str = ""
    error: Optional[str] = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelInvoker:
    """
    Invokes CanopyWave model API with retry logic and metrics collection.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        config = get_config()
        self.api_key = api_key or config.api_key
        self.timeout = config.timeout
        self.max_retries = config.max_retries
        
    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
    
    def _build_payload(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        messages: List[Dict[str, str]] = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    
    def invoke(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> InvokeResult:
        """
        Invoke the model API and return result with metrics.
        
        Args:
            prompt: User prompt to send
            model: Model name (defaults to config default)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            
        Returns:
            InvokeResult with response data and metrics
        """
        config = get_config()
        model = model or config.default_model
        
        url = get_model_endpoint(model)
        headers = self._build_headers()
        payload = self._build_payload(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        
        last_error: Optional[str] = None
        
        for attempt in range(self.max_retries):
            try:
                start_time = time.perf_counter()
                
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, json=payload, headers=headers)
                
                latency = time.perf_counter() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    content = ""
                    
                    # Extract content from response
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            content = choice["message"]["content"]
                    
                    # Extract token usage
                    usage = data.get("usage", {})
                    
                    return InvokeResult(
                        success=True,
                        latency=latency,
                        response=data,
                        content=content,
                        model=model,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                    )
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    
            except httpx.TimeoutException:
                latency = time.perf_counter() - start_time
                last_error = f"Request timeout after {latency:.2f}s"
                
            except httpx.RequestError as e:
                latency = time.perf_counter() - start_time
                last_error = f"Request error: {str(e)}"
            
            except Exception as e:
                latency = time.perf_counter() - start_time
                last_error = f"Unexpected error: {str(e)}"
        
        # All retries failed
        return InvokeResult(
            success=False,
            latency=latency if 'latency' in locals() else 0,
            error=last_error,
            model=model,
        )
    
    def invoke_multi_model(
        self,
        prompt: str,
        models: List[str],
        **kwargs
    ) -> Dict[str, InvokeResult]:
        """
        Invoke multiple models with the same prompt.
        
        Args:
            prompt: User prompt
            models: List of model names
            **kwargs: Additional arguments for invoke()
            
        Returns:
            Dict mapping model name to InvokeResult
        """
        results = {}
        for model in models:
            results[model] = self.invoke(prompt, model=model, **kwargs)
        return results


# Convenience function
def call_model(
    prompt: str,
    model: Optional[str] = None,
    **kwargs
) -> Tuple[float, Dict[str, Any]]:
    """
    Simple function to call model API.
    
    Returns:
        Tuple of (latency_seconds, response_dict)
    """
    invoker = ModelInvoker()
    result = invoker.invoke(prompt, model=model, **kwargs)
    
    if result.success:
        return result.latency, result.response or {}
    else:
        return result.latency, {"error": result.error}
