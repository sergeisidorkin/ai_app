# asgi.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import office_addin.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(office_addin.routing.websocket_urlpatterns)
    ),
})