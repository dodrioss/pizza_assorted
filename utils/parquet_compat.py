"""
utils/parquet_compat.py — безопасная конвертация PyArrow таблиц в Pandas.

Решает проблему совместимости параметров dtype_backend между версиями
PyArrow и Pandas (особенно при переходе на Pandas 2.x / PyArrow 14+).
"""

import logging

logger = logging.getLogger(__name__)


def safe_to_pandas(table, **kwargs) -> "pd.DataFrame":
    """
    Безопасно конвертирует PyArrow Table в pandas DataFrame.

    Пробует использовать dtype_backend="numpy_nullable" (Pandas 2.0+),
    при ошибке откатывается на стандартный to_pandas().
    """
    import pandas as pd

    kwargs.pop("dtype_backend", None)

    try:
        return table.to_pandas(dtype_backend="numpy_nullable", **kwargs)
    except (TypeError, AttributeError, ValueError) as e:
        logger.debug("PyArrow/Pandas не поддерживают dtype_backend, fallback: %s", e)
        return table.to_pandas(**kwargs)