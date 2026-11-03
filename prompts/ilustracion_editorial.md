# Ilustración editorial de la pieza (Magnific, Flux 2 Pro desde texto)

El estilo de la casa para la ilustración editorial (31/10, B1 y B6 del catálogo): el lenguaje de las
revistas de ideas, una metáfora visual con un concepto fuerte, no la ilustración del suceso. El director
de arte escribe la escena (`escena`, en inglés); el código (`folio.imagenes.editorial`) le añade lo que hay
bajo la sección de estilo y lo envía. Lo que hay antes de esa sección no se envía.

Letras (2/11, a petición del usuario: «evitar esas letras de IA»): Seedream pintaba una cabecera de revista
inventada encima de la imagen y cuadros de color sueltos. El estilo ya no nombra revistas, páginas ni nada
editorial (eso lo llevaba a maquetar), describe la imagen como una pintura sin palabras con todas las
superficies lisas y pone el color de acento en objetos de la escena, nunca como formas sueltas.
Tampoco dice que se va a partir en dos: con «split into two halves» salió un díptico con un margen blanco en
medio; ahora pide una sola escena continua de lado a lado. Además,
`folio.imagenes.editorial.revisar` descarta las variantes que aún salgan con letras o manchas.

Mano (2/11, a petición del usuario: «lo veo muy IA aún… tiene que parecer Wired, The Atlantic, The New Yorker»):
el estilo pide técnica de verdad (gouache sobre papel, pincel seco, contornos imperfectos, grano de serigrafía,
mucho espacio vacío) y el modelo pasó a Flux 2 Pro, el que más parece hecho a mano en la comparación con Mystic,
RunWay y Seedream. Ninguna revista se nombra en el prompt: la palabra «magazine» hacía que el modelo escribiera.

Collage (3/11, a petición del usuario: «me gusta más el tipo de ilustración de Los cinco del libro que en el
resto de noticias»): el estilo de la casa pasa del gouache al collage conceptual de «Cinco del libro» (papel
rasgado, fragmentos de foto en trama, magenta y amarillo planos, negro), en todas las ilustraciones: la de
portada y noticia, el friso y la banda. Como en el collage los bloques de color y el papel rasgado son el estilo,
el revisor de letras ya no cuenta las «manchas sueltas», solo las letras. Las frases «with points of interest…
uncluttered.» y «No real or recognisable people…» las sustituyen el friso y la banda: no cambiarlas sin tocar
`folio.imagenes.friso` y `folio.imagenes.banda`.

Reglas: sin nombres de artistas, revistas ni marcas; sin texto, letras ni números en la imagen (los textos
los pone el código); sin personas reales ni caras reconocibles (como mucho, figuras diminutas y anónimas);
apaisada, porque cruza dos diapositivas: lo importante, repartido a lo ancho, sin nada clave en el centro
exacto (es el corte entre las dos).

## estilo

A wordless bold conceptual collage built on one witty visual metaphor that makes the viewer think: cut-paper shapes with torn edges mixed with black-and-white halftone photo fragments, flat hot magenta and lemon yellow blocks, deep black and warm off-white paper, visible paper grain, witty and surreal, high contrast. One single continuous scene that flows across the full width with no division, with points of interest on the left and on the right and nothing essential in the exact centre; the lower left area calm and uncluttered. Every surface is plain: blank walls, blank sky, blank paper, book spines without titles, screens showing only light, signs left empty. The picture contains no writing of any kind: absolutely no text, letters, numbers, signatures, logos or labels anywhere, and no frames, borders, panels or white margins. No medals, coins or plaques. No real or recognisable people; any human figures are anonymous.
