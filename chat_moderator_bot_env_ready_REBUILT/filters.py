import re
from config import BANNED_WORDS

def has_profanity(text: str) -> bool:
    return any(word in text.lower() for word in BANNED_WORDS)

def has_link(text: str) -> bool:
    return bool(re.search(r"(https?://|t\.me/|@\w+|www\.)", text))
