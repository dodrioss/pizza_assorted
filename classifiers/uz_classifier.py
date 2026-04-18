"""
4-й этап: Классификация уровня защищённости (УЗ-1…УЗ-4)
по требованиям Федерального закона № 152-ФЗ
"""

from typing import Dict

class UZClassifier:
    """Классификатор уровня защищённости информационной системы."""

    # Группировка категорий ПДн (ключи должны совпадать с теми, что возвращает pii_detector)
    SPECIAL_BIOMETRIC_CATS = {
        "БИОМЕТРИЯ", "ЗДОРОВЬЕ", "РЕЛИГИЯ", "ПОЛИТИКА", "РАСА",
        "СПЕЦИАЛЬНЫЕ_КАТЕГОРИИ", "БИОМЕТРИЧЕСКИЕ_ДАННЫЕ"
    }

    PAYMENT_CATS = {"НОМЕР_КАРТЫ", "БАНКОВСКИЙ_СЧЕТ", "БИК", "ПЛАТЕЖНЫЕ_ДАННЫЕ"}

    STATE_ID_CATS = {
        "ПАСПОРТ", "СНИЛС", "ИНН", "ВОДИТЕЛЬСКОЕ_УДОСТОВЕРЕНИЕ",
        "MRZ", "ГОСУДАРСТВЕННЫЕ_ИДЕНТИФИКАТОРЫ"
    }

    ORDINARY_CATS = {
        "ФИО", "ТЕЛЕФОН", "EMAIL", "ДАТА_РОЖДЕНИЯ", "АДРЕС",
        "МЕСТО_РОЖДЕНИЯ", "КОНТАКТНАЯ_ИНФОРМАЦИЯ"
    }

    # Пороги «больших объёмов» (настраиваемо)
    LARGE_ORDINARY_THRESHOLD = 20      # обычных ПДн
    LARGE_STATE_THRESHOLD = 5          # государственных идентификаторов

    def classify(self, pii_counts: Dict[str, int]) -> str:
        """
        Возвращает УЗ-1…УЗ-4 на основе обнаруженных категорий и их количества.
        pii_counts — словарь {категория: количество_находок}
        """
        if not pii_counts:
            return "УЗ-4"

        # 1. Специальные категории или биометрия → УЗ-1 (самый высокий риск)
        if any(cat in self.SPECIAL_BIOMETRIC_CATS for cat in pii_counts if pii_counts[cat] > 0):
            return "УЗ-1"

        # Подсчёт по группам
        payment_count = sum(pii_counts.get(cat, 0) for cat in self.PAYMENT_CATS)
        state_count = sum(pii_counts.get(cat, 0) for cat in self.STATE_ID_CATS)
        ordinary_count = sum(pii_counts.get(cat, 0) for cat in self.ORDINARY_CATS)

        # 2. Платёжная информация ИЛИ гос. идентификаторы в больших объёмах → УЗ-2
        if payment_count > 0 or state_count >= self.LARGE_STATE_THRESHOLD:
            return "УЗ-2"

        # 3. Гос. идентификаторы в малых объёмах ИЛИ обычные ПДн в больших объёмах → УЗ-3
        if state_count > 0 or ordinary_count >= self.LARGE_ORDINARY_THRESHOLD:
            return "УЗ-3"

        # 4. Только обычные ПДн в малых объёмах → УЗ-4
        return "УЗ-4"


# ====================== ТЕСТОВЫЕ ДАННЫЕ ======================
if __name__ == "__main__":
    classifier = UZClassifier()

    test_cases = [
        ({"ФИО": 3, "EMAIL": 2}, "УЗ-4"),                    # только обычные, мало
        ({"ФИО": 25, "ТЕЛЕФОН": 15}, "УЗ-3"),                # обычные в большом объёме
        ({"ПАСПОРТ": 3}, "УЗ-3"),                            # гос. идентификаторы мало
        ({"ПАСПОРТ": 7}, "УЗ-2"),                            # гос. идентификаторы много
        ({"НОМЕР_КАРТЫ": 1}, "УЗ-2"),                       # платёжка
        ({"ЗДОРОВЬЕ": 1}, "УЗ-1"),                           # специальная категория
        ({"БИОМЕТРИЯ": 2, "ФИО": 100}, "УЗ-1"),             # биометрия перекрывает всё
    ]

    for counts, expected in test_cases:
        result = classifier.classify(counts)
        print(f"Counts: {counts} => {result}  {'OK' if result == expected else 'Bad'}")