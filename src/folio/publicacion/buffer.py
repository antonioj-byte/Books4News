"""Cliente de la API de Buffer (GraphQL en https://api.buffer.com) para programar el carrusel de una pieza
en el Instagram de Folio conectado a Buffer (decidido el 31/10: plan gratis, sin crear app en Meta).

Una sola mutación, createPost, con el canal de Instagram, el pie, los archivos en orden (assets: imagen
o vídeo, cada uno de una URL pública) y la hora (mode customScheduled con dueAt en UTC) o la cola de
Buffer (addToQueue). Buffer descarga los archivos al publicar, no al programar: los enlaces firmados
tienen que valer hasta entonces (folio.publicacion.enlaces, con caducidad a medida).

La clave (BUFFER_API_KEY) va en la cabecera Authorization: Bearer; todo mensaje de error se limpia antes
de salir. Ante 401, 403 o 429 no se reintenta: se para y se avisa.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

URL = "https://api.buffer.com"
MAX_PIE = 2200            # caracteres del pie que admite Instagram

_CANALES = """query Canales($org: OrganizationId!) {
  channels(input: { organizationId: $org }) { id name service }
}"""
_ORGANIZACIONES = "query { account { id organizations { id name } } }"
_ENUM = 'query Enum($nombre: String!) { __type(name: $nombre) { enumValues { name } } }'
_CREAR = """mutation Crear($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt assets { id mimeType } } }
    ... on MutationError { message }
  }
}"""


class ErrorBuffer(Exception):
    def __init__(self, mensaje: str, bloqueo: bool = False):
        super().__init__(mensaje)
        self.bloqueo = bloqueo


class Buffer:
    def __init__(self, clave: str | None, cliente: httpx.Client | None = None):
        if not clave:
            raise ErrorBuffer("Falta BUFFER_API_KEY")
        self.clave = clave
        self.c = cliente or httpx.Client(timeout=60)

    def _limpio(self, texto: str) -> str:
        return texto.replace(self.clave, "***")

    def consulta(self, query: str, variables: dict | None = None) -> dict:
        try:
            r = self.c.post(URL, json={"query": query, "variables": variables or {}},
                            headers={"Authorization": f"Bearer {self.clave}", "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise ErrorBuffer(self._limpio(f"Sin respuesta de Buffer ({type(e).__name__})")) from None
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = {}
        errores = cuerpo.get("errors") if isinstance(cuerpo, dict) else None
        if r.status_code >= 400 or errores:
            detalle = "; ".join(str(e.get("message", e)) for e in errores or []) or r.text[:200]
            bloqueo = r.status_code in (401, 403, 429) or "rate limit" in detalle.lower()
            raise ErrorBuffer(self._limpio(f"Buffer respondió {r.status_code}: {detalle}"), bloqueo=bloqueo)
        return cuerpo.get("data") or {}

    # --- Lectura ---------------------------------------------------------------

    def organizaciones(self) -> list[dict]:
        return (self.consulta(_ORGANIZACIONES).get("account") or {}).get("organizations") or []

    def canales(self, organizacion: str) -> list[dict]:
        return self.consulta(_CANALES, {"org": organizacion}).get("channels") or []

    def canal_instagram(self, canal: str | None = None) -> dict:
        """El canal de Instagram: el indicado (BUFFER_CHANNEL_ID) o el único de Instagram de la cuenta."""
        todos = [c for o in self.organizaciones() for c in self.canales(o["id"])]
        if canal:
            elegido = [c for c in todos if c["id"] == canal]
        else:
            elegido = [c for c in todos if str(c.get("service", "")).lower() == "instagram"]
        if len(elegido) != 1:
            raise ErrorBuffer(f"{'No encuentro el canal ' + canal if canal else 'Hay ' + str(len(elegido)) + ' canales de Instagram'}"
                              " en Buffer: conecta el de Folio o fija BUFFER_CHANNEL_ID")
        return elegido[0]

    def valores(self, enum: str) -> list[str]:
        """Valores de un enum del esquema (introspección, solo lectura), para comprobar los que usamos."""
        tipo = self.consulta(_ENUM, {"nombre": enum}).get("__type") or {}
        return [v["name"] for v in tipo.get("enumValues") or []]

    # --- Escritura ---------------------------------------------------------------

    @staticmethod
    def entrada(canal: str, pie: str, medios: list[tuple[str, str]], cuando: datetime | None,
                borrador: bool = False) -> dict:
        """CreatePostInput del carrusel: `medios` son («imagen» o «video», URL pública) en orden; sin
        `cuando`, a la cola de Buffer. Con `borrador`, se guarda en los borradores de Buffer y no se publica."""
        if not 2 <= len(medios) <= 10:
            raise ErrorBuffer(f"Un carrusel de Instagram lleva de 2 a 10 archivos, no {len(medios)}")
        if len(pie) > MAX_PIE:
            raise ErrorBuffer(f"El pie tiene {len(pie)} caracteres; Instagram admite {MAX_PIE}")
        entrada = {
            "channelId": canal, "text": pie, "schedulingType": "automatic",
            "assets": [{"video" if tipo == "video" else "image": {"url": url}} for tipo, url in medios],
            "metadata": {"instagram": {"type": "post", "shouldShareToFeed": True}},
        }
        if cuando:
            if cuando.tzinfo is None:
                raise ErrorBuffer("La hora tiene que llevar zona horaria")
            entrada |= {"mode": "customScheduled",
                        "dueAt": cuando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        else:
            entrada["mode"] = "addToQueue"
        if borrador:
            entrada["saveToDraft"] = True
        return entrada

    def programar(self, canal: str, pie: str, medios: list[tuple[str, str]], cuando: datetime | None,
                  borrador: bool = False) -> dict:
        """Programa el carrusel (o lo deja en borradores). Devuelve el post de Buffer ({id, dueAt, assets})."""
        datos = self.consulta(_CREAR, {"input": self.entrada(canal, pie, medios, cuando, borrador)}).get("createPost") or {}
        if "post" not in datos:
            raise ErrorBuffer(self._limpio(f"Buffer no programó el carrusel: {datos.get('message', 'sin respuesta')}"))
        return datos["post"]
