"""
Регулярные выражения и ключевые слова для поиска персональных данных (ПДн).

Все паттерны соответствуют категориям ПДн по 152-ФЗ «О персональных данных»:

Категории:
    - **ФИО** — фамилия, имя, отчество
    - **Контактные данные** — телефоны, e-mail
    - **Дата и место рождения**
    - **Адрес** — проживания / регистрации
    - **Паспорт РФ** — серия и номер
    - **СНИЛС** — страховой номер
    - **ИНН** — физических и юридических лиц
    - **Водительское удостоверение**
    - **MRZ** — машиносчитываемая зона документов
    - **Банковские карты** — номер, CVV, срок действия
    - **Банковские счета** — номера счетов и БИК
    - **Биометрия** — упоминания биометрических характеристик
    - **Специальные категории** — здоровье, религия, политика, раса

Соглашение об именовании:
    Каждый паттерн — скомпилированный объект ``re.Pattern``.
    Группы именованные (``(?P<name>...)``), если нужна валидация.

Флаги:
    По умолчанию ``re.IGNORECASE | re.UNICODE``.
    Многострочные паттерны компилируются с ``re.VERBOSE``.

Example::

    from detectors.regex_patterns import PII_PATTERNS, SPECIAL_KEYWORDS
    import re

    for category, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(text):
            print(category, match.group())
"""

from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Вспомогательные константы
# ---------------------------------------------------------------------------

_F = re.IGNORECASE | re.UNICODE

# Граница слова, совместимая с кириллицей (lookahead/lookbehind)
_WB_L = r"(?<![А-Яа-яЁёA-Za-z0-9_])"
_WB_R = r"(?![А-Яа-яЁёA-Za-z0-9_])"


def _wb(pattern: str) -> str:
    """Оборачивает паттерн в кириллица-совместимые границы слова."""
    return _WB_L + pattern + _WB_R


# Русская фамилия + имя (обязательно) + необязательное отчество
# Покрывает: «Иванов Иван Иванович», «Иванова Мария», «Петров-Водкин Кузьма»
_FULL_NAME_RU = re.compile(
    r"""
    (?<![А-ЯЁ])                        # не начинается с прописной (не середина слова)
    (?P<last>   [А-ЯЁ][а-яё]+-?[а-яё]*)   # Фамилия (с дефисом)
    \s+
    (?P<first>  [А-ЯЁ][а-яё]+)           # Имя
    (?:
        \s+
        (?P<middle> [А-ЯЁ][а-яё]+(?:вич|вна|ович|овна|евич|евна|ич|на))  # Отчество
    )?
    """,
    re.VERBOSE | re.UNICODE,
)

# Инициалы рядом с фамилией: «Иванов И.И.» / «И.И. Иванов»
_INITIALS_NAME_RU = re.compile(
    r"""
    (?:
        [А-ЯЁ][а-яё]+-?[а-яё]*\s+[А-ЯЁ]\.[А-ЯЁ]\.   # Фамилия И.О.
        |
        [А-ЯЁ]\.[А-ЯЁ]\.\s+[А-ЯЁ][а-яё]+-?[а-яё]*   # И.О. Фамилия
    )
    """,
    re.VERBOSE | re.UNICODE,
)


# Покрывает форматы:
# +7 (999) 123-45-67   8 (999) 123-45-67
# +79991234567         89991234567
# 8-999-123-45-67      +7 999 123 45 67
_PHONE_RU = re.compile(
    r"""
    (?<!\d)
    (?:
        (?:\+7|8)                         # код страны
        [\s\-\(]*
        (?:\d{3})                         # код региона (3 цифры)
        [\s\-\)]*
        \d{3}                             # первые 3 цифры номера
        [\s\-]?
        \d{2}                             # следующие 2
        [\s\-]?
        \d{2}                             # последние 2
    )
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)

_EMAIL = re.compile(
    r"""
    (?<![A-Za-z0-9._%+\-])
    [A-Za-z0-9._%+\-]{1,64}
    @
    [A-Za-z0-9.\-]{1,253}
    \.[A-Za-z]{2,10}
    (?![A-Za-z0-9._%+\-@])
    """,
    re.VERBOSE | re.UNICODE,
)


# ДД.ММ.ГГГГ  |  ДД/ММ/ГГГГ  |  ДД-ММ-ГГГГ  |  ГГГГ-ММ-ДД
_DATE_OF_BIRTH = re.compile(
    r"""
    (?<!\d)
    (?:
        (?:0?[1-9]|[12]\d|3[01])   # день
        [.\-/]
        (?:0?[1-9]|1[0-2])         # месяц
        [.\-/]
        (?:19|20)\d{2}             # год (1900-2099)
        |
        (?:19|20)\d{2}             # ISO: год
        -
        (?:0?[1-9]|1[0-2])
        -
        (?:0?[1-9]|[12]\d|3[01])
    )
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)

# «23 января 1985 года»
_DATE_VERBAL = re.compile(
    r"""
    (?<!\d)
    (?:0?[1-9]|[12]\d|3[01])\s+
    (?:январ[яь]|феврал[яь]|март[аe]?|апрел[яь]|ма[йя]|июн[яь]|
       июл[яь]|август[аe]?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])
    \s+
    (?:19|20)\d{2}
    (?:\s+года?)?
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)


# Упоминание адреса: «ул. Ленина, д. 5, кв. 12» / «пр-т Мира 17-34»
_ADDRESS_RU = re.compile(
    r"""
    (?:
        (?:ул(?:ица)?\.?\s*|пр(?:-?т|оспект)?\.?\s*|пер(?:еулок)?\.?\s*|
           бул(?:ьвар)?\.?\s*|наб(?:ережная)?\.?\s*|пл(?:ощадь)?\.?\s*|
           ш(?:оссе)?\.?\s*|тракт\.?\s*)
        [А-ЯЁа-яёA-Za-z0-9\s\-\.]{2,50}
        [,\s]+
        (?:д(?:ом)?\.?\s*\d+[а-яА-Я]?(?:/\d+)?)?
        (?:[,\s]+кв(?:артира)?\.?\s*\d+)?
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

# Почтовый индекс РФ
_POSTAL_CODE_RU = re.compile(r"(?<!\d)[1-6]\d{5}(?!\d)")


# Серия 4 цифры + номер 6 цифр (с различными разделителями)
# Форматы: «4510 123456», «45 10 123456», «4510123456»
_PASSPORT_RF = re.compile(
    r"""
    (?<!\d)
    (?P<series>
        \d{2}\s?\d{2}     # серия: 4 цифры (с необязательным пробелом)
    )
    [\s\-]?
    (?P<number>
        \d{6}             # номер: 6 цифр
    )
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)

# Контекстный паттерн: ключевое слово + серия/номер
_PASSPORT_RF_CONTEXT = re.compile(
    r"""
    (?:паспорт|passport|пасп\.?|серия\s+и\s+номер)
    [\s:№#]*
    \d{2}\s?\d{2}[\s\-]?\d{6}
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

# MRZ (Machine Readable Zone): строки вида «P<RUSFAMILIYA<<IMYA<<<<<<<<<<»
_MRZ_LINE = re.compile(
    r"""
    [A-Z0-9<]{30,44}        # MRZ-строка TD1/TD3
    """,
    re.VERBOSE | re.UNICODE,
)


# Форматы: «123-456-789 01», «12345678901», «123 456 789 01»
_SNILS = re.compile(
    r"""
    (?<!\d)
    (?P<snils>
        \d{3}[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}
    )
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)


# ИНН физлица: 12 цифр; ИНН юрлица: 10 цифр
_INN = re.compile(
    r"""
    (?<!\d)
    (?P<inn>
        \d{12}     # физлицо
        |
        \d{10}     # юрлицо
    )
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)

# Контекстный ИНН: рядом ключевое слово
_INN_CONTEXT = re.compile(
    r"(?:инн|inn|taxpayer)[\s:№#]*(?P<inn>\d{10}(?:\d{2})?)",
    re.IGNORECASE | re.UNICODE,
)

# Серия 2 цифры 2 буквы + номер 6 цифр (или полностью цифровой)
_DRIVER_LICENSE = re.compile(
    r"""
    (?:
        вод(?:ительское)?\s+уд(?:остоверение)?|
        в\.у\.|ву\b|driver.?licen[cs]e
    )
    [\s:№#]*
    (?P<series>\d{2}\s?[А-ЯЁA-Z]{2}|\d{4})
    [\s\-]?
    (?P<number>\d{6})
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)


# Номер карты (Luhn): 13-19 цифр с разделителями пробел/дефис
# Покрывает Visa (4...), MC (5...), МИР (2...), Amex (3...)
_CARD_NUMBER = re.compile(
    r"""
    (?<!\d)
    (?:
        \d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,4}   # стандарт 16 цифр
        |
        \d{4}[\s\-]?\d{6}[\s\-]?\d{5}                 # Amex 15 цифр
        |
        \d{13}                                        # короткий формат
    )
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)

# CVV/CVC: 3-4 цифры рядом с ключевым словом
_CVV = re.compile(
    r"(?:cvv|cvc|cvv2|cvc2|cv2|csc)[\s:]*(?P<cvv>\d{3,4})",
    re.IGNORECASE | re.UNICODE,
)

# Срок действия карты: MM/YY или MM/YYYY
_CARD_EXPIRY = re.compile(
    r"""
    (?<!\d)
    (?:0[1-9]|1[0-2])   # месяц
    /
    (?:\d{2}|\d{4})     # год (2 или 4 цифры)
    (?!\d)
    """,
    re.VERBOSE | re.UNICODE,
)


# Расчётный счёт РФ: 20 цифр
_BANK_ACCOUNT = re.compile(
    r"""
    (?:
        р/?с|расч(?:ётный|ет\.|ет)\s+счёт?|bank\s+account|account
    )
    [\s:№#]*
    (?P<account>\d{20})
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

# БИК: 9 цифр, начинается с 04
_BIC = re.compile(
    r"""
    (?:бик|bik|bic)[\s:]*(?P<bic>04\d{7})
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

# IBAN
_IBAN = re.compile(
    r"(?<![A-Z])[A-Z]{2}\d{2}[A-Z0-9]{4,30}(?![A-Z0-9])",
    re.UNICODE,
)


_BIOMETRIC_KEYWORDS = re.compile(
    r"""
    (?:
        отпечат(?:ок|ки)\s+пальц|
        дактилоскопи|
        сетчатк[аи]\s+глаз|
        радужн(?:ая|ой)\s+оболочк|
        рисунок\s+вен|
        геометри[ия]\s+лиц|
        распознавани[ея]\s+лиц|
        голосов(?:ой|ые)\s+(?:образец|данные|биометр)|
        face\s+recognition|
        fingerprint|
        iris\s+scan|
        retina\s+scan|
        voice\s+(?:print|sample)|
        biometric
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)


_HEALTH_KEYWORDS = re.compile(
    r"""
    (?:
        диагноз|диагностика|заболевани[ея]|болезн[ьи]|
        инвалидност[ьи]|инвалид\b|
        мед(?:ицинск(?:ий|ая|ое|ие))?\s+(?:карт[аы]|заключени[ея]|справк[аи]|
            анализ|осмотр|история)|
        история\s+болезни|
        амбулаторн(?:ая|ый)\s+карт[аы]|
        эпикриз|выписк[аи]\s+из\s+(?:больниц|клиник)|
        рецепт\b|назначени[ея]\s+врача|
        группа\s+крови|
        вич|спид|hiv|aids|
        психиатри|наркологи|онкологи|кардиологи
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

_RELIGION_KEYWORDS = re.compile(
    r"""
    (?:
        вероисповедани[ея]|религи(?:я|озн)|
        православ|католи|ислам|мусульман|буддист|иудей|
        церков|мечет[ьи]|синагог|
        атеист|агностик|
        religion|faith|muslim|christian|buddhist|jewish
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

_POLITICAL_KEYWORDS = re.compile(
    r"""
    (?:
        политическ(?:ие|их)\s+взгляд|
        политическ(?:ие|ие)\s+убежден|
        член\s+(?:партии|профсоюза)|
        партийн(?:ость|ая\s+принадлежность)|
        политическ(?:ая|ие)\s+принадлежн
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

_RACE_KEYWORDS = re.compile(
    r"""
    (?:
        национальн(?:ость|ая\s+принадлежность)|
        расов(?:ая|ое)\s+(?:принадлежность|происхождение)|
        этническ(?:ое|ая)\s+(?:происхождение|принадлежность)|
        этнос\b|этничность
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

_CRIMINAL_KEYWORDS = re.compile(
    r"""
    (?:
        судим(?:ость|ости)|
        уголовн(?:ое|ый)\s+(?:дело|преследование|запись)|
        привлекался\s+к\s+уголовной|
        снят(?:ие|ие)\s+судимости
    )
    """,
    re.VERBOSE | re.IGNORECASE | re.UNICODE,
)

class PatternMeta(NamedTuple):
    """Метаданные одного PII-паттерна.

    Attributes:
        pattern: Скомпилированный объект ``re.Pattern``.
        category: Категория ПДн (строка-идентификатор).
        description: Человекочитаемое описание.
        requires_validation: Нужна ли дополнительная математическая
            валидация (алгоритм Луна, контрольные суммы).
        is_special_category: Относится ли к специальным категориям
            по ст. 10 152-ФЗ (ч. 1) → влияет на УЗ-1.
        is_biometric: Является ли биометрическими данными → УЗ-1.
    """

    pattern: re.Pattern
    category: str
    description: str
    requires_validation: bool = False
    is_special_category: bool = False
    is_biometric: bool = False


# Реестр: имя → PatternMeta
# Используется в pii_detector.py для итерации по всем паттернам
PII_PATTERNS: dict[str, PatternMeta] = {
    # --- ФИО ---
    "full_name": PatternMeta(
        pattern=_FULL_NAME_RU,
        category="full_name",
        description="ФИО (фамилия + имя + отчество)",
    ),
    "initials_name": PatternMeta(
        pattern=_INITIALS_NAME_RU,
        category="full_name",
        description="ФИО с инициалами",
    ),
    # --- Контактные данные ---
    "phone": PatternMeta(
        pattern=_PHONE_RU,
        category="contact",
        description="Номер телефона (РФ)",
    ),
    "email": PatternMeta(
        pattern=_EMAIL,
        category="contact",
        description="Адрес электронной почты",
    ),
    # --- Дата рождения ---
    "date_of_birth": PatternMeta(
        pattern=_DATE_OF_BIRTH,
        category="birth_info",
        description="Дата рождения (цифровой формат)",
    ),
    "date_verbal": PatternMeta(
        pattern=_DATE_VERBAL,
        category="birth_info",
        description="Дата рождения (словесный формат)",
    ),
    # --- Адрес ---
    "address": PatternMeta(
        pattern=_ADDRESS_RU,
        category="address",
        description="Адрес проживания/регистрации",
    ),
    "postal_code": PatternMeta(
        pattern=_POSTAL_CODE_RU,
        category="address",
        description="Почтовый индекс РФ",
    ),
    # --- Документы ---
    "passport_rf": PatternMeta(
        pattern=_PASSPORT_RF_CONTEXT,
        category="government_id",
        description="Паспорт РФ (серия и номер, контекстный)",
        requires_validation=True,
    ),
    "snils": PatternMeta(
        pattern=_SNILS,
        category="government_id",
        description="СНИЛС",
        requires_validation=True,
    ),
    "inn": PatternMeta(
        pattern=_INN_CONTEXT,
        category="government_id",
        description="ИНН (контекстный)",
        requires_validation=True,
    ),
    "driver_license": PatternMeta(
        pattern=_DRIVER_LICENSE,
        category="government_id",
        description="Водительское удостоверение",
    ),
    "mrz": PatternMeta(
        pattern=_MRZ_LINE,
        category="government_id",
        description="MRZ (машиносчитываемая зона документов)",
    ),
    # --- Платёжные данные ---
    "card_number": PatternMeta(
        pattern=_CARD_NUMBER,
        category="payment",
        description="Номер банковской карты",
        requires_validation=True,
    ),
    "cvv": PatternMeta(
        pattern=_CVV,
        category="payment",
        description="CVV/CVC код карты",
    ),
    "card_expiry": PatternMeta(
        pattern=_CARD_EXPIRY,
        category="payment",
        description="Срок действия карты",
    ),
    "bank_account": PatternMeta(
        pattern=_BANK_ACCOUNT,
        category="payment",
        description="Номер банковского счёта",
    ),
    "bic": PatternMeta(
        pattern=_BIC,
        category="payment",
        description="БИК банка",
    ),
    "iban": PatternMeta(
        pattern=_IBAN,
        category="payment",
        description="IBAN",
    ),
    # --- Биометрия ---
    "biometric": PatternMeta(
        pattern=_BIOMETRIC_KEYWORDS,
        category="biometric",
        description="Упоминание биометрических данных",
        is_biometric=True,
    ),
    # --- Специальные категории ---
    "health": PatternMeta(
        pattern=_HEALTH_KEYWORDS,
        category="special",
        description="Сведения о состоянии здоровья",
        is_special_category=True,
    ),
    "religion": PatternMeta(
        pattern=_RELIGION_KEYWORDS,
        category="special",
        description="Религиозные убеждения",
        is_special_category=True,
    ),
    "political": PatternMeta(
        pattern=_POLITICAL_KEYWORDS,
        category="special",
        description="Политические взгляды",
        is_special_category=True,
    ),
    "race_ethnicity": PatternMeta(
        pattern=_RACE_KEYWORDS,
        category="special",
        description="Расовая/национальная принадлежность",
        is_special_category=True,
    ),
    "criminal": PatternMeta(
        pattern=_CRIMINAL_KEYWORDS,
        category="special",
        description="Судимость и уголовное преследование",
        is_special_category=True,
    ),
}

# Удобный набор только скомпилированных паттернов (без мета)
COMPILED_PATTERNS: dict[str, re.Pattern] = {
    name: meta.pattern for name, meta in PII_PATTERNS.items()
}

# Имена паттернов, требующих математической валидации
VALIDATION_REQUIRED: frozenset[str] = frozenset(
    name for name, meta in PII_PATTERNS.items() if meta.requires_validation
)

# Имена паттернов, дающих УЗ-1 при обнаружении
UZ1_PATTERN_NAMES: frozenset[str] = frozenset(
    name
    for name, meta in PII_PATTERNS.items()
    if meta.is_special_category or meta.is_biometric
)