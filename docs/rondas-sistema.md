# Rondas de mejora del sistema

Bucle de mejora pedido por el usuario: una mejora por ronda, rotando las áreas (a) velocidad, (b) coste,
(c) fiabilidad, (d) seguridad, (e) dirección de arte y render, (f) web. Para a las 5 rondas o cuando una ronda
no encuentra nada que valga la pena. Los cambios visibles de diseño o producto no se implementan: se preparan
las opciones en un Artifact para que el usuario elija.

| Ronda | Área | Mejora | Tipo | Probado | Coste |
|---|---|---|---|---|---|
| 1 | (a) velocidad | Hechos y arte a la vez en «Proceder» | interna, hecha | sí (test + llamada real a Haiku) | 0,0016 $ |

Gasto acumulado del bucle: **0,0016 $** (tope: 3 $).

---

## Ronda 1 · (a) Velocidad y paralelización

**Limitación del entorno**: en esta sesión no hay `data/` ni `informes/` (están fuera de git, en el volumen de
Railway), así que no hay líneas `TIEMPO:` ni trazas reales que leer. La revisión se hizo sobre el código y se
midió con una llamada real.

**Qué encontré**

- `Pipeline.desarrollar` (`src/folio/pipeline.py`, «Proceder» en la web) hacía, una detrás de otra:
  textos → guion → `comprobar_hechos([pieza])` → `dirigir_arte(…)`. La comprobación de hechos (Haiku) solo
  escribe `pieza.hechos`, y la dirección de arte no la lee (en `arte.py` y `imagenes/` no hay ninguna
  referencia a `pieza.hechos`; solo el docstring dice «después de la comprobación de hechos»). Eran dos
  esperas independientes en serie.
- Medido de verdad: una comprobación de hechos con Haiku sobre un guion corto de prueba (`tests/datos.py`)
  tarda **11,9 s** (traza `hechos:prueba-ronda1`, 0,0016 $). Con los 3–5 textos de una pieza real, más.
  La dirección de arte tarda bastante más (director, búsquedas de Europeana, hoja de contactos, a veces Flux
  o Magnific), así que en paralelo la comprobación queda tapada entera.
- Otros candidatos vistos y descartados para esta ronda:
  - `_cubiertas_de` en la mesa de madrugada busca las cubiertas en serie (unas 12 búsquedas). Se ganaría
    tiempo de madrugada, pero nadie lo espera (la mesa está lista a las 5:30) y toca la caché de cubiertas
    desde varios hilos: más riesgo, menos impacto.
  - `dirigir_arte` va pieza a pieza a propósito (no repetir imagen ni composición): no se toca.
  - Los textos del guion van en serie porque el modelo de embeddings no se comparte entre hilos: no se toca.

**Por qué esta**: es lo que el usuario espera con el botón delante («me tiltea lo lento que es»), el cambio
es de diez líneas y no altera ningún resultado, solo el orden en el tiempo.

**Qué se hizo** (arreglo interno)

- `desarrollar` lanza `comprobar_hechos(..., anunciar=False)` en un hilo y dirige el arte en el principal;
  espera a los dos antes de devolver la pieza (y propaga cualquier excepción inesperada como antes).
- `anunciar=False`: la comprobación no escribe líneas `ETAPA:` en «Proceder» (si no, la web enseñaría
  «Comprobando hechos (1 de 1)» mientras el arte sigue). Las etapas de la madrugada no cambian.
- Los dos hilos filtran y añaden avisos en `pieza.avisos`: ahora bajo un cerrojo (`Pipeline._avisos_pieza`)
  para que un filtrado no pise al otro.
- Los textos ya están congelados cuando se comprueba (los guardó `_textos`), así que el hilo de los hechos
  no carga el modelo de embeddings.

**Antes / después**

- Test `test_proceder_comprueba_hechos_a_la_vez_que_el_arte` (hechos y arte simulados de 0,5 s cada uno,
  los dos fallando): con el código anterior tarda **1,02 s** y falla; con el nuevo, ~0,5 s y pasa, con los
  avisos de los dos fallos en la pieza.
- En producción: «Proceder» debería tardar lo que tarde la comprobación de hechos menos (≥ 12 s por pieza).
  **No se ha medido en Railway**: hay que mirar las líneas `TIEMPO:` de `data/desarrollos/<pieza>.log` del
  próximo «Proceder» (desaparece la etapa «Comprobando hechos» y «Dirección de arte» no debería crecer).

**Cómo se probó**: `uv run pytest` (353 en verde); el test nuevo falla con el código viejo; una llamada
real a Haiku para medir la comprobación.

**Coste**: 0,0016 $.

**Pendiente**: medir el ahorro real en Railway tras el próximo merge (lo decide el usuario); valorar las
cubiertas en paralelo en la mesa si los `TIEMPO:` de madrugada lo justifican.
