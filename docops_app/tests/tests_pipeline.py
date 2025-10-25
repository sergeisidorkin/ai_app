from django.test import SimpleTestCase
from docops_app.pipeline import process_answer_through_pipeline

class PipelineTests(SimpleTestCase):
    def test_raw_docops_passes(self):
        text = """```docops
        {"type":"DocOps","version":"v1","ops":[{"op":"paragraph.insert","text":"Hello"}]}
        ```"""
        r = process_answer_through_pipeline(text)
        self.assertEqual(r["kind"], "docops")
        self.assertGreater(len(r["blocks"]), 0)
        # нормализация не нужна — стиль не задействован
        self.assertFalse(r["normalized"])

        ops = r["program"]["ops"]
        self.assertEqual(ops[0]["op"], "paragraph.insert")
        self.assertEqual(ops[0]["text"], "Hello")

    def test_docops_needs_normalization(self):
        # style не указан, только человекочитаемый styleName → пайплайн должен нормализовать в ListBullet + styleId
        text = """{"type":"DocOps","version":"v1",
                   "ops":[{"op":"paragraph.insert","styleName":"Маркированный список","text":"item"}]}"""
        r = process_answer_through_pipeline(text)
        self.assertEqual(r["kind"], "docops")
        self.assertTrue(r["normalized"])

        op0 = r["program"]["ops"][0]
        # после нормализации появится canonical стиль
        self.assertEqual(op0.get("style"), "ListBullet")
        # и, если в ruleset проецируется style_id, он тоже должен появиться (в базовой карте это "a")
        self.assertIn(op0.get("style_id"), (None, "a"))  # оставим гибко: зависит от ruleset

    def test_plain_text_becomes_program(self):
        # Синтез срабатывает по маркерам "- " / "• "
        text = "- один\n- два\n- три"
        r = process_answer_through_pipeline(text)
        self.assertEqual(r["kind"], "docops")
        self.assertEqual(r["source"], "synthesized")
        self.assertGreater(len(r["blocks"]), 0)

        # в программе должен появиться list.start / list.item / list.end
        ops = [o["op"] for o in r["program"]["ops"]]
        self.assertIn("list.start", ops)
        self.assertIn("list.item", ops)
        self.assertIn("list.end", ops)