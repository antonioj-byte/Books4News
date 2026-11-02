# Detector de caras (Haiku, con la imagen)

2/11, regla aceptada en la Memoria: «las fotos de personas se recortan mal y en la imagen solo queda la frente»
(Pinker, Fitzek). El código encuadra la foto en el centro de la cara que devuelve este modelo, en la portada, en el
círculo junto a la cubierta y en la tarjeta del cierre. Lo que hay antes de la línea no se envía.

---

Mira la foto y localiza la cara principal (la de la persona retratada, la más grande si hay varias). Devuelve su caja
en porcentajes de la imagen, de 0 a 100: `x0` y `x1` de izquierda a derecha, `y0` y `y1` de arriba abajo, desde la
frente hasta la barbilla y de oreja a oreja. Si no hay ninguna cara visible, `hay_cara` en false y la caja en ceros.
