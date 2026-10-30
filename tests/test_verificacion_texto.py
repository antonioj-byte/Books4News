from folio.verificacion_texto import autor_coincide, clave_libro, titulos_coinciden


def test_titulos_con_y_sin_subtitulo():
    assert titulos_coinciden("Eichmann en Jerusalén", "Eichmann en Jerusalén: un estudio sobre la banalidad del mal")
    assert titulos_coinciden("La peste", "LA PESTE")
    assert titulos_coinciden("El extranjero", "Extranjero")


def test_titulos_distintos():
    assert not titulos_coinciden("Vigilar y castigar", "Discipline and Punish")
    assert not titulos_coinciden("La peste", "La pesta", umbral=1.0)
    assert not titulos_coinciden("Eichmann en Jerusalén", "Eichmann en Xerusalén", umbral=1.0)


def test_autor_por_apellido():
    assert autor_coincide("Hannah Arendt", ["Hannah Arendt"])
    assert autor_coincide("Byung-Chul Han", ["Byung-Chul Han"])
    assert autor_coincide("Albert Camus", ["CAMUS, Albert"])
    assert not autor_coincide("Hannah Arendt", ["Michel Foucault"])


def test_clave_libro_estable():
    assert clave_libro("La peste", "Albert Camus") == clave_libro("Peste", "A. Camus")
