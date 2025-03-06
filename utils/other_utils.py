"""Utility functions for the application."""
from configs.constants import AVAILABLE_LANGUAGES_LITERAL, AVAILABLE_LANGUAGES_LIST

def check_language_availability(language_code: str) -> AVAILABLE_LANGUAGES_LITERAL:
    """Check if a language code is available in the supported languages list.
    
    Args:
        language_code (str): The language code to check.
        
    Returns:
        Literal['en', 'fa']: The validated language code. Returns 'en' if the input is not supported.
    """
    global AVAILABLE_LANGUAGES_LIST
    return language_code if language_code in AVAILABLE_LANGUAGES_LIST else 'en'