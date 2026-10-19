"""Рекомендательная система по Minecraft на основе базы знаний (minecraft.pl).

Запуск:  python3 recommender.py [путь_к_БЗ]

Формат входной строки фиксированный:
    Я в мире: <мир>, у меня есть: <предмет1>, <предмет2>, хочу добыть: <блок>
Пример:
    Я в мире: overworld, у меня есть: iron_pickaxe, stick, хочу добыть: diamond_ore
Объекты можно называть идентификатором из БЗ или русским названием
(полное совпадение, регистр не важен). Пустой инвентарь: «у меня есть: ничего».
"""
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Dict, List

from prolog_kb import KnowledgeBase

# БЗ minecraft.pl лежит в той же папке, что и этот скрипт.
KB_FILENAME = "minecraft.pl"
DEFAULT_KB = os.path.join(os.path.dirname(os.path.abspath(__file__)), KB_FILENAME)

INPUT_RE = re.compile(
    r"^Я в мире: (?P<dim>[^,]+), у меня есть: (?P<inv>.+), хочу добыть: (?P<goal>[^,]+)$"
)
NOTHING = "ничего"

# Русские названия объектов БЗ (только для ввода и красивого вывода).
RU: Dict[str, str] = {
    "stone": "камень", "iron_ore": "железная руда", "diamond_ore": "алмазная руда",
    "oak_log": "дубовое бревно", "obsidian": "обсидиан", "quartz_ore": "кварцевая руда",
    "end_stone": "камень Энда",
    "iron_ingot": "железный слиток", "diamond": "алмаз", "stick": "палка",
    "wooden_pickaxe": "деревянная кирка", "iron_pickaxe": "железная кирка",
    "diamond_pickaxe": "алмазная кирка", "bread": "хлеб",
    "rotten_flesh": "гнилая плоть", "raw_beef": "сырая говядина", "bone": "кость",
    "wool": "шерсть",
    "zombie": "зомби", "skeleton": "скелет", "creeper": "крипер", "cow": "корова",
    "sheep": "овца",
    "overworld": "верхний мир", "nether": "незер", "end": "энд",
}


class InputError(Exception):
    """Ошибка разбора или проверки пользовательского ввода."""


@dataclass
class Profile:
    dimension: str
    inventory: List[str]
    goal: str


def label(atom: str) -> str:
    return f"{atom} ({RU[atom]})" if atom in RU else atom


def _resolve(kb: KnowledgeBase, text: str, predicates: List[str], what: str) -> str:
    """Сопоставить введённое имя атому БЗ и проверить, что он нужного вида."""
    text = text.strip()
    by_name = {k.lower(): k for k in RU}
    by_name.update({v.lower(): k for k, v in RU.items()})
    atom = by_name.get(text.lower())
    if atom is None and re.fullmatch(r"[a-z][a-z0-9_]*", text):
        atom = text
    if atom is not None and any(kb.holds(f"{p}({atom})") for p in predicates):
        return atom
    known = sorted({a for p in predicates for a in kb.values(f"{p}(X)", "X")})
    raise InputError(
        f"Неизвестно {what}: «{text}». Доступно: " + ", ".join(label(a) for a in known)
    )


def parse_input(line: str, kb: KnowledgeBase) -> Profile:
    """Разобрать строку фиксированного формата в факты профиля."""
    m = INPUT_RE.match(line.strip())
    if not m:
        raise InputError(
            "Неверный формат. Ожидается:\n"
            "  Я в мире: <мир>, у меня есть: <предметы через запятую>, хочу добыть: <блок>\n"
            "Пример:\n"
            "  Я в мире: overworld, у меня есть: iron_pickaxe, stick, хочу добыть: diamond_ore"
        )
    dim = _resolve(kb, m["dim"], ["dimension"], "измерение")
    inv_raw = m["inv"].strip()
    inventory: List[str] = []
    if inv_raw.lower() != NOTHING:
        for part in inv_raw.split(","):
            item = _resolve(kb, part, ["item"], "предмет")
            if item not in inventory:
                inventory.append(item)
    goal = _resolve(kb, m["goal"], ["block"], "блок")
    return Profile(dim, inventory, goal)


def parse_yes_no(answer: str) -> bool:
    a = answer.strip().lower()
    if a in ("да", "д", "yes", "y"):
        return True
    if a in ("нет", "н", "no", "n"):
        return False
    raise InputError("Ответьте «да» или «нет».")


# --- запросы к базе знаний и сборка рекомендаций ------------------------------

def _craft_plan(kb: KnowledgeBase, item: str, inventory: List[str], depth: int = 0) -> List[str]:
    """Что нужно, чтобы получить предмет: рекурсивно по craft_ingredient."""
    pad = "  " * (depth + 1)
    ingredients = kb.values(f"craft_ingredient({item}, I)", "I")
    if not ingredients:
        return [f"{pad}«{label(item)}» в БЗ не крафтится: его нужно раздобыть"]
    lines = [f"{pad}для крафта «{label(item)}» нужно: " + ", ".join(label(i) for i in ingredients)]
    for ing in ingredients:
        if ing in inventory:
            lines.append(f"{pad}  ✓ {label(ing)} уже есть")
        else:
            lines.append(f"{pad}  ✗ не хватает: {label(ing)}")
            if depth < 3 and kb.holds(f"craft_ingredient({ing}, _)"):
                lines += _craft_plan(kb, ing, inventory, depth + 1)
    return lines


def advise_goal(kb: KnowledgeBase, p: Profile) -> List[str]:
    out = [f"== Цель: добыть {label(p.goal)} =="]
    usable = [i for i in p.inventory if kb.holds(f"can_mine({i}, {p.goal})")]
    if usable:
        out.append("Можно добывать прямо сейчас: " + ", ".join(label(i) for i in usable) + ".")
    else:
        needed = kb.values(f"can_mine(T, {p.goal})", "T")
        if kb.holds(f"required_tool({p.goal}, _)"):
            tool = needed[0]
            out.append(f"Для этого блока нужен инструмент: {label(tool)}. В инвентаре его нет.")
            out += _craft_plan(kb, tool, p.inventory)
        else:
            out.append(
                "Специальный инструмент не нужен, подойдёт любой, но в инвентаре инструментов нет. "
                "Возьмите, например: " + ", ".join(label(t) for t in needed) + "."
            )
    dims = kb.values(f"found_in({p.goal}, D)", "D")
    if not dims:
        out.append("Где встречается этот блок, в БЗ нет данных.")
    for d in dims:
        if d == p.dimension:
            out.append(f"Блок встречается в вашем мире ({label(d)}): ищите его здесь.")
        else:
            out.append(f"Блок встречается в другом мире: {label(d)}. Вы сейчас в {label(p.dimension)}, нужен переход.")
    if kb.holds(f"needs_nether_exploration({p.goal})"):
        out.append("Внимание: для этого нужно исследовать Незер.")
    return out


def advise_dimension(kb: KnowledgeBase, p: Profile) -> List[str]:
    blocks = kb.values(f"valuable_resource({p.dimension}, B)", "B")
    if not blocks:
        return [f"== Ценные ресурсы мира {label(p.dimension)} ==", "В БЗ для этого мира ценных ресурсов нет."]
    lines = [f"== Ценные ресурсы мира {label(p.dimension)} =="]
    for b in blocks:
        tool = kb.values(f"required_tool({b}, T)", "T")[0]
        lines.append(f"- {label(b)}: нужен {label(tool)}")
    return lines


def advise_loot(kb: KnowledgeBase, fight: bool) -> List[str]:
    lines = ["== Лут с мобов =="]
    for sol in kb.query("farmable_drop(M, D)"):
        lines.append(f"- безопасно: {label(sol['D'])} с моба {label(sol['M'])} (мирный)")
    if fight:
        for sol in kb.query("dangerous_drop(M, D)"):
            lines.append(f"- рискованно: {label(sol['D'])} с моба {label(sol['M'])} (враждебный)")
    else:
        lines.append("(лут с враждебных мобов не показан: вы не готовы сражаться)")
    return lines


def advise_food(kb: KnowledgeBase, fight: bool) -> List[str]:
    lines = ["== Еда =="]
    for food in kb.values("safe_food(I)", "I"):
        src = kb.values(f"drops(M, {food})", "M")
        how = "выпадает с " + ", ".join(label(m) for m in src) if src else "ни с кого не выпадает, делается крафтом"
        lines.append(f"- безопасная еда: {label(food)} ({how})")
    if fight:
        for food in kb.values("edible(I), \\+ safe_food(I)", "I"):
            src = kb.values(f"drops(M, {food})", "M")
            lines.append(f"- рискованная еда: {label(food)} (выпадает с {', '.join(label(m) for m in src)})")
    return lines


def recommend(kb: KnowledgeBase, p: Profile, fight: bool, need_food: bool) -> List[str]:
    out = advise_goal(kb, p) + [""] + advise_dimension(kb, p) + [""] + advise_loot(kb, fight)
    if need_food:
        out += [""] + advise_food(kb, fight)
    return out


# --- диалог ---------------------------------------------------------------------

def _ask(prompt: str, parse: Callable[[str], object], ask: Callable[[str], str], say: Callable[[str], None]):
    while True:
        try:
            return parse(ask(prompt))
        except InputError as e:
            say(str(e))


def run(kb: KnowledgeBase, ask: Callable[[str], str] = input, say: Callable[[str], None] = print) -> None:
    say("Советник по Minecraft. Опишите себя одной строкой в формате:")
    say("  Я в мире: <мир>, у меня есть: <предметы через запятую>, хочу добыть: <блок>")
    say("Пример: Я в мире: overworld, у меня есть: iron_pickaxe, stick, хочу добыть: diamond_ore")
    profile = _ask("> ", lambda s: parse_input(s, kb), ask, say)
    say("")
    fight = _ask("Готовы сражаться с враждебными мобами? (да/нет) ", parse_yes_no, ask, say)
    need_food = _ask("Нужна ли вам еда? (да/нет) ", parse_yes_no, ask, say)
    say("")
    for line in recommend(kb, profile, fight, need_food):
        say(line)


def main() -> None:
    kb = KnowledgeBase.from_file(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KB)
    try:
        run(kb)
    except (EOFError, KeyboardInterrupt):
        print("\nДо встречи!")


if __name__ == "__main__":
    main()