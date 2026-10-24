import unittest
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import patch
from app.services import ai_field_service as service, expr
from app.services.ai_scenes import SCENE_BY_KEY
from app.services.ai_template_formulas import FORMULAS, calculate


class FormulaTemplateTests(unittest.TestCase):
    def run_case(self, key, values):
        scene = SCENE_BY_KEY[key]
        names = [r['key'] for r in scene['inputRoles']]
        cfg = {'scene': key, 'inputFields': names, 'inputBindings': {k: k for k in names}}
        fields = [NS(field_name=r['key'], field_type='text' if r['key'] in ('gender', 'text') else 'date' if 'date' in r['types'] else 'number', options={}, label=r['key']) for r in scene['inputRoles']]
        with patch('app.services.llm.get_default_provider', side_effect=AssertionError('must not use model')), patch('app.services.ai_template_compute.compute', side_effect=AssertionError('must execute formula, not legacy compute')):
            result, billable, tokens = service.compute_raw(None, cfg, fields, dict(zip(names, values)), [])
        self.assertEqual((billable, tokens), (False, 0))
        return result

    def test_all_formulas_parse(self):
        for key, formula in FORMULAS.items():
            with self.subTest(key=key):
                expr.parse(formula)
                expr.parse(SCENE_BY_KEY[key]['formulaDisplay'])

    def test_date_templates_use_formulas_and_blank_branches(self):
        from app.services.formula_funcs import FUNCTIONS
        with patch.dict(FUNCTIONS['TODAY'], impl=lambda: date(2026,4,17)):
            for end, expected in [('2026-05-15',28), ('2026-04-17',None), ('2026-04-10',None), (None,None)]:
                self.assertEqual(self.run_case('deadlineCountdown',[end]),expected)
            self.assertEqual(self.run_case('hrAge',['2000-04-18']),25)
            self.assertIsNone(self.run_case('hrAge',['2027-01-01']))
            self.assertEqual(self.run_case('hrSeniority',['2025-04-17']),1)
            self.assertEqual(self.run_case('hrContract',['2026-04-17']),'即将到期')
            self.assertEqual(self.run_case('stHealthDays',['2026-04-16']),-1)
            self.assertEqual(self.run_case('taskStatus',[None,None,None]),'未开始')
            self.assertEqual(self.run_case('taskStatus',['2026-01-01','2026-01-02',None]),'已延期')
            self.assertEqual(self.run_case('taskStatus',[None,None,'2026-01-01']),'已完成')
        self.assertEqual(self.run_case('stHealthExpiry',['2024-02-29']),'2025-02-28')
        self.assertEqual(self.run_case('orderShippingStatus',['2026-01-01',None]),'待发货')
        self.assertEqual(self.run_case('orderShippingStatus',['2026-01-01','2026-01-03']),'延迟发货')

    def test_new_formula_functions_and_conversions(self):
        self.assertEqual(self.run_case('cvBmr',[175,70,30,'男']),1649)
        self.assertEqual(self.run_case('cvMonthDays',['2024-02-10']),29)
        self.assertTrue(self.run_case('cvMonthEnd',['2024-02-29']))
        self.assertEqual(self.run_case('cvMileKm',[1]),1.61)
        self.assertEqual(self.run_case('cvWordCount',[' 中 文\nA\t B\u3000']),4)
        self.assertTrue(1<=self.run_case('cvRandom',[])<=100)
        self.assertEqual(self.run_case('workdays',['2026-10-12','2026-10-16']),5)
        # China calendar must count the make-up working Sunday, unlike NETWORKDAYS.
        self.assertEqual(self.run_case('workdays',['2024-02-18','2024-02-18']),1)
        for key in ('stHours','pdTicketTime'):
            self.assertEqual(self.run_case(key,['2026-01-01T00:00:00Z','2026-01-01T09:30:00+08:00']),1.5)
        with self.assertRaises(ValueError):
            self.run_case('workdays',['2026-10-16','2026-10-12'])

    def test_power_precedence_and_literals(self):
        for source, expected in [('70/(175/100)^2', 22.857142857142858), ('2*3^2',18), ('2^3^2',512), ('"x^2"','x^2')]:
            self.assertEqual(expr.evaluate(expr.parse(source), {}, strict=True), expected)

    def test_tax_brackets_at_each_boundary(self):
        for limit, rate, next_rate in [(3000,'3%','10%'), (12000,'10%','20%'), (25000,'20%','25%'), (35000,'25%','30%'), (55000,'30%','35%'), (80000,'35%','45%')]:
            self.assertEqual(self.run_case('fnIitLevel', [limit]), rate)
            self.assertEqual(self.run_case('fnIitLevel', [limit+.01]), next_rate)
        self.assertEqual(self.run_case('fnIit', [9200]), 710)
        self.assertEqual(self.run_case('fnIit', [0]), 0)
        self.assertEqual(self.run_case('fnBonusSeparate', [36000]), '3%')
        self.assertEqual(self.run_case('fnBonusSeparate', [36000.12]), '10%')
        self.assertEqual(self.run_case('fnBonusMerge', [120000, 60000]), '20%')

    def test_leave_and_dates(self):
        for years, days in [(0,0),(.99,0),(1,5),(9.99,5),(10,10),(20,15)]:
            self.assertEqual(self.run_case('hrLeave', [years]), days)
        for date, expected in [('2026-10-15','2026-11-16'),('2026-12-31','2027-01-15'),('2026-07-01','2026-08-17')]:
            self.assertEqual(self.run_case('fnVat', [date]), expected)

    def test_existing_arithmetic_and_validation(self):
        for key, values, expected in [('pdStock',[100,20,15],105), ('pdStockAlert',[5,10],'偏低'), ('pdHours',[3,8],24), ('pdDefect',[3,200],1.5), ('stAttendance',[19,20],True), ('cvBmi',[175,70],22.9)]:
            self.assertEqual(self.run_case(key, values), expected)
        for key, values in [('fnIitLevel',[-1]), ('fnIit',['工资10000']), ('fnIit',[float('nan')]), ('pdDefect',[3,0]), ('cvBmi',[0,70])]:
            with self.assertRaises(ValueError):
                self.run_case(key, values)
        self.assertIsNone(self.run_case('fnIit', [None]))
