from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # ws://127.0.0.1:8001/ws/addin/user/<email>/
    re_path(r"^ws/addin/user/(?P<email>[^/]+)/$", consumers.AddinConsumer.as_asgi()),
]