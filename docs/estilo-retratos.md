# Estilo de la casa para los retratos generados: prueba del 30/10

**Elegidos (31/10): low-poly, vóxel, dithering de 1 bit y render de videojuego de los 2000** (este
último, a gusto del usuario aunque no salió como pedía el prompt: queda entre píxel y vóxel), integrados en `folio.imagenes.retrato_generado`
(ver CLAUDE.md, «Retratos generados»). La hoja de contactos con las imágenes está en una página
privada (Artifact) del usuario. Las imágenes no se guardan en el repo.

- **Foto de partida**: Philip Roth por Bernard Gotfryd (Library of Congress, `gtfy/03200/03254v.jpg`,
  «No known restrictions on publication»), enviada en base64. Por URL, la LoC responde 403 al
  servidor de Magnific.
- **Endpoint**: Seedream 4.5 Edit (`POST /v1/ai/text-to-image/seedream-v4-5-edit`), el que mejor
  conservó el parecido en la prueba anterior. Una imagen por estilo, 1774×2364, ninguna repetida.
- **Coste**: la API no lo devuelve y la Analytics API responde 403 en esta cuenta. Hay que mirarlo en
  el panel (tareas del 30/10, de 22:13 a 22:20 UTC).
- **Notas** (1–5): parecido, si se lee a 300 px en el móvil, encaje con Wired × Alighieria y que no
  ridiculice al autor.

| # | Estilo | Tiempo | Parecido | Móvil | Encaje | Dignidad | Total |
|---|---|---|---|---|---|---|---|
| 1 | Pixel art 16 bits | 19,1 s | 4 | 4 | 4 | 4 | 16 |
| 2 | Pixel art 8 bits | 31,6 s | 4 | 4 | 3 | 4 | 15 |
| 3 | Pantalla de carga de mundo abierto | 39,5 s | 4 | 5 | 2 | 4 | 15 |
| 4 | Low-poly | 18,1 s | 4 | 5 | 5 | 5 | 19 |
| 5 | Render de videojuego de los 2000 | 18,3 s | 3 | 4 | 3 | 3 | 13 |
| 6 | Voxel | 18,2 s | 3 | 4 | 3 | 2 | 12 |
| 7 | ASCII de terminal | 31,2 s | 4 | 2 | 2 | 4 | 12 |
| 8 | Glitch / datamosh | 22,6 s | 5 | 4 | 2 | 5 | 16 |
| 9 | Avatar de red social antigua | 18,0 s | 4 | 4 | 2 | 3 | 13 |
| 10 | Dithering de 1 bit | 18,0 s | 5 | 5 | 4 | 5 | 19 |

**Las tres mejores**: low-poly (4), dithering de 1 bit (10) y pixel art de 16 bits (1). Se pintaron
como portada en «sangre» y «neon» con una pieza de prueba («Philip Roth», sin texto atribuido) y
FOLIO_DATOS en un directorio temporal.

**Segundo autor**: Norman Mailer por Bernard Gotfryd, 1967 (LoC, ficha 2020732210,
`gtfy/02600/02669v.jpg`, «No known restrictions on publication»), en low-poly y dithering. Low-poly
mantiene el estilo. El dithering también, pero le deja color a la ropa (chaqueta azul) y en los dos
autores sale con fondo blanco.

**Recomendación**: low-poly. Si se elige el dithering, conviene forzar el blanco y negro en código
(umbral de 1 bit), porque el modelo no lo garantiza.

Descartados, y por qué: el 7 (ASCII) no usa caracteres reales y el verde no está en la paleta; el 8
(glitch) a 300 px parece una foto real, y eso confunde en una imagen generada de una persona real; el
9 (avatar) lleva un marco que recuerda a un sistema operativo concreto y tiene fondo claro; el 6
(vóxel) parece un juguete.

## Prompts

Todos terminan con el mismo bloque de parecido: «Keep the exact likeness of the person in the photo:
face shape, eyes, eyebrows, nose, mouth, hairline and hair, calm serious expression, same clothing,
head-and-shoulders bust, same head angle.», el fondo oscuro liso y «No text, no letters, no numbers,
no logos, no watermark, no signature.» (el 7 sin «text», el 9 sin fondo y el 10 con «Plain
background»). La parte propia de cada estilo:

1. Recreate this portrait as 16-bit pixel art: a head-and-shoulders character portrait like a classic video game dialogue portrait, limited palette of about 32 colors, clearly visible square pixels, clean pixel shading, no anti-aliasing.
2. Recreate this portrait as 8-bit pixel art: very low resolution, large chunky visible square pixels, only 6 to 8 colors, bold simple shapes that stay readable as a tiny thumbnail.
3. Recreate this portrait as a loading-screen illustration for an open-world video game: cel-shaded, thick bold black outlines, saturated colors, a dignified neutral pose, the person shown as a respectable character. No weapons, no vehicles, no money, nothing that suggests crime.
4. Recreate this portrait as a low-poly 3D bust: a model made of a few large triangular polygons with flat shading, faceted surfaces and visible polygon edges.
5. Recreate this portrait as an early-2000s video game character render: a 3D character model with low-resolution blurry textures, simple geometry, a slightly stiff look, lit like a character selection screen, bust facing the camera.
6. Recreate this portrait as a voxel bust: the head and shoulders built entirely from small cubes, like a block-building game, cubic hair and features, soft ambient occlusion lighting.
7. Recreate this portrait as terminal ASCII art: the face built only from monospaced characters (symbols such as @ # % * + = - : .) glowing in phosphor green on a pure black screen, like an old computer terminal, with faint scanlines. The characters form the image; no readable words.
8. Recreate this portrait with digital glitch and datamosh effects: horizontal slice displacement, RGB channel split, JPEG compression blocks and pixel smearing over parts of the image, while the face stays clearly recognizable.
9. Recreate this portrait as an early-2000s social network profile picture: a low-resolution, slightly pixelated, over-compressed webcam-style photo shown inside a simple generic grey-and-blue user interface window frame with an empty title bar.
10. Recreate this portrait as 1-bit dithered graphics: only pure black and pure white pixels, with dithering patterns for the shading, like the screen of an early monochrome personal computer.
