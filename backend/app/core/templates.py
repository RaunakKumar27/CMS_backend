import os
import re
from datetime import datetime
from fastapi.templating import Jinja2Templates

# Dynamic resolution of templates folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates_dir = os.path.join(BASE_DIR, "templates")
if not os.path.exists(templates_dir):
    templates_dir = os.path.join(os.path.dirname(BASE_DIR), "templates")

templates = Jinja2Templates(directory=templates_dir)

def strftime_filter(value, format_str="%b %d, %Y"):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return value
    return value.strftime(format_str)

def truncate_words_filter(text, num_words=25):
    if not text:
        return ""
    # Strip HTML tags
    clean_text = re.sub('<[^<]+?>', '', str(text))
    words = clean_text.split()
    if len(words) <= num_words:
        return clean_text
    return " ".join(words[:num_words]) + "..."

templates.env.filters["strftime"] = strftime_filter
templates.env.filters["truncate_words"] = truncate_words_filter
