import os
import requests
from dotenv import load_dotenv
from typing import Dict, Any


# Load environment variables from .env file
load_dotenv()


class LLM:
    """Interface to interact with GWDG's LLM service.
    
    This class provides a wrapper around the OpenAI-compatible API
    provided by GWDG (German Academic Cloud).
    """
    
    def __init__(self, model: str = None):
        """Initialize the LLM class.
        
        Args:
            model (str, optional): The name of the model to use. 
                                  If None, uses AGENT_LLM_MODEL from .env
        """
        # Use provided model or fall back to environment variable
        self.model = model or os.getenv("AGENT_LLM_MODEL", "openai-gpt-oss-120b")
        
        # Number of retry attempts for API calls
        self.retries = 3
        
        # Timeout in seconds for API calls
        self.timeout = 10
        
        # Get API endpoint from environment variables
        self.base_url = os.getenv("GWDG_MODEL_URL", "https://chat-ai.academiccloud.de/v1")
        
        # Get API key from environment variables
        self.api_key = os.getenv("GWDG_MODEL_API_KEY", "")
        
        # Build reusable headers for all requests
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Default system prompt that defines the LLM's behavior
        self.system_prompt = "You are a useful and helpful assistant."
    
    def send_request(self, query: str) -> str:
        """Send a request to the GWDG LLM service and get a response.
        
        Args:
            query (str): The user's query to send to the LLM
            
        Returns:
            str: The LLM's response text or an error message
        """
        # Try multiple times based on self.retries
        for attempt in range(self.retries):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": query}
                    ],
                    "temperature": 0.2,
                }
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract and return the response content
                result = data["choices"][0]["message"]["content"]
                return result
                
            except Exception as e:
                # Log error and retry
                print(f"Error communicating with GWDG LLM (attempt {attempt + 1}/{self.retries}): {str(e)}")
                if attempt == self.retries - 1:
                    # Return error message if all retry attempts fail
                    return f"Error: API call failed after {self.retries} attempts: {str(e)}"
    
    def chat(self, prompt: str) -> Dict[str, Any]:
        """Send a chat request to the GWDG LLM API.
        
        This method is an alias for send_request to maintain compatibility.
        
        Args:
            prompt (str): The user's prompt to send to the LLM.
            
        Returns:
            Dict[str, Any]: The LLM's response as a dictionary.
        """
        response_text = self.send_request(prompt)
        return {"content": response_text}
    
    def test_connection(self) -> bool:
        """Test the connection to the GWDG service.
        
        Returns:
            bool: True if connection is successful
            
        Raises:
            RuntimeError: If connection fails or the model is not available
        """
        try:
            # Get a list of available models from the API
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract the model IDs
            available_model_ids = [m["id"] for m in data.get("data", [])]
            
            # Check if the requested model is available
            if self.model in available_model_ids:
                print(f"✓ GWDG LLM connection successful for model: {self.model}")
                return True
            else:
                raise RuntimeError(
                    f"Model '{self.model}' not found. Available models: {available_model_ids}"
                )
        except Exception as e:
            raise RuntimeError(f"Failed to connect to GWDG LLM: {str(e)}")
    
    def set_system_prompt(self, prompt: str) -> None:
        """Update the system prompt used for all requests.
        
        Args:
            prompt (str): The new system prompt
        """
        self.system_prompt = prompt


# Create a singleton instance for easy access
llm = LLM()
