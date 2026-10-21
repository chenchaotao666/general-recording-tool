import unittest
from app.services import expr


class FormulaChainingTests(unittest.TestCase):
    def test_field_method_and_nested_method(self):
        row = {'contact': ' Alice '}
        self.assertEqual(expr.evaluate(expr.parse('[contact].CONCAT("!")', {'contact'}), row), ' Alice !')
        self.assertEqual(expr.evaluate(expr.parse('[contact].TRIM().CONCAT("!")', {'contact'}), row), 'Alice!')
        self.assertEqual(expr.evaluate(expr.parse('[contact].CONCAT()', {'contact'}), row), ' Alice ')

    def test_method_keeps_field_dependency(self):
        tree = expr.parse('[contact].CONCAT("!")', {'contact'})
        self.assertEqual(expr.referenced_fields(tree), {'contact'})
