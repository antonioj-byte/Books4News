import re

import pytest

from videos.prompts import ErrorPrompt, cargar


def test_todos_los_prompts_tienen_version(cfg):
    for r in cfg.prompts.glob("*.md"):
        assert re.match(r"<!--\s*version:", r.read_text(encoding="utf-8")), r.name


def test_marcadores_que_faltan_fallan(cfg):
    with pytest.raises(ErrorPrompt):
        cargar(cfg, "juez_gancho", gancho="x")
    texto, version = cargar(cfg, "juez_gancho", gancho="Descansar cansa", idea="x")
    assert version == "juez_gancho@2" and "Descansar cansa" in texto and "{{" not in texto
