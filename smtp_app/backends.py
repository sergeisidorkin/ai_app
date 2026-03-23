import ssl

from django.core.mail.backends.smtp import EmailBackend
from django.utils.functional import cached_property


class ExternalSMTPEmailBackend(EmailBackend):
    def __init__(self, *args, skip_tls_verify=False, **kwargs):
        self.skip_tls_verify = bool(skip_tls_verify)
        super().__init__(*args, **kwargs)

    @cached_property
    def ssl_context(self):
        ssl_context = super().ssl_context
        if self.skip_tls_verify:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
