"""Мини-интерпретатор Prolog для базы знаний minecraft.pl.

Поддерживается ровно тот подмножество Prolog, которое используется в БЗ:
  * факты  foo(a, b).
  * правила  head :- g1, g2, \\+ g3, \\+ (g4, g5).
  * переменные (с заглавной буквы или _), атомы, комментарии % и /* */
  * отрицание как неудача (\\+)

Запросы выполняются резолюцией с возвратом (SLD), как в обычном Prolog.
"""
import itertools
import re
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple, Union


class PrologSyntaxError(Exception):
    pass


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Atom:
    value: str


@dataclass(frozen=True)
class Compound:
    functor: str
    args: Tuple["Term", ...]


Term = Union[Var, Atom]


@dataclass(frozen=True)
class Not:
    goals: Tuple[Compound, ...]


Goal = Union[Compound, Not]


@dataclass(frozen=True)
class Rule:
    head: Compound
    body: Tuple[Goal, ...]


_TOKEN_RE = re.compile(r"\s*(:-|\\\+|[(),.]|[A-Za-z_][A-Za-z0-9_]*)")


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"%[^\n]*", " ", text)


def _tokenize(text: str) -> List[str]:
    tokens, pos = [], 0
    text = _strip_comments(text)
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise PrologSyntaxError(f"Неожиданный символ: {text[pos:pos + 20]!r}")
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: List[str]):
        self.t = tokens
        self.i = 0
        self.anon = 0

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, expected: Optional[str] = None) -> str:
        tok = self.peek()
        if tok is None or (expected is not None and tok != expected):
            raise PrologSyntaxError(f"Ожидалось {expected!r}, получено {tok!r}")
        self.i += 1
        return tok

    def term(self) -> Term:
        tok = self.take()
        if tok == "_":
            self.anon += 1
            return Var(f"_{self.anon}")
        if tok[0].isupper() or tok[0] == "_":
            return Var(tok)
        if re.fullmatch(r"[a-z][A-Za-z0-9_]*", tok):
            return Atom(tok)
        raise PrologSyntaxError(f"Некорректный терм: {tok!r}")

    def compound(self) -> Compound:
        name = self.take()
        if not re.fullmatch(r"[a-z][A-Za-z0-9_]*", name):
            raise PrologSyntaxError(f"Некорректное имя предиката: {name!r}")
        args: List[Term] = []
        if self.peek() == "(":
            self.take("(")
            args.append(self.term())
            while self.peek() == ",":
                self.take(",")
                args.append(self.term())
            self.take(")")
        return Compound(name, tuple(args))

    def goal(self) -> Goal:
        if self.peek() == "\\+":
            self.take()
            if self.peek() == "(":
                self.take("(")
                goals = [self.compound()]
                while self.peek() == ",":
                    self.take(",")
                    goals.append(self.compound())
                self.take(")")
                return Not(tuple(goals))
            return Not((self.compound(),))
        return self.compound()

    def clause(self) -> Rule:
        head = self.compound()
        body: List[Goal] = []
        if self.peek() == ":-":
            self.take()
            body.append(self.goal())
            while self.peek() == ",":
                self.take(",")
                body.append(self.goal())
        self.take(".")
        return Rule(head, tuple(body))

    def program(self) -> List[Rule]:
        rules = []
        while self.peek() is not None:
            rules.append(self.clause())
        return rules


Subst = Dict[Var, Term]


def _walk(term: Term, s: Subst) -> Term:
    while isinstance(term, Var) and term in s:
        term = s[term]
    return term


def _unify(a: Term, b: Term, s: Subst) -> Optional[Subst]:
    a, b = _walk(a, s), _walk(b, s)
    if a == b:
        return s
    if isinstance(a, Var):
        return {**s, a: b}
    if isinstance(b, Var):
        return {**s, b: a}
    return None


class KnowledgeBase:
    def __init__(self, source: str):
        self.rules: List[Rule] = _Parser(_tokenize(source)).program()
        self._counter = itertools.count()

    @classmethod
    def from_file(cls, path: str) -> "KnowledgeBase":
        """Прочитать БЗ, автоматически определив кодировку.

        Порядок попыток:
          1. utf-8-sig — UTF-8 с BOM (типично для Блокнота/VS Code).
          2. utf-8     — обычный UTF-8.
          3. cp1251    — кириллица Windows (старые редакторы).
        """
        last_err: Optional[UnicodeDecodeError] = None
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                with open(path, encoding=enc) as f:
                    return cls(f.read())
            except UnicodeDecodeError as e:
                last_err = e
                continue
        assert last_err is not None
        raise UnicodeDecodeError(
            last_err.encoding, last_err.object,
            last_err.start, last_err.end,
            f"Не удалось прочитать {path}: сохраните файл в UTF-8 или cp1251",
        )

    # --- резолюция ---------------------------------------------------
    def _rename(self, rule: Rule) -> Rule:
        n = next(self._counter)

        def r(t: Term) -> Term:
            return Var(f"{t.name}#{n}") if isinstance(t, Var) else t

        def rc(c: Compound) -> Compound:
            return Compound(c.functor, tuple(r(a) for a in c.args))

        body = tuple(
            Not(tuple(rc(g) for g in b.goals)) if isinstance(b, Not) else rc(b)
            for b in rule.body
        )
        return Rule(rc(rule.head), body)

    def _solve(self, goals: Tuple[Goal, ...], s: Subst) -> Iterator[Subst]:
        if not goals:
            yield s
            return
        first, rest = goals[0], goals[1:]
        if isinstance(first, Not):
            # отрицание как неудача: успех, если у конъюнкции нет решений
            if next(self._solve(first.goals, s), None) is None:
                yield from self._solve(rest, s)
            return
        for rule in self.rules:
            if rule.head.functor != first.functor or len(rule.head.args) != len(first.args):
                continue
            rule = self._rename(rule)
            s2: Optional[Subst] = s
            for x, y in zip(first.args, rule.head.args):
                s2 = _unify(x, y, s2)
                if s2 is None:
                    break
            if s2 is None:
                continue
            yield from self._solve(rule.body + rest, s2)

    @staticmethod
    def _parse_query(query: str) -> Tuple[Goal, ...]:
        p = _Parser(_tokenize(query.strip().rstrip(".") + "."))
        goals = [p.goal()]
        while p.peek() == ",":
            p.take(",")
            goals.append(p.goal())
        p.take(".")
        return tuple(goals)

    def query(self, query: str) -> List[Dict[str, str]]:
        """Выполнить запрос, например ``farmable_drop(Mob, Drop)``.

        Возвращает список решений (словарь «имя переменной -> атом»);
        для запроса без переменных - [{}] (истина) или [] (ложь).
        Повторяющиеся решения удаляются, порядок сохраняется.
        """
        goals = self._parse_query(query)
        names: List[Var] = []

        def collect(c: Compound) -> None:
            for a in c.args:
                if isinstance(a, Var) and not a.name.startswith("_") and a not in names:
                    names.append(a)

        for g in goals:
            for c in (g.goals if isinstance(g, Not) else (g,)):
                collect(c)
        seen, out = set(), []
        for s in self._solve(goals, {}):
            sol = {}
            for v in names:
                val = _walk(v, s)
                sol[v.name] = val.value if isinstance(val, Atom) else "_"
            key = tuple(sol.items())
            if key not in seen:
                seen.add(key)
                out.append(sol)
        return out

    def holds(self, query: str) -> bool:
        return bool(self.query(query))

    def values(self, query: str, var: str) -> List[str]:
        return [sol[var] for sol in self.query(query)]