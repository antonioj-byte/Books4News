import pytest

from videos.config import Config

CAPITULO_1 = ("Durante siglos creímos que el descanso consistía en no hacer nada. "
              "Sin embargo, el cerebro que no hace nada se pone a rumiar, y rumiar cansa más que trabajar. "
              "Por eso los domingos vacíos agotan: el descanso verdadero es un cambio de actividad, no su ausencia. "
              "Los monjes lo sabían y alternaban el trabajo manual con la lectura. ") * 4
CAPITULO_2 = ("La atención no se gasta como el dinero; se entrena como un músculo que también se atrofia. "
              "Quien mira el móvil cada pocos minutos no está distraído: está entrenando la distracción. "
              "La buena noticia es que el entrenamiento funciona en las dos direcciones. ") * 4


@pytest.fixture
def cfg(tmp_path):
    c = Config(datos=tmp_path / "datos", anthropic_api_key="x", magnific_api_key="", elevenlabs_api_key="")
    return c


@pytest.fixture
def libro_txt(tmp_path):
    r = tmp_path / "libro.txt"
    r.write_text(f"Capítulo 1\n\n{CAPITULO_1}\n\nCapítulo 2\n\n{CAPITULO_2}\n", encoding="utf-8")
    return r
