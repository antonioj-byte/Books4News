"""Descargas de URLs que Folio no controla (ronda 4 de mejora, seguridad).

Los enlaces de «Proponer un tema», las URLs que trae la búsqueda web (prensa del libro, nevera, fuentes de los temas)
y las páginas de las noticias se descargan desde el servicio «api», que escucha sin contraseña en su contenedor y en la
red privada de Railway (la contraseña la pone la web). Una página puede redirigir a `http://localhost:8000/api/…` o a
otro servicio interno, y lo que devuelva entraría en el guion como si fuera una fuente. Este gancho rechaza cada
petición, también las de las redirecciones, cuyo destino no sea una dirección pública de internet.
"""

from __future__ import annotations

import ipaddress
import socket

import httpx


class DestinoNoPermitido(httpx.RequestError):
    """La URL (o una redirección) apunta a una dirección que no es pública: localhost, red privada, etc."""


def _ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        return [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        pass
    try:
        return [ipaddress.ip_address(x[4][0].split("%")[0]) for x in socket.getaddrinfo(host, None)]
    except (socket.gaierror, UnicodeError, ValueError):
        return []          # sin resolver, no hay conexión directa posible; httpx fallará por su cuenta


def es_publica(host: str) -> bool:
    """Si el nombre o la IP solo lleva a direcciones públicas de internet."""
    if not host or host.lower() == "localhost" or host.lower().endswith((".localhost", ".internal", ".local")):
        return False
    return all(ip.is_global and not ip.is_multicast for ip in _ips(host))


def solo_publicas(request: httpx.Request) -> None:
    """Gancho `request` de httpx: se llama antes de cada petición, también en cada redirección."""
    if not es_publica(request.url.host):
        raise DestinoNoPermitido(f"destino no permitido: {request.url.host}", request=request)


def cliente_externo(**kw) -> httpx.Client:
    """`httpx.Client` para URLs de fuera, con el gancho `solo_publicas`."""
    ganchos = kw.pop("event_hooks", {}) or {}
    ganchos = {**ganchos, "request": [solo_publicas, *ganchos.get("request", [])]}
    return httpx.Client(event_hooks=ganchos, **kw)
