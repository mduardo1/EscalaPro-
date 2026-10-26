"""Encaminhamento restrito ao peer e aos saltos configurados."""

from ipaddress import ip_address
from werkzeug.middleware.proxy_fix import ProxyFix


class TrustedProxy:
    def __init__(self, app, networks, hops, proto_hops=None):
        proto_hops = hops if proto_hops is None else proto_hops
        self.app, self.networks, self.hops = app, networks, max(hops, proto_hops)
        self.forwarded = ProxyFix(
            app, x_for=hops, x_proto=proto_hops, x_host=0, x_port=0, x_prefix=0
        )

    def __call__(self, environ, start_response):
        try:
            peer = ip_address(environ.get("REMOTE_ADDR", ""))
            trusted = self.hops > 0 and any(
                peer in network for network in self.networks
            )
        except ValueError:
            trusted = False
        if not trusted:
            for key in list(environ):
                if key.startswith("HTTP_X_FORWARDED_") or key == "HTTP_FORWARDED":
                    environ.pop(key)
            return self.app(environ, start_response)
        return self.forwarded(environ, start_response)
