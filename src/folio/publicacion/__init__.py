"""Publicación en Instagram (Fase 4, adelantada a petición del usuario el 31/10).

- enlaces: URL públicas firmadas y con caducidad para que Instagram descargue las imágenes (la web
  pide contraseña; solo /api/publico/ queda abierto, y solo con firma válida).
- preparar: la pieza en su versión actual (la de la web, con las ediciones) → JPEG de cada diapositiva,
  portada en vídeo si tiene imagen y el texto del pie con los créditos.
- instagram: cliente de la API de Instagram con login de Instagram (graph.instagram.com).

Nada se publica solo: hace falta una pieza «aprobada» y confirmarlo de forma explícita.
"""
