#!/usr/bin/env python3
"""Дерево тестов зеркалит исходники — и это проверяется, а не только описано.

На вопрос «какой тест покрывает этот модуль?» должен быть один ответ, и он читается из пути:
`app/core/totp.py` → `tests/unit/app/core/test_totp.py`. Польза не только в опрятности —
mutmut сопоставляет мутанты с тестами, и при зеркале «какой тест должен был это поймать?»
становится поиском по пути, а не расследованием.

Скрипт падает в четырёх случаях:

1. у модуля нет зеркального теста и его нет в списке исключений;
2. тест в зеркале не имеет исходного модуля — сирота после переименования или удаления;
3. в списке исключений есть модуль, у которого тест уже появился: строку надо убрать;
4. в списке есть модуль, которого больше нет.

Правила 3 и 4 и делают список убывающим: он не может тихо зарасти вместе с кодом. Отдельно
проверяется бюджет — число в первой строке самого списка: дописать строку можно, но тогда
придётся поднять бюджет, и это видно в диффе.

Сценарные тесты (`frontend/tests/screens/`) в зеркало не входят: у них нет одного модуля.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXEMPT_FILE = ROOT / "scripts" / "tests-tree-exempt.txt"


@dataclass(frozen=True)
class Side:
    """Одна сторона проекта: где исходники, где их зеркало и как зовётся тест модуля."""

    name: str
    sources: Path
    mirror: Path
    suffixes: tuple[str, ...]

    def modules(self) -> list[Path]:
        found: list[Path] = []
        for suffix in self.suffixes:
            found.extend(
                path
                for path in (ROOT / self.sources).rglob(f"*{suffix}")
                # пакетные файлы без собственного кода и объявления типов тестировать нечего
                if path.name != "__init__.py" and not path.name.endswith(".d.ts")
            )
        return sorted(found)

    def test_names(self, module: Path) -> tuple[str, ...]:
        """Как может называться тест этого модуля — основной и дополнительные с суффиксом.

        Дополнительные нужны, чтобы правило не требовало склеивать разные по смыслу наборы в
        один файл ради формы: `test_config.py` и `test_config_origins.py` оба про `config.py`.
        """
        stem = module.stem
        if self.name == "backend":
            return (f"test_{stem}.py", f"test_{stem}_")
        return (f"{stem}.test.ts", f"{stem}.test.tsx", f"{stem}.")


SIDES = (
    Side("backend", Path("backend/app"), Path("backend/tests/unit/app"), (".py",)),
    Side("frontend", Path("frontend/src"), Path("frontend/tests/unit/src"), (".ts", ".tsx")),
)


def read_exempt() -> tuple[set[str], int]:
    """Список исключений и бюджет из его первой строки."""
    if not EXEMPT_FILE.exists():
        return set(), 0
    budget = 0
    entries: set[str] = set()
    for line in EXEMPT_FILE.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("# budget:"):
            budget = int(stripped.split(":", 1)[1])
        elif stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries, budget


def belongs_to(side: Side, module: Path, filename: str) -> bool:
    """Этот файл — тест этого модуля? Одно место, где это решается: прямая проверка и поиск
    сирот должны отвечать одинаково, иначе одно из двух врёт."""
    names = side.test_names(module)
    return filename in names[:-1] or filename.startswith(names[-1])


def mirrored_test(side: Side, module: Path) -> Path | None:
    relative = module.relative_to(ROOT / side.sources).parent
    directory = ROOT / side.mirror / relative
    if not directory.is_dir():
        return None
    for candidate in sorted(directory.iterdir()):
        if candidate.is_file() and belongs_to(side, module, candidate.name):
            return candidate
    return None


def check(only: str | None = None) -> list[str]:
    exempt, budget = read_exempt()
    problems: list[str] = []
    covered: set[str] = set()
    known: set[str] = set()
    sides = [side for side in SIDES if only in (None, side.name)]

    for side in sides:
        for module in side.modules():
            key = str(module.relative_to(ROOT))
            known.add(key)
            if mirrored_test(side, module) is not None:
                covered.add(key)
            elif key not in exempt:
                mirror = side.mirror / module.relative_to(ROOT / side.sources).parent
                problems.append(f"нет теста: {key} — ждали его в {mirror}/")

        # сироты: тест есть, модуля под него нет
        for test in sorted((ROOT / side.mirror).rglob("*")):
            # только исходные файлы: скомпилированное и служебное тестами не является
            if not test.is_file() or test.name == "__init__.py":
                continue
            if "__pycache__" in test.parts or test.suffix not in side.suffixes:
                continue
            relative = test.relative_to(ROOT / side.mirror).parent
            adopted = any(
                belongs_to(side, module, test.name)
                for module in side.modules()
                if module.relative_to(ROOT / side.sources).parent == relative
            )
            if not adopted:
                problems.append(f"тест без модуля: {test.relative_to(ROOT)}")

    # Строки чужой стороны не разбираются: их проверит её собственная job, и красная галочка
    # должна говорить, где дыра, а не что она где-то есть.
    owned = {key for key in exempt if any(key.startswith(str(side.sources).split("/")[0]) for side in sides)}
    for key in sorted(owned):
        if key in covered:
            problems.append(f"тест появился, строку из списка надо убрать: {key}")
        elif key not in known:
            problems.append(f"модуля больше нет, строку из списка надо убрать: {key}")

    if len(exempt) > budget:
        problems.append(f"в списке исключений {len(exempt)} строк при бюджете {budget}")

    return problems


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only is not None and only not in {side.name for side in SIDES}:
        print(f"неизвестная сторона: {only}", file=sys.stderr)
        return 2
    problems = check(only)
    if not problems:
        exempt, budget = read_exempt()
        print(f"зеркало сходится; в списке исключений {len(exempt)} строк из {budget}")
        return 0
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"\nвсего расхождений: {len(problems)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
