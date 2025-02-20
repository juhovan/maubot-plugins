from openai import OpenAI
from typing import Dict, List, Optional, Any
import json
import logging
import requests
from functools import lru_cache
import asyncio  # new import

class OpenRouterClient:
    def __init__(self, api_key: str, site_url: str, site_name: str, config: dict):
        """Initialize the OpenRouter client with the necessary configuration."""
        self.log = logging.getLogger("maubot.chatgpt.client")
        self.log.setLevel(logging.DEBUG)
        self.log.info("Initializing OpenRouter client")
        self.api_key = api_key
        self.config = config
        self._capabilities_cache = {}  # In-memory cache for model capabilities
        self._pricing_cache = {}  # In-memory cache for model pricing
        self._all_models = None   # Cache for all models

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_name
            }
        )

    def _get_cache_key(self, model: str) -> str:
        """Generate a cache key for model capabilities."""
        return model

    def check_model_capabilities(self, model: str) -> Dict[str, bool]:
        """Check model capabilities using OpenRouter's API with caching.

        Args:
            model: The model identifier (e.g., "openai/gpt-4", "anthropic/claude-3-sonnet")

        Returns:
            Dictionary of capabilities (e.g., {"tools": True})
        """
        cache_key = self._get_cache_key(model)

        # Check in-memory cache first
        if cache_key in self._capabilities_cache:
            self.log.debug(f"Cache hit for model capabilities: {model}")
            return self._capabilities_cache[cache_key]

        self.log.debug(f"Cache miss for model capabilities: {model}")
        try:
            self.log.debug(f"Checking capabilities for model: {model}")
            response = requests.get(
                f"https://openrouter.ai/api/v1/models/{model}/endpoints",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
            endpoint_data = response.json()

            # Log endpoint information for debugging
            self.log.debug(f"Endpoint info: {json.dumps(endpoint_data, indent=2)}")

            # Check if any endpoint supports tools
            supports_tools = False
            if "data" in endpoint_data and "endpoints" in endpoint_data["data"]:
                for endpoint in endpoint_data["data"]["endpoints"]:
                    if "supported_parameters" in endpoint and "tools" in endpoint["supported_parameters"]:
                        supports_tools = True
                        break

            self.log.debug(f"Model {model} tools support: {supports_tools}")

            # Cache the result
            capabilities = {"tools": supports_tools}
            self._capabilities_cache[cache_key] = capabilities
            self.log.debug(f"Cached capabilities for {model}")

            return capabilities

        except requests.exceptions.RequestException as e:
            self.log.error(f"Error checking model capabilities: {str(e)}", exc_info=True)
            if e.response is not None and e.response.status_code == 404:
                # If we get a 404, the model doesn't exist or doesn't support tools
                capabilities = {"tools": False}
                self._capabilities_cache[cache_key] = capabilities
                return capabilities
            # For other errors, default to no capabilities but don't cache
            return {"tools": False}
        except Exception as e:
            self.log.error(f"Unexpected error checking model capabilities for model {model}: {str(e)}", exc_info=True)
            raise OpenRouterError(f"Model {model} not found due to error: {str(e)}")

    def check_model_pricing(self, model: str) -> Dict[str, bool]:
        """Check if model's price is within allowed limits.

        Args:
            model: The model identifier (e.g., "openai/gpt-4", "anthropic/claude-3-sonnet")

        Returns:
            Dictionary with pricing info and whether model is allowed
        """
        cache_key = self._get_cache_key(model)

        # Check in-memory cache first
        if cache_key in self._pricing_cache:
            self.log.debug(f"Cache hit for model pricing: {model}")
            return self._pricing_cache[cache_key]

        self.log.debug(f"Cache miss for model pricing: {model}")
        try:
            self.log.debug(f"Checking pricing for model: {model}")
            response = requests.get(
                f"https://openrouter.ai/api/v1/models/{model}/endpoints",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
            endpoint_data = response.json()

            # Log endpoint information for debugging
            self.log.debug(f"Endpoint info: {json.dumps(endpoint_data, indent=2)}")

            # Get the lowest prompt price from all endpoints
            min_prompt_price = float('inf')
            if "data" in endpoint_data and "endpoints" in endpoint_data["data"]:
                for endpoint in endpoint_data["data"]["endpoints"]:
                    if "pricing" in endpoint and "prompt" in endpoint["pricing"]:
                        try:
                            price = float(endpoint["pricing"]["prompt"])
                            min_prompt_price = min(min_prompt_price, price)
                        except (ValueError, TypeError):
                            continue

            # Check if price is within allowed limit
            max_price = self.config.get("max_price_per_token", 0.000005)
            is_allowed = min_prompt_price <= max_price

            self.log.debug(f"Model {model} price: {min_prompt_price}, allowed: {is_allowed}")

            # Cache the result
            result = {
                "price_per_token": min_prompt_price,
                "is_allowed": is_allowed
            }
            self._pricing_cache[cache_key] = result
            self.log.debug(f"Cached pricing for {model}")

            return result

        except requests.exceptions.RequestException as e:
            self.log.error(f"Error checking model pricing: {str(e)}", exc_info=True)
            if e.response is not None and e.response.status_code == 404:
                # If we get a 404, the model doesn't exist
                result = {"price_per_token": float('inf'), "is_allowed": False}
                self._pricing_cache[cache_key] = result
                return result
            # For other errors, default to not allowed but don't cache
            return {"price_per_token": float('inf'), "is_allowed": False}
        except Exception as e:
            self.log.error(f"Unexpected error checking model pricing: {str(e)}", exc_info=True)
            # Default to not allowed if check fails, but don't cache
            return {"price_per_token": float('inf'), "is_allowed": False}

    def clear_caches(self) -> None:
        """Clear all caches."""
        self.log.info("Clearing all caches")
        self._capabilities_cache.clear()
        self._pricing_cache.clear()

    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
        include_reasoning: bool = False,
        logprobs: bool = False,
    ) -> Any:
        """
        Create a chat completion using the OpenRouter API.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: The model identifier (e.g., "openai/gpt-4", "anthropic/claude-3-sonnet")
            temperature: Controls randomness in responses
            max_tokens: Maximum tokens in the response
            tools: Optional list of function tools
            tool_choice: Optional tool choice configuration
            stream: Optional flag to enable streaming responses

        Returns:
            The API response as a dictionary or an async generator for streaming

        Raises:
            OpenRouterError: If the model is not allowed or other API errors occur
        """
        try:
            self.log.info(f"Creating chat completion with model: {model}")

            # Check if model is allowed based on pricing
            pricing_info = self.check_model_pricing(model)
            if not pricing_info["is_allowed"]:
                raise OpenRouterError(f"Model {model} exceeds maximum allowed price per token ({pricing_info['price_per_token']} > {self.config.get('max_price_per_token', 0.000005)})")

            # Check if model supports tools before including them
            capabilities = self.check_model_capabilities(model)
            if tools and not capabilities["tools"]:
                self.log.debug(f"Model {model} does not support tools, excluding them from request")
                tools = None

            # Prepare the request parameters
            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "extra_body": {"include_reasoning": include_reasoning, "logprobs": logprobs},
            }

            # Add optional parameters if provided
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            if tools is not None:
                params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
            if stream:
                params["stream"] = True

            self.log.debug(f"Request parameters: {json.dumps(params, indent=2)}")

            # Make the API call
            self.log.debug("Making API call to OpenRouter")
            response = self.client.chat.completions.create(**params)

            if stream:
                # Wrap synchronous iterator into an async generator
                async def async_stream():
                    for chunk in response:
                        yield chunk
                return async_stream()
            else:
                try:
                    self.log.debug(f"Raw response type: {type(response)}")
                    raw_response = response.model_dump()
                    self.log.debug(f"Raw response dump: {json.dumps(raw_response, indent=2)}")
                except Exception as dump_error:
                    self.log.error(f"Error dumping response: {dump_error}")
                    self.log.debug(f"Raw response: {response}")
                response_dict = json.loads(response.model_dump_json())
                self.log.debug(f"Processed response: {json.dumps(response_dict, indent=2)}")
                if not response_dict.get("choices"):
                    self.log.error(f"No choices in response. Full response: {json.dumps(response_dict, indent=2)}")
                    raise OpenRouterError(f"Model {model} returned no choices in response. This might indicate an issue with the model or the API.")
                return response_dict

        except Exception as e:
            self.log.error(f"OpenRouter API Error: {str(e)}", exc_info=True)
            raise OpenRouterError(f"OpenRouter API Error with {model}: {str(e)}")

    def fetch_all_models(self) -> dict:
        """Fetch and cache all models from OpenRouter API."""
        if self._all_models is None:
            self.log.debug("Fetching all models from OpenRouter")
            try:
                response = requests.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                response.raise_for_status()
                self._all_models = response.json()  # Expecting {"data": [ ... ]}
            except Exception as e:
                self.log.error(f"Error fetching all models: {str(e)}", exc_info=True)
                self._all_models = {"data": []}
        return self._all_models

class OpenRouterError(Exception):
    """Custom exception for OpenRouter API errors."""
    pass
