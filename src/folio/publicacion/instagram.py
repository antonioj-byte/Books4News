"""Cliente de la API de Instagram con login de Instagram (graph.instagram.com), para la cuenta de Folio.

Publicar un carrusel son cuatro pasos: un contenedor por diapositiva (imagen JPEG o vídeo, con
is_carousel_item), esperar a que Instagram los procese (status_code FINISHED), el contenedor del
carrusel con los hijos y el pie, y media_publish. Instagram descarga cada archivo de su URL pública en
ese momento (folio.publicacion.enlaces). Instagram no programa: la hora la decide quien publica.

El token (INSTAGRAM_TOKEN, permisos instagram_business_basic e instagram_business_content_publish) va
como access_token, así que todo mensaje de error se limpia antes de salir. Ante 403, 429, límite de
publicaciones (códigos 4, 17, 32, 613) o token caducado (190) no se reintenta: se para y se avisa.
"""

from __future__ import annotations

import time

import httpx

BASE = "https://graph.instagram.com"
VERSION = "v26.0"
ESPERA_S = 10.0           # entre consultas del estado de un contenedor (los tests la ponen a 0)
CODIGOS_BLOQUEO = {4, 17, 32, 613}
MAX_PIE = 2200            # caracteres del pie que admite Instagram


class ErrorInstagram(Exception):
    def __init__(self, mensaje: str, bloqueo: bool = False):
        super().__init__(mensaje)
        self.bloqueo = bloqueo


class Instagram:
    def __init__(self, token: str, usuario: str | None = None, cliente: httpx.Client | None = None,
                 espera_max_s: float = 300):
        if not token:
            raise ErrorInstagram("Falta INSTAGRAM_TOKEN")
        self.token, self._usuario, self.espera_max_s = token, usuario, espera_max_s
        self.c = cliente or httpx.Client(timeout=60)

    def _limpio(self, texto: str) -> str:
        return texto.replace(self.token, "***")

    def _llamar(self, metodo: str, ruta: str, **datos) -> dict:
        url = f"{BASE}/{VERSION}/{ruta}"
        try:
            if metodo == "GET":
                r = self.c.get(url, params={**datos, "access_token": self.token})
            else:
                r = self.c.post(url, data={**datos, "access_token": self.token})
        except httpx.HTTPError as e:
            raise ErrorInstagram(self._limpio(f"Sin respuesta de Instagram ({type(e).__name__})")) from None
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = {}
        error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
        if r.status_code >= 400 or error:
            error = error or {}
            codigo = error.get("code")
            mensaje = self._limpio(f"Instagram respondió {r.status_code}"
                                   + (f" (código {codigo})" if codigo else "") + f": {error.get('message', r.text[:200])}")
            if codigo == 190:
                raise ErrorInstagram(f"El token no vale o ha caducado; genera uno nuevo. {mensaje}", bloqueo=True)
            raise ErrorInstagram(mensaje, bloqueo=r.status_code in (403, 429) or codigo in CODIGOS_BLOQUEO)
        return cuerpo

    # --- Lectura ---------------------------------------------------------------

    def cuenta(self) -> dict:
        """La cuenta conectada: {user_id, username, account_type}."""
        datos = self._llamar("GET", "me", fields="user_id,username,account_type")
        self._usuario = self._usuario or str(datos.get("user_id") or datos.get("id"))
        return datos

    @property
    def usuario(self) -> str:
        if not self._usuario:
            self.cuenta()
        return self._usuario

    def limite(self) -> tuple[int, int]:
        """(publicaciones en las últimas 24 h, máximo)."""
        datos = self._llamar("GET", f"{self.usuario}/content_publishing_limit", fields="quota_usage,config")
        fila = (datos.get("data") or [{}])[0]
        return int(fila.get("quota_usage", 0)), int((fila.get("config") or {}).get("quota_total", 0))

    # --- Publicación -----------------------------------------------------------

    def _contenedor(self, **datos) -> str:
        return self._llamar("POST", f"{self.usuario}/media", **datos)["id"]

    def esperar(self, contenedor: str) -> None:
        t0 = time.monotonic()
        while True:
            estado = self._llamar("GET", contenedor, fields="status_code").get("status_code")
            if estado in ("FINISHED", "PUBLISHED"):
                return
            if estado in ("ERROR", "EXPIRED"):
                raise ErrorInstagram(f"Instagram no pudo procesar el contenedor {contenedor} ({estado})")
            if time.monotonic() - t0 > self.espera_max_s:
                raise ErrorInstagram(f"El contenedor {contenedor} no terminó en {self.espera_max_s:.0f} s")
            time.sleep(ESPERA_S)

    def publicar_carrusel(self, medios: list[tuple[str, str]], pie: str) -> dict:
        """medios: [(«imagen» o «video», URL pública)], de 2 a 20. Devuelve {id, permalink}."""
        if not 2 <= len(medios) <= 20:
            raise ErrorInstagram(f"Un carrusel lleva de 2 a 20 diapositivas, no {len(medios)}")
        if len(pie) > MAX_PIE:
            raise ErrorInstagram(f"El pie tiene {len(pie)} caracteres; Instagram admite {MAX_PIE}")
        hijos = [self._contenedor(is_carousel_item="true", **({"media_type": "VIDEO", "video_url": url}
                                                                if tipo == "video" else {"image_url": url}))
                 for tipo, url in medios]
        for h in hijos:
            self.esperar(h)
        carrusel = self._contenedor(media_type="CAROUSEL", children=",".join(hijos), caption=pie)
        self.esperar(carrusel)
        media = self._llamar("POST", f"{self.usuario}/media_publish", creation_id=carrusel)["id"]
        try:
            permalink = self._llamar("GET", media, fields="permalink").get("permalink")
        except ErrorInstagram:
            permalink = None                     # ya está publicada: el enlace es solo un extra
        return {"id": media, "permalink": permalink}
