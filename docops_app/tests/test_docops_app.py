# docops_app/tests.py
from django.test import SimpleTestCase
from docops_app.normalize import load_ruleset, nl_to_ir
from docops_app.ir import validate_ir

class DocOpsPhase1Tests(SimpleTestCase):
    def setUp(self):
        self.rules = load_ruleset("docops_app/rulesets/base.ru.yml")

    def test_bullet_style_variants(self):
        for phrase in [
            'сделай абзац в стиле "Маркированный список"',
            'следующий абзац должен быть отформатирован как «Маркированный список»',
            'примени к создаваемому абзацу стиль "Маркированный список"',
        ]:
            prog = nl_to_ir(phrase, self.rules)
            validate_ir(prog)
            ops = [o.to_dict() for o in prog.ops]
            self.assertEqual(ops[0]["op"], "paragraph.insert")
            self.assertEqual(ops[0]["style"], "ListBullet")