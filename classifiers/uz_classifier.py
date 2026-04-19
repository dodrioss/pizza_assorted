"""
4-й этап: Классификация уровня защищённости (УЗ-1…УЗ-4) по 152-ФЗ
"""

from typing import Dict


class UZClassifier:
    """Классификатор уровня защищённости персональных данных."""

    # Нормализованные категории (приводим всё к UPPER)
    SPECIAL_CATEGORIES = {
        "БИОМЕТРИЯ", "BIOMETRIC", "BIOMETRY",
        "ЗДОРОВЬЕ", "HEALTH", "MEDICAL",
        "РЕЛИГИЯ", "RELIGION",
        "ПОЛИТИКА", "POLITICAL",
        "РАСА", "RACE", "ETHNICITY",
        "SPECIAL", "SPECIAL_CATEGORY"
    }

    PAYMENT_CATEGORIES = {
        "НОМЕР_КАРТЫ", "CREDIT_CARD", "CARD_NUMBER",
        "БАНКОВСКИЙ_СЧЕТ", "BANK_ACCOUNT", "IBAN",
        "ПЛАТЕЖНЫЕ_ДАННЫЕ", "PAYMENT"
    }

    STATE_ID_CATEGORIES = {
        "ПАСПОРТ", "PASSPORT",
        "СНИЛС", "SNILS",
        "ИНН", "INN",
        "ВОДИТЕЛЬСКОЕ_УДОСТОВЕРЕНИЕ", "DRIVERS_LICENSE",
        "MRZ", "ГОСУДАРСТВЕННЫЕ_ИДЕНТИФИКАТОРЫ"
    }

    ORDINARY_CATEGORIES = {
        "ФИО", "FIO", "FULL_NAME", "NAME",
        "ТЕЛЕФОН", "PHONE",
        "EMAIL",
        "ДАТА_РОЖДЕНИЯ", "BIRTHDATE",
        "АДРЕС", "ADDRESS",
        "МЕСТО_РОЖДЕНИЯ"
    }

    # Пороги
    LARGE_ORDINARY_THRESHOLD = 20   # много обычных ПДн
    LARGE_STATE_THRESHOLD = 5       # много гос. идентификаторов


    def _normalize_key(self, key: str) -> str:
        """Приводим ключ к верхнему регистру для сравнения."""
        return str(key).strip().upper()


    def classify(self, pii_counts: Dict[str, int]) -> str:
        """
        Основной метод классификации.
        pii_counts: { "FIO": 5, "PASSPORT": 2, "PHONE": 10, ... }
        """
        if not pii_counts:
            return "УЗ-4"

        # Нормализуем все ключи
        normalized = {self._normalize_key(k): v for k, v in pii_counts.items() if v > 0}

        # 1. Специальные категории → УЗ-1 (самый высокий уровень)
        if any(cat in self.SPECIAL_CATEGORIES for cat in normalized):
            return "УЗ-1"

        # Подсчёт по группам
        payment_count = sum(normalized.get(cat, 0) for cat in self.PAYMENT_CATEGORIES)
        state_count = sum(normalized.get(cat, 0) for cat in self.STATE_ID_CATEGORIES)
        ordinary_count = sum(normalized.get(cat, 0) for cat in self.ORDINARY_CATEGORIES)

        # 2. Платёжные данные или много гос. идентификаторов → УЗ-2
        if payment_count > 0 or state_count >= self.LARGE_STATE_THRESHOLD:
            return "УЗ-2"

        # 3. Гос. идентификаторы (хоть немного) или много обычных ПДн → УЗ-3
        if state_count > 0 or ordinary_count >= self.LARGE_ORDINARY_THRESHOLD:
            return "УЗ-3"

        # 4. Только немного обычных ПДн → УЗ-4
        return "УЗ-4"


if __name__ == "__main__":
    classifier = UZClassifier()
    
    test_cases = [
        ({"FIO": 3, "EMAIL": 2}, "УЗ-4"),
        ({"FIO": 25, "PHONE": 15}, "УЗ-3"),
        ({"PASSPORT": 3}, "УЗ-3"),
        ({"SNILS": 7, "FIO": 5}, "УЗ-2"),
        ({"CREDIT_CARD": 1}, "УЗ-2"),
        ({"HEALTH": 1}, "УЗ-1"),
        ({"BIOMETRIC": 2, "FIO": 100}, "УЗ-1"),
        ({"passport": 4, "phone": 30}, "УЗ-3"),   
    ]

    print("=== ТЕСТЫ UZClassifier ===\n")
    for counts, expected in test_cases:
        result = classifier.classify(counts)
        status = "OK" if result == expected else "BAD"
        print(f"{status}  {counts}  →  {result} (ожидали {expected})")