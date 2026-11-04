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
MAX_PIE_LINKEDIN = 3000   # y LinkedIn
MAX_IMAGENES_LINKEDIN = 9 # LinkedIn no mezcla vídeo e imágenes: va el carrusel en imágenes, como mucho nueve
REDES = ("instagram", "linkedin")
NOMBRE_RED = {"instagram": "Instagram", "linkedin": "LinkedIn"}

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

    def canal_de(self, red: str, canal: str | None = None) -> dict:
        """El canal de una red («instagram» o «linkedin», 3/11): el indicado (BUFFER_CHANNEL_ID,
        BUFFER_LINKEDIN_CHANNEL_ID) o el único de esa red en la cuenta."""
        todos = [c for o in self.organizaciones() for c in self.canales(o["id"])]
        if canal:
            elegido = [c for c in todos if c["id"] == canal]
        else:
            elegido = [c for c in todos if str(c.get("service", "")).lower() == red]
        if len(elegido) != 1:
            variable = "BUFFER_CHANNEL_ID" if red == "instagram" else "BUFFER_LINKEDIN_CHANNEL_ID"
            nombre = NOMBRE_RED.get(red, red)
            raise ErrorBuffer(f"{'No encuentro el canal ' + canal if canal else 'Hay ' + str(len(elegido)) + ' canales de ' + nombre}"
                              f" en Buffer: conecta el de Folio o fija {variable}")
        return elegido[0]

    def canal_instagram(self, canal: str | None = None) -> dict:
        return self.canal_de("instagram", canal)

    def valores(self, enum: str) -> list[str]:
        """Valores de un enum del esquema (introspección, solo lectura), para comprobar los que usamos."""
        tipo = self.consulta(_ENUM, {"nombre": enum}).get("__type") or {}
        return [v["name"] for v in tipo.get("enumValues") or []]

    # --- Escritura ---------------------------------------------------------------

    @staticmethod
    def entrada(canal: str, pie: str, medios: list[tuple[str, str]], cuando: datetime | None,
                borrador: bool = False, red: str = "instagram") -> dict:
        """CreatePostInput del carrusel: `medios` son («imagen» o «video», URL pública) en orden; sin
        `cuando`, a la cola de Buffer. Con `borrador`, se guarda en los borradores de Buffer y no se publica.
        En LinkedIn (3/11), solo imágenes (no mezcla vídeo e imágenes), de 1 a 9, y sin metadatos de Instagram; o,
        desde el 4/11, un documento: `medios` = [(«documento», URL del PDF, URL de la portada, título)], que LinkedIn
        enseña como un carrusel que se pasa página a página."""
        if red == "linkedin" and medios and medios[0][0] == "documento":
            if len(medios) != 1 or len(medios[0]) != 4:
                raise ErrorBuffer("Un documento de LinkedIn va solo: el PDF, su portada y un título")
            if len(pie) > MAX_PIE_LINKEDIN:
                raise ErrorBuffer(f"El pie tiene {len(pie)} caracteres; LinkedIn admite {MAX_PIE_LINKEDIN}")
            _, url, portada, titulo = medios[0]
            entrada = {"channelId": canal, "text": pie, "schedulingType": "automatic",
                       "assets": [{"document": {"url": url, "thumbnailUrl": portada, "title": titulo[:120]}}]}
            return Buffer._cuando(entrada, cuando, borrador)
        if red == "linkedin":
            if any(t == "video" for t, _ in medios):
                raise ErrorBuffer("LinkedIn no mezcla vídeo e imágenes: el carrusel va en imágenes")
            if not 1 <= len(medios) <= MAX_IMAGENES_LINKEDIN:
                raise ErrorBuffer(f"Una publicación de LinkedIn lleva de 1 a {MAX_IMAGENES_LINKEDIN} imágenes, no {len(medios)}")
            if len(pie) > MAX_PIE_LINKEDIN:
                raise ErrorBuffer(f"El pie tiene {len(pie)} caracteres; LinkedIn admite {MAX_PIE_LINKEDIN}")
        else:
            if not 2 <= len(medios) <= 10:
                raise ErrorBuffer(f"Un carrusel de Instagram lleva de 2 a 10 archivos, no {len(medios)}")
            if len(pie) > MAX_PIE:
                raise ErrorBuffer(f"El pie tiene {len(pie)} caracteres; Instagram admite {MAX_PIE}")
        entrada = {
            "channelId": canal, "text": pie, "schedulingType": "automatic",
            "assets": [{"video" if tipo == "video" else "image": {"url": url}} for tipo, url in medios],
        }
        if red == "instagram":
            entrada["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": True}}
        return Buffer._cuando(entrada, cuando, borrador)

    @staticmethod
    def _cuando(entrada: dict, cuando: datetime | None, borrador: bool) -> dict:
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
                  borrador: bool = False, red: str = "instagram") -> dict:
        """Programa el carrusel (o lo deja en borradores). Devuelve el post de Buffer ({id, dueAt, assets})."""
        datos = self.consulta(_CREAR, {"input": self.entrada(canal, pie, medios, cuando, borrador, red)}).get("createPost") or {}
        if "post" not in datos:
            raise ErrorBuffer(self._limpio(f"Buffer no programó el carrusel: {datos.get('message', 'sin respuesta')}"))
        return datos["post"]
