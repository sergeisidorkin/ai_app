import os

# Если переменная DJANGO_ENV=prod — грузим prod, иначе local.
if os.environ.get("DJANGO_ENV") == "prod":
    from .prod import *  # noqa
else:
    from .local import *  # noqa