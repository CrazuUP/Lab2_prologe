import os
import unittest

from prolog_kb import KnowledgeBase, PrologSyntaxError
from recommender import (InputError, Profile, parse_input, parse_yes_no,
                         recommend, run)

KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "minecraft.pl")


class KBTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase.from_file(KB_PATH)

    def test_facts(self):
        self.assertTrue(self.kb.holds("block(obsidian)"))
        self.assertFalse(self.kb.holds("block(diamond)"))

    def test_farmable_drop(self):
        self.assertEqual(set(self.kb.values("farmable_drop(M, D)", "D")), {"raw_beef", "wool"})

    def test_dangerous_drop(self):
        self.assertEqual(set(self.kb.values("dangerous_drop(M, D)", "D")), {"rotten_flesh", "bone"})

    def test_can_mine_required_tool(self):
        self.assertEqual(self.kb.values("can_mine(T, diamond_ore)", "T"), ["iron_pickaxe"])
        self.assertFalse(self.kb.holds("can_mine(wooden_pickaxe, obsidian)"))

    def test_can_mine_negation_branch(self):
        self.assertEqual(len(self.kb.values("can_mine(T, stone)", "T")), 3)
        self.assertFalse(self.kb.holds("can_mine(bread, stone)"))  # хлеб не инструмент

    def test_safe_food_conjunction_in_negation(self):
        self.assertEqual(set(self.kb.values("safe_food(I)", "I")), {"bread", "raw_beef"})

    def test_valuable_resource(self):
        self.assertEqual(
            {(s["D"], s["B"]) for s in self.kb.query("valuable_resource(D, B)")},
            {("overworld", "diamond_ore"), ("overworld", "obsidian")},
        )

    def test_nether(self):
        self.assertEqual(self.kb.values("needs_nether_exploration(O)", "O"), ["quartz_ore"])

    def test_syntax_error(self):
        with self.assertRaises(PrologSyntaxError):
            KnowledgeBase("foo(a")


class ParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase.from_file(KB_PATH)

    def test_ids(self):
        p = parse_input("Я в мире: overworld, у меня есть: iron_pickaxe, stick, хочу добыть: diamond_ore", self.kb)
        self.assertEqual(p, Profile("overworld", ["iron_pickaxe", "stick"], "diamond_ore"))

    def test_russian_names(self):
        p = parse_input("Я в мире: Незер, у меня есть: железная кирка, хочу добыть: кварцевая руда", self.kb)
        self.assertEqual(p, Profile("nether", ["iron_pickaxe"], "quartz_ore"))

    def test_empty_inventory(self):
        p = parse_input("Я в мире: end, у меня есть: ничего, хочу добыть: end_stone", self.kb)
        self.assertEqual(p.inventory, [])

    def test_duplicates_removed(self):
        p = parse_input("Я в мире: end, у меня есть: stick, stick, хочу добыть: stone", self.kb)
        self.assertEqual(p.inventory, ["stick"])

    def test_bad_format(self):
        for s in ["Мне 13 лет, мне нравятся: RPG", "", "Я в мире: end, хочу добыть: stone"]:
            with self.assertRaises(InputError):
                parse_input(s, self.kb)

    def test_unknown_objects(self):
        with self.assertRaises(InputError):
            parse_input("Я в мире: mars, у меня есть: stick, хочу добыть: stone", self.kb)
        with self.assertRaises(InputError):
            parse_input("Я в мире: end, у меня есть: laser, хочу добыть: stone", self.kb)

    def test_goal_must_be_block(self):
        with self.assertRaises(InputError):
            parse_input("Я в мире: end, у меня есть: stick, хочу добыть: diamond", self.kb)

    def test_no_partial_match(self):
        with self.assertRaises(InputError):
            parse_input("Я в мире: over, у меня есть: stick, хочу добыть: stone", self.kb)

    def test_yes_no(self):
        self.assertTrue(parse_yes_no(" Да "))
        self.assertFalse(parse_yes_no("нет"))
        with self.assertRaises(InputError):
            parse_yes_no("может")


class RecommendationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase.from_file(KB_PATH)

    def text(self, p, fight=False, food=False):
        return "\n".join(recommend(self.kb, p, fight, food))

    def test_can_mine_now(self):
        t = self.text(Profile("overworld", ["iron_pickaxe"], "diamond_ore"))
        self.assertIn("Можно добывать прямо сейчас", t)

    def test_craft_plan_shows_missing(self):
        t = self.text(Profile("overworld", ["stick"], "obsidian"))
        self.assertIn("✗ не хватает: diamond", t)
        self.assertIn("✓ stick", t)

    def test_other_dimension(self):
        t = self.text(Profile("overworld", [], "quartz_ore"))
        self.assertIn("нужен переход", t)
        self.assertIn("Незер", t)

    def test_fight_flag_controls_dangerous_loot(self):
        p = Profile("overworld", [], "stone")
        self.assertNotIn("zombie", self.text(p, fight=False))
        self.assertIn("zombie", self.text(p, fight=True))

    def test_food_section(self):
        p = Profile("overworld", [], "stone")
        self.assertNotIn("== Еда ==", self.text(p))
        peaceful = self.text(p, fight=False, food=True)
        self.assertIn("bread", peaceful)
        self.assertNotIn("rotten_flesh", peaceful)
        self.assertIn("рискованная еда: rotten_flesh", self.text(p, fight=True, food=True))

    def test_no_tool_needed_no_inventory(self):
        t = self.text(Profile("overworld", [], "stone"))
        self.assertIn("подойдёт любой", t)


class DialogueTests(unittest.TestCase):
    def test_full_dialogue_with_retries(self):
        kb = KnowledgeBase.from_file(KB_PATH)
        answers = iter([
            "привет",  # неверный формат
            "Я в мире: overworld, у меня есть: iron_pickaxe, хочу добыть: diamond_ore",
            "может",  # неверный ответ
            "да",
            "нет",
        ])
        out = []
        run(kb, ask=lambda _: next(answers), say=out.append)
        text = "\n".join(out)
        self.assertIn("Неверный формат", text)
        self.assertIn("Ответьте «да» или «нет»", text)
        self.assertIn("== Цель: добыть diamond_ore", text)
        self.assertIn("zombie", text)
        self.assertNotIn("== Еда ==", text)


if __name__ == "__main__":
    unittest.main()
