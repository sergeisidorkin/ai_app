import re, json, logging
from django.utils.deprecation import MiddlewareMixin

log = logging.getLogger("runprobe")

class RunProbeMiddleware(MiddlewareMixin):
    """
    Ловит любой запрос на /blocks/.../run и пишет в лог:
    - метод/путь/qs/заголовки HTMX
    - content-type
    - «сырой» префикс тела (до 2 КБ)
    - снимки GET/POST
    """
    RX = re.compile(r"/blocks/.*/run(?:/|$)")

    def process_request(self, request):
        try:
            path = request.path
            if not self.RX.search(path):
                return None

            data = {
                "stage": "pre-view",
                "method": request.method,
                "path": path,
                "qs": request.META.get("QUERY_STRING", ""),
                "content_type": request.META.get("CONTENT_TYPE", ""),
                "hx": {
                    "HX-Request": request.headers.get("HX-Request"),
                    "HX-Trigger": request.headers.get("HX-Trigger"),
                    "HX-Target":  request.headers.get("HX-Target"),
                    "HX-Boosted": request.headers.get("HX-Boosted"),
                },
                "raw_body_prefix": (request.body[:2048].decode("utf-8", "ignore") if request.body else ""),
            }

            get_pairs  = {k: (request.GET.getlist(k) if len(request.GET.getlist(k)) > 1 else request.GET.get(k))
                          for k in request.GET.keys()}
            post_pairs = {k: (request.POST.getlist(k) if len(request.POST.getlist(k)) > 1 else request.POST.get(k))
                          for k in request.POST.keys()}

            data["GET"]  = get_pairs
            data["POST"] = post_pairs
            data["get_keys"]  = list(get_pairs.keys())
            data["post_keys"] = list(post_pairs.keys())

            log.warning("RUNPROBE %s", json.dumps(data, ensure_ascii=False, default=str))
        except Exception as e:
            log.exception("RUNPROBE failed: %s", e)
        return None