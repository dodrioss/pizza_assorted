"""
Математические валидаторы для проверки достоверности найденных ПДн.

Реализованные алгоритмы:
    - **Алгоритм Луна** — проверка номеров банковских карт (ISO/IEC 7812).
    - **Контрольная сумма СНИЛС** — по алгоритму ПФР РФ.
    - **Контрольная сумма ИНН** — физических лиц (12 цифр) и
      юридических лиц (10 цифр) по алгоритму ФНС РФ.
    - **Проверка паспорта РФ** — структурная валидация серии и номера
      (математического checksum у паспорта нет, только формат).
    - **MRZ check digit** — контрольная цифра полей MRZ по ИКАО 9303.

Принцип работы:
    Каждая функция принимает строку (возможно с разделителями),
    нормализует её (удаляет пробелы, дефисы) и возвращает ``True``
    если значение валидно, иначе ``False``.

    Функции не бросают исключений — при невалидном вводе
    возвращают ``False``.

Example::

    from detectors.validators import validate_card_luhn, validate_snils

    assert validate_card_luhn("4111 1111 1111 1111")   # Visa тест
    assert validate_snils("112-233-445 95")
    assert not validate_snils("000-000-000 00")
"""

from __future__ import annotations

import re


_DIGITS_ONLY = re.compile(r"\D")


def _digits(value: str) -> str:
    """Возвращает строку, содержащую только цифры.

    Args:
        value: Исходная строка (с пробелами, дефисами и т.п.).

    Returns:
        Строка из цифр.

    Example::

        _digits("123-456 78") == "12345678"
    """
    return _DIGITS_ONLY.sub("", value)



def validate_card_luhn(card_number: str) -> bool:
    """Проверяет номер банковской карты алгоритмом Луна (ISO/IEC 7812).

    Алгоритм:
        1. Удаляем все нецифровые символы.
        2. Двигаемся справа налево, каждую вторую цифру умножаем на 2.
        3. Если результат > 9 — вычитаем 9.
        4. Сумма всех цифр должна делиться на 10.

    Args:
        card_number: Номер карты в любом формате
            (``"4111 1111 1111 1111"``, ``"4111111111111111"`` и т.д.).

    Returns:
        ``True`` если номер проходит проверку Луна и имеет допустимую
        длину (13–19 цифр), иначе ``False``.

    Example::

        validate_card_luhn("4111 1111 1111 1111")  # True  (Visa test)
        validate_card_luhn("1234 5678 9012 3456")  # False
    """
    digits = _digits(card_number)
    if not (13 <= len(digits) <= 19):
        return False

    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:          # каждая вторая цифра (с позиции 1)
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0


def validate_snils(snils: str) -> bool:
    """Проверяет контрольную сумму СНИЛС.

    Алгоритм ПФР РФ:
        1. Удаляем разделители — остаётся 11 цифр.
        2. Первые 9 цифр — сам номер, последние 2 — контрольное число.
        3. Считаем взвешенную сумму: digit[i] * (9 - i) для i = 0..8.
        4. Если сумма < 100 — контрольное число = сумма.
        5. Если сумма == 100 или 101 — контрольное число = 00.
        6. Если сумма > 101 — контрольное число = сумма % 101
           (если результат == 100 или 101 → 00).

    Args:
        snils: СНИЛС в любом формате:
            ``"112-233-445 95"``, ``"11223344595"``.

    Returns:
        ``True`` если контрольная сумма верна, иначе ``False``.

    Note:
        Номера вида ``000-000-000 00`` (все нули) считаются
        невалидными, несмотря на то что контрольная сумма сходится.

    Example::

        validate_snils("112-233-445 95")   # True
        validate_snils("000-000-000 00")   # False  (заглушка)
        validate_snils("123-456-789 01")   # зависит от суммы
    """
    digits = _digits(snils)
    if len(digits) != 11:
        return False

    # Все нули — невалидный номер
    if digits == "0" * 11:
        return False

    number_part = digits[:9]
    check_part = int(digits[9:])

    weight_sum = sum(int(number_part[i]) * (9 - i) for i in range(9))

    if weight_sum < 100:
        expected = weight_sum
    elif weight_sum in (100, 101):
        expected = 0
    else:
        remainder = weight_sum % 101
        expected = 0 if remainder in (100, 101) else remainder

    return check_part == expected



def validate_inn(inn: str) -> bool:
    """Проверяет контрольную сумму ИНН физического или юридического лица.

    Поддерживает:
        - **ИНН юрлица (10 цифр)**: одна контрольная цифра (10-я).
        - **ИНН физлица (12 цифр)**: две контрольные цифры (11-я и 12-я).

    Весовые коэффициенты (ФНС РФ):
        - Для 10-значного: ``[2, 4, 10, 3, 5, 9, 4, 6, 8, 0]``
        - Для 12-значного (11-я): ``[7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]``
        - Для 12-значного (12-я): ``[3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]``

    Args:
        inn: ИНН в виде строки (допускаются пробелы/дефисы).

    Returns:
        ``True`` если ИНН корректен, иначе ``False``.

    Example::

        validate_inn("7707083893")      # True  (ФНС России, 10 цифр)
        validate_inn("500100732259")    # True  (физлицо, 12 цифр)
        validate_inn("1234567890")      # False
    """
    digits = _digits(inn)

    _W10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    _W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    _W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

    def _check(d: str, weights: list[int], position: int) -> bool:
        """Проверяет одну контрольную цифру ИНН.

        Args:
            d: Строка цифр ИНН.
            weights: Весовые коэффициенты.
            position: Позиция контрольной цифры (с нуля).

        Returns:
            ``True`` если контрольная цифра совпадает.
        """
        weighted = sum(int(d[i]) * weights[i] for i in range(len(weights)))
        return (weighted % 11) % 10 == int(d[position])

    if len(digits) == 10:
        return _check(digits, _W10, 9)

    if len(digits) == 12:
        return _check(digits, _W11, 10) and _check(digits, _W12, 11)

    return False



def validate_passport_rf(series: str, number: str) -> bool:
    """Структурно проверяет серию и номер паспорта РФ.

    У паспорта РФ нет публично известного алгоритма контрольной суммы,
    поэтому выполняется только структурная проверка:
        - Серия: ровно 4 цифры.
        - Номер: ровно 6 цифр.
        - Номер не является «нулевым» (``000000``).

    Args:
        series: Серия паспорта (строка, допускаются пробелы).
        number: Номер паспорта (строка, допускаются пробелы).

    Returns:
        ``True`` если структура соответствует, иначе ``False``.

    Example::

        validate_passport_rf("45 10", "123456")  # True
        validate_passport_rf("4510",  "000000")  # False  (нулевой номер)
        validate_passport_rf("1234",  "12345")   # False  (5 цифр в номере)
    """
    s = _digits(series)
    n = _digits(number)

    if len(s) != 4 or len(n) != 6:
        return False

    # Серия: первые 2 цифры — регион (01–99), вторые 2 — год (от 97)
    region = int(s[:2])
    if region < 1 or region > 99:
        return False

    # Номер не может быть нулевым
    if n == "000000":
        return False

    return True



# Таблица символов ИКАО: A=10, B=11, ..., Z=35; цифры = их значение; <  = 0
_MRZ_CHAR_VALUES: dict[str, int] = {
    "<": 0,
    **{str(i): i for i in range(10)},
    **{chr(ord("A") + i): 10 + i for i in range(26)},
}
_MRZ_WEIGHTS = [7, 3, 1]  # веса повторяются циклически


def validate_mrz_check_digit(field: str, check_digit: str) -> bool:
    """Проверяет контрольную цифру поля MRZ по алгоритму ИКАО Doc 9303.

    Алгоритм:
        1. Каждому символу поля присваивается числовое значение
           (цифра — само значение, буква — ord(ch) - 55, «<» — 0).
        2. Каждое значение умножается на вес (7, 3, 1 циклически).
        3. Сумма произведений берётся по модулю 10.
        4. Результат должен совпадать с ``check_digit``.

    Args:
        field: Поле MRZ без контрольной цифры (может содержать «<»).
        check_digit: Одна цифра — контрольный символ.

    Returns:
        ``True`` если контрольная цифра верна, иначе ``False``.

    Example::

        validate_mrz_check_digit("520727", "3")  # True
        validate_mrz_check_digit("D231458907<<<<<<<<<<<<<<<", "2")
    """
    if len(check_digit) != 1 or not check_digit.isdigit():
        return False

    total = 0
    for i, ch in enumerate(field.upper()):
        val = _MRZ_CHAR_VALUES.get(ch, -1)
        if val < 0:
            return False  # недопустимый символ
        total += val * _MRZ_WEIGHTS[i % 3]

    return (total % 10) == int(check_digit)



def validate(pattern_name: str, raw_match: str) -> bool:
    """Диспетчер: выбирает нужный валидатор по имени паттерна.

    Используется в ``pii_detector.py`` для единообразного вызова
    валидации без ветвления.

    Args:
        pattern_name: Имя паттерна из ``regex_patterns.PII_PATTERNS``
            (например ``"card_number"``, ``"snils"``, ``"inn"``).
        raw_match: Строка, найденная паттерном (до очистки).

    Returns:
        ``True`` если значение валидно или валидатор не требуется,
        ``False`` если значение не прошло проверку.

    Example::

        validate("card_number", "4111 1111 1111 1111")  # True
        validate("snils", "112-233-445 95")              # True
        validate("email", "user@example.com")            # True  (нет валидатора → pass)
    """
    match pattern_name:
        case "card_number":
            return validate_card_luhn(raw_match)
        case "snils":
            return validate_snils(raw_match)
        case "inn" | "inn_context":
            return validate_inn(raw_match)
        case "passport_rf":
            # Для паспорта пытаемся разобрать серию и номер из строки
            digits = _digits(raw_match)
            if len(digits) >= 10:
                return validate_passport_rf(digits[:4], digits[4:10])
            return False
        case _:
            # Нет математической валидации — считаем валидным
            return True