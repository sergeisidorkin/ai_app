from .base import *

DEBUG = True
READ_DOTENV = True  # читаем .env локально

OPENAI_FILTER_MODELS = False
OPENAI_ALLOWED_PREFIXES = ("gpt-4", "gpt-4o", "o4")

# WhiteNoise в dev, чтобы статика работала под Daphne
WHITENOISE_AUTOREFRESH = True       # авто-перечитывать файлы без collectstatic
WHITENOISE_USE_FINDERS = True       # искать статику через finders в DEBUG