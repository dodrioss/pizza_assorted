"""
tests/test_uz_classifier.py — Полный набор тестов для UZClassifier
"""

import unittest
from classifiers.uz_classifier import UZClassifier


class TestUZClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = UZClassifier()

    # ====================== БАЗОВЫЕ ТЕСТЫ ======================

    def test_empty_or_none(self):
        """Пустой ввод должен возвращать УЗ-4"""
        self.assertEqual(self.classifier.classify({}), "УЗ-4")
        self.assertEqual(self.classifier.classify(None), "УЗ-4")
        self.assertEqual(self.classifier.classify({}), "УЗ-4")

    # ====================== ОБЫЧНЫЕ ПДн ======================

    def test_ordinary_small_volume(self):
        """Малое количество обычных ПДн → УЗ-4"""
        cases = [
            {"FIO": 5, "EMAIL": 3, "PHONE": 4},
            {"ADDRESS": 8},
            {"FIO": 12, "BIRTHDATE": 3},
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), "УЗ-4")

    def test_ordinary_large_volume(self):
        """Большое количество обычных ПДн → УЗ-3"""
        cases = [
            {"FIO": 25, "PHONE": 15},
            {"EMAIL": 30, "ADDRESS": 12, "FIO": 8},
            {"PHONE": 22, "EMAIL": 18},
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), "УЗ-3")

    # ====================== ГОСУДАРСТВЕННЫЕ ИДЕНТИФИКАТОРЫ ======================

    def test_state_id_small(self):
        """Небольшое количество гос. идентификаторов → УЗ-3"""
        cases = [
            {"PASSPORT": 3},
            {"SNILS": 2},
            {"INN": 4, "FIO": 10},
            {"PASSPORT": 1, "SNILS": 1},
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), "УЗ-3")

    def test_state_id_large(self):
        """Большое количество гос. идентификаторов → УЗ-2"""
        cases = [
            {"PASSPORT": 6},
            {"SNILS": 7},
            {"INN": 8, "PASSPORT": 3},
            {"SNILS": 5, "FIO": 20},
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), "УЗ-2")

    # ====================== ПЛАТЁЖНЫЕ ДАННЫЕ ======================

    def test_payment_data(self):
        """Любые платёжные данные → УЗ-2"""
        cases = [
            {"CREDIT_CARD": 1},
            {"BANK_ACCOUNT": 3},
            {"CREDIT_CARD": 5, "FIO": 50},
            {"IBAN": 2},
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), "УЗ-2")

    # ====================== СПЕЦИАЛЬНЫЕ КАТЕГОРИИ ======================

    def test_special_categories(self):
        """Специальные категории всегда дают УЗ-1"""
        cases = [
            {"HEALTH": 1},
            {"BIOMETRIC": 2},
            {"RELIGION": 1},
            {"POLITICAL": 3},
            {"RACE": 1},
            {"HEALTH": 1, "FIO": 100},
            {"BIOMETRIC": 5},
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), "УЗ-1")

    # ====================== РЕГИСТРОНЕЗАВИСИМОСТЬ ======================

    def test_case_insensitivity(self):
        """Проверка нечувствительности к регистру и разным вариантам написания"""
        cases = [
            ({"fio": 25, "phone": 10}, "УЗ-3"),
            ({"Passport": 6}, "УЗ-2"),
            ({"snils": 8}, "УЗ-2"),
            ({"health": 1}, "УЗ-1"),
            ({"credit_card": 2}, "УЗ-2"),
            ({"Biometric": 1}, "УЗ-1"),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), expected)

    # ====================== СМЕШАННЫЕ СЦЕНАРИИ ======================

    def test_mixed_scenarios(self):
        """Сложные смешанные случаи"""
        cases = [
            ({"FIO": 30, "PASSPORT": 2}, "УЗ-2"),      # гос. ид. перекрывает
            ({"EMAIL": 40, "PHONE": 25}, "УЗ-3"),      # много обычных
            ({"CREDIT_CARD": 1, "FIO": 100}, "УЗ-2"),
            ({"BIOMETRIC": 1, "PASSPORT": 10}, "УЗ-1"), # специальная категория важнее всего
            ({"SNILS": 4, "EMAIL": 15}, "УЗ-3"),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(self.classifier.classify(data), expected)

    # ====================== КРАЕВЫЕ СЛУЧАИ ======================

    def test_edge_cases(self):
        """Краевые значения порогов"""
        self.assertEqual(self.classifier.classify({"FIO": 19}), "УЗ-4")   # ниже порога
        self.assertEqual(self.classifier.classify({"FIO": 20}), "УЗ-3")   # на пороге
        self.assertEqual(self.classifier.classify({"PASSPORT": 4}), "УЗ-3") # ниже порога
        self.assertEqual(self.classifier.classify({"PASSPORT": 5}), "УЗ-2") # на пороге


if __name__ == "__main__":
    unittest.main(verbosity=2)