"""
Gemini LLM Service
------------------
This file replaces the llm_ollama.py service.
It correctly calls the Google Gemini API using the specified model
and asynchronous requests with httpx.
"""

import os
import httpx
import logging
from typing import List, Dict, Optional

log = logging.getLogger("backend")

# --- Configuration ---
# Make sure your .env file has GEMINI_API_KEY="your_key_here"
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    log.warning("⚠️ GEMINI_API_KEY not found in .env file. LLM calls will fail.")
    # Provide a dummy key if not found, to prevent crashes, but log errors.

# --- FIX: Use the correct Gemini 2.5 Flash model ---
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"

# Use a persistent async client for connection pooling
client = httpx.AsyncClient(timeout=30.0)

class LLMService:
    """
    Wrapper for making asynchronous calls to the Gemini API.
    """

    def __init__(self):
        if API_KEY == "DUMMY_KEY_NOT_SET":
            log.error("LLMService initialized, but GEMINI_API_KEY is missing!")
        log.info(f"LLMService initialized for model: {MODEL_NAME}")

    async def answer(self, system_prompt: str) -> str:
        """
        Sends a prompt to the Gemini API and returns the text response.
        
        Args:
            system_prompt (str): The full prompt (including RAG context)
                                 to send to the model.
        
        Returns:
            str: The model's text response.
        """
        if API_KEY == "DUMMY_KEY_NOT_SET":
            log.error("Cannot call Gemini API: API Key is not set.")
            return "Error: The LLM service is not configured. (Missing API Key)"

        # The new RAG prompt builder creates one big prompt.
        # We send this as a simple "user" query.
        payload = {
            "contents": [{
                "parts": [{"text": system_prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.9,
                "maxOutputTokens": 1024,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        }

        try:
            response = await client.post(API_URL, json=payload)

            # Handle API errors
            response.raise_for_status() 

            result = response.json()
            
            if "candidates" in result:
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            elif "error" in result:
                log.error(f"Gemini API returned an error: {result['error']}")
                return f"Error from LLM: {result['error']['message']}"
            else:
                log.warning(f"Gemini API returned an unexpected response: {result}")
                return "Error: Received an unexpected response from the LLM."

        except httpx.HTTPStatusError as e:
            log.error(f"⚠️ Gemini API call failed: {e.response.status_code} {e.response.text}")
            if e.response.status_code == 404:
                return f"Error: API call failed (404 Not Found). Is the model name '{MODEL_NAME}' correct?"
            if e.response.status_code == 400:
                 return f"Error: API call failed (400 Bad Request). Check prompt for safety issues. {e.response.text}"
            if e.response.status_code == 429:
                return "Error: The AI service is currently overloaded. Please try again in a moment."
            return f"Error: An API error occurred ({e.response.status_code})."
        except Exception as e:
            log.exception(f"An unexpected error occurred during the LLM call: {e}")
            return "Error: An unexpected error occurred while contacting the AI."

    @staticmethod
    async def format_compatibility_summary(part_info: Dict, model_hint: Optional[str], llm_instance: "LLMService") -> str:
        """
        Uses the LLM to generate a clean, human-readable summary for a compatibility check.
        """
        if not llm_instance:
            return "Error: LLM service is not available."

        # Create a mini-prompt specifically for this task
        prompt = f"""
You are a parts expert. A user wants to know if a part fits their model.
Based on the data, give a simple 1-2 sentence answer.

Part Data: {part_info}
User's Model Hint: {model_hint or "Not provided"}

If the model_hint is in the "compatible_models" list, say it's a confirmed fit.
If not, state that the part is compatible with models like [list 1-2 from the list] and ask them to verify their full model number.
"""
        return await llm_instance.answer(prompt)
