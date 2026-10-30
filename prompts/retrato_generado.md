# Retrato generado del autor (Magnific, Seedream 4.5 Edit)

Prompts para convertir la foto libre del autor en uno de los estilos de la casa, elegidos el 31/10
tras la prueba de `docs/estilo-retratos.md`. Van en inglés porque el modelo los sigue mejor.
El código (`folio.imagenes.retrato_generado`) lee la sección del estilo (`## low_poly`, `## voxel`,
`## dithering`, `## render_2000`) y le añade la sección `## comun`. Lo que hay antes del primer encabezado `##` no se
envía.

Reglas: nada de nombres de juegos, consolas, estudios ni artistas; sin texto ni logotipos; la cara
siempre sale de la foto (el parecido se pide explícitamente en `comun`).

## low_poly

Recreate this portrait as a low-poly 3D bust: a model made of a few large triangular polygons with flat shading, faceted surfaces and visible polygon edges. Plain dark background, flat or a soft near-black gradient.

## voxel

Recreate this portrait as a voxel bust: the head and shoulders built entirely from small cubes, like a block-building game, cubic hair and features, soft ambient occlusion lighting. Plain dark background, flat or a soft near-black gradient.

## dithering

Recreate this portrait as 1-bit dithered graphics: only pure black and pure white pixels, with dithering patterns for the shading, like the screen of an early monochrome personal computer. Plain background.

## render_2000

Recreate this portrait as an early-2000s video game character render: a 3D character model with low-resolution blurry textures, simple geometry, a slightly stiff look, lit like a character selection screen, bust facing the camera. Plain dark background, flat or a soft near-black gradient.

## comun

Keep the exact likeness of the person in the photo: face shape, eyes, eyebrows, nose, mouth, hairline and hair, calm serious expression, same clothing, head-and-shoulders bust, same head angle. No text, no letters, no numbers, no logos, no watermark, no signature.
