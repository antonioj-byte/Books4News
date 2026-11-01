"""Evaluador de puentes (2/11, a petición del usuario: «otro ejemplo de contenido muy pillado con pinzas»).

Un modelo barato e independiente del jefe (prompts/evaluador_puente.md, modelo `puente`) puntúa de 1 a 5 el vínculo
entre la historia y el libro de cada propuesta de la mesa, antes de verificar y escribir nada. Las que no llegan a
`seleccion.puente_minimo` se quedan fuera (mejor una propuesta menos que una forzada) y la que se escribe sola tiene que
llegar a `seleccion.puente_para_escribir`: si la primera no llega, sube la primera que sí. Si el evaluador falla, la
mesa sigue como estaba (con aviso).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from folio.llm import LLM, ErrorLLM
from folio.modelos import HistoriaElegida, SeleccionJefe


class Nota(BaseModel):
    numero: int = Field(description="El número de la propuesta, tal como viene")
    puntuacion: int = Field(description="De 1 a 5, lo sólido y natural que es el vínculo historia-libro")
    por_que: str = Field(description="En una línea, qué une de verdad la historia y el libro, o qué falta")


class Notas(BaseModel):
    notas: list[Nota]


def _prompt(cfg) -> str:
    texto = (cfg.dir_prompts / "evaluador_puente.md").read_text(encoding="utf-8")
    return texto.split("\n---\n", 1)[1].strip()


def _bloque(elegidas: list[HistoriaElegida]) -> str:
    partes = []
    for i, e in enumerate(elegidas, 1):
        libros = "; ".join(f"{l.titulo} ({l.autor})" for l in e.libros_candidatos) or "(sin libro)"
        partes.append(f"{i}. [{e.formato}] {e.titular}\n   De qué se habla: {e.de_que_se_habla}\n"
                      f"   Cuestión de fondo: {e.cuestion_de_fondo}\n   Gancho del libro: {e.gancho_libro}\n   Libros: {libros}")
    return "<propuestas>\n" + "\n\n".join(partes) + "\n</propuestas>"


def evaluar(llm: LLM, sel: SeleccionJefe) -> tuple[SeleccionJefe, dict[str, tuple[int, str]], list[str]]:
    """Puntúa los puentes, deja fuera los forzados y pone primera una con puente sólido. Devuelve (mesa, notas por
    id de historia, avisos)."""
    cfg = llm.cfg
    p = cfg.pipeline.seleccion
    if not sel.elegidas:
        return sel, {}, []
    prompt = _prompt(cfg).replace("[pegar propuestas]", _bloque(sel.elegidas))
    try:
        r, _ = llm.estructurado("puentes", [{"role": "user", "content": prompt}], Notas, etapa_modelo="puente", max_tokens=3000)
    except ErrorLLM as exc:
        return sel, {}, [f"Evaluador de puentes: no se pudo ({exc}); la mesa sigue sin evaluar"]
    por_numero = {n.numero: n for n in r.notas}
    notas, quedan, avisos = {}, [], []
    for i, e in enumerate(sel.elegidas, 1):
        n = por_numero.get(i)
        if n is None or e.formato == "curiosidad" and not e.libros_candidatos:
            quedan.append(e)
            continue
        puntos = max(1, min(5, n.puntuacion))
        notas[e.historia_id] = (puntos, n.por_que.strip())
        if puntos < p.puente_minimo:
            avisos.append(f"Evaluador de puentes: fuera «{e.titular}» ({puntos}/5: {n.por_que.strip()})")
        else:
            quedan.append(e)
    # La que se escribe sola, con un puente sólido: si la primera no llega, sube la primera que sí
    solidas = [e for e in quedan if notas.get(e.historia_id, (5, ""))[0] >= p.puente_para_escribir]
    if quedan and solidas and solidas[0] is not quedan[0]:
        avisos.append(f"Evaluador de puentes: «{solidas[0].titular}» pasa a ser la primera (la de arriba tenía un puente "
                      f"de {notas[quedan[0].historia_id][0]}/5)")
        quedan.remove(solidas[0])
        quedan.insert(0, solidas[0])
    return sel.model_copy(update={"elegidas": quedan}), notas, avisos
