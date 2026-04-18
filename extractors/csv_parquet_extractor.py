"""
Экстрактор текстового содержимого из структурированных файлов данных.

Поддерживаемые форматы:
    - **CSV** (``.csv``) — с автоматическим определением разделителя
      и кодировки; большие файлы читаются чанками.
    - **Parquet** (``.parquet``) — через PyArrow; только строковые
      и категориальные столбцы попадают в извлечённый текст.

Стратегия извлечения:
    Данные преобразуются в *текстовое представление* — строки таблицы
    объединяются через пробел/новую строку, что позволяет детектору PII
    искать персональные данные с помощью регулярных выражений.

    Числовые столбцы (int, float) включаются только если находятся
    в «белом списке» имён (напр., ``inn``, ``snils``, ``phone``), так как
    сами по себе не несут PII, но в качестве идентификаторов — несут.

Зависимости:
    - ``pandas``
    - ``pyarrow`` (только для Parquet)

Example::

    from extractors.csv_parquet_extractor import CsvParquetExtractor

    result = CsvParquetExtractor("customers.csv").extract()
    print(f"Строк: {result.metadata['row_count']}")
    print(result.text[:300])
"""

from __future__ import annotations

import logging
import os
from typing import Iterator

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError

logger = logging.getLogger(__name__)

# Имена столбцов (lowercase), числовые значения которых тоже включаются
# в текст — т.к. они могут содержать идентификаторы PII.
_PII_NUMERIC_COLUMN_KEYWORDS: frozenset[str] = frozenset(
    {
        "inn", "инн", "snils", "снилс", "phone", "телефон", "passport",
        "паспорт", "card", "карта", "account", "счет", "счёт", "zip",
        "postal", "индекс", "ogrn", "огрн", "kpp", "кпп",
    }
)

# Чанк по умолчанию для чтения CSV (строк за раз)
_CSV_CHUNK_SIZE = 5_000

# Максимальное число строк в итоговом тексте (остаток игнорируется при
# быстрой проверке — полный анализ выполняется через extract_chunks)
_MAX_ROWS_IN_MEMORY = 50_000


class CsvParquetExtractor(BaseExtractor):
    """Экстрактор для CSV и Parquet файлов с поддержкой чанкинга.

    Args:
        file_path: Путь к ``.csv`` или ``.parquet`` файлу.
        csv_chunk_size: Количество строк, читаемых за один раз при
            обработке CSV.  По умолчанию 5 000.
        max_rows: Максимальное число строк, включаемых в объединённый
            ``text`` результата.  Остальные строки доступны через
            :meth:`extract_chunks`.  По умолчанию 50 000.

    Raises:
        FileNotFoundError: Если файл не найден.
    """

    def __init__(
        self,
        file_path: str,
        csv_chunk_size: int = _CSV_CHUNK_SIZE,
        max_rows: int = _MAX_ROWS_IN_MEMORY,
    ) -> None:
        super().__init__(file_path)
        self._csv_chunk_size = csv_chunk_size
        self._max_rows = max_rows
        self._ext = os.path.splitext(file_path)[-1].lower()

    
    def extract(self) -> ExtractionResult:
        """Извлекает текстовое представление табличных данных.

        Для больших файлов загружает не более ``max_rows`` строк в память.
        Полный обход доступен через :meth:`extract_chunks`.

        Returns:
            :class:`~extractors.base.ExtractionResult` с текстом и
            метаданными:

            - ``row_count`` — общее число строк (если известно)
            - ``column_count`` — число столбцов
            - ``columns`` — список имён столбцов
            - ``encoding`` — кодировка (только для CSV)
            - ``truncated`` — ``True`` если данные обрезаны по ``max_rows``

        Raises:
            ExtractionError: При ошибке чтения файла.
        """
        start = self._log_start()

        if self._ext == ".parquet":
            result = self._extract_parquet(start)
        else:
            result = self._extract_csv(start)

        self._log_done(result)
        return result

    def extract_chunks(self) -> Iterator[str]:
        """Генератор текстовых чанков для потоковой обработки.

        Каждый чанк содержит текстовое представление одного блока строк.

        Yields:
            Строки таблицы, объединённые в текстовый блок.

        Raises:
            ExtractionError: При ошибке чтения файла.
        """
        if self._ext == ".parquet":
            yield from self._iter_parquet_chunks()
        else:
            yield from self._iter_csv_chunks()


    def _extract_csv(self, start: float) -> ExtractionResult:
        """Читает CSV и формирует текстовый результат.

        Args:
            start: Монотонное время начала.

        Returns:
            :class:`~extractors.base.ExtractionResult`.

        Raises:
            ExtractionError: При ошибке чтения файла.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ExtractionError(
                self.file_path, "Библиотека 'pandas' не установлена."
            ) from exc

        encoding, sep = self._detect_csv_params()

        chunks: list[str] = []
        total_rows = 0
        columns: list[str] = []
        truncated = False

        try:
            reader = pd.read_csv(
                self.file_path,
                sep=sep,
                encoding=encoding,
                chunksize=self._csv_chunk_size,
                dtype=str,  # читаем всё как строки для PII-поиска
                on_bad_lines="skip",
                low_memory=False,
            )
            for df_chunk in reader:
                if not columns:
                    columns = df_chunk.columns.tolist()

                chunk_text = self._dataframe_to_text(df_chunk)
                if chunk_text:
                    chunks.append(chunk_text)

                total_rows += len(df_chunk)
                if total_rows >= self._max_rows:
                    truncated = True
                    break

        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Ошибка чтения CSV: {exc}"
            ) from exc

        full_text = "\n".join(chunks)
        return self._make_result(
            text=full_text,
            chunks=chunks,
            metadata={
                "row_count": total_rows,
                "column_count": len(columns),
                "columns": columns,
                "encoding": encoding,
                "separator": sep,
                "truncated": truncated,
            },
            start_time=start,
        )

    def _iter_csv_chunks(self) -> Iterator[str]:
        """Итерирует CSV по чанкам без ограничения на число строк.

        Yields:
            Текстовый фрагмент на каждый чанк строк.

        Raises:
            ExtractionError: При ошибке чтения.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ExtractionError(
                self.file_path, "Библиотека 'pandas' не установлена."
            ) from exc

        encoding, sep = self._detect_csv_params()

        try:
            reader = pd.read_csv(
                self.file_path,
                sep=sep,
                encoding=encoding,
                chunksize=self._csv_chunk_size,
                dtype=str,
                on_bad_lines="skip",
                low_memory=False,
            )
            for df_chunk in reader:
                chunk_text = self._dataframe_to_text(df_chunk)
                if chunk_text:
                    yield chunk_text
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Ошибка чтения CSV: {exc}"
            ) from exc

    def _detect_csv_params(self) -> tuple[str, str]:
        """Определяет кодировку и разделитель CSV-файла.

        Пробует кодировки по приоритету: UTF-8 → cp1251 → latin-1.
        Разделитель определяет ``csv.Sniffer``.

        Returns:
            Кортеж ``(encoding, separator)``.
        """
        import csv

        encodings = ["utf-8-sig", "utf-8", "cp1251", "latin-1"]
        encoding = "utf-8"
        sep = ","

        for enc in encodings:
            try:
                with open(self.file_path, encoding=enc, errors="strict") as f:
                    sample = f.read(4096)
                encoding = enc
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                    sep = dialect.delimiter
                except csv.Error:
                    sep = ","
                break
            except (UnicodeDecodeError, LookupError):
                continue

        return encoding, sep


    def _extract_parquet(self, start: float) -> ExtractionResult:
        """Читает Parquet-файл и формирует текстовый результат.

        Args:
            start: Монотонное время начала.

        Returns:
            :class:`~extractors.base.ExtractionResult`.

        Raises:
            ExtractionError: При ошибке чтения файла.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ExtractionError(
                self.file_path,
                "Библиотека 'pyarrow' не установлена. "
                "Выполните: pip install pyarrow",
            ) from exc

        try:
            table = pq.read_table(self.file_path)
            df = table.to_pandas(dtype_backend="numpy_nullable")
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Ошибка чтения Parquet: {exc}"
            ) from exc

        truncated = False
        if len(df) > self._max_rows:
            df = df.iloc[: self._max_rows]
            truncated = True

        chunk_text = self._dataframe_to_text(df)
        chunks = [chunk_text] if chunk_text else []

        return self._make_result(
            text=chunk_text,
            chunks=chunks,
            metadata={
                "row_count": len(table),
                "column_count": len(df.columns),
                "columns": df.columns.tolist(),
                "truncated": truncated,
            },
            start_time=start,
        )

    def _iter_parquet_chunks(self) -> Iterator[str]:
        """Итерирует Parquet по батчам строк.

        Yields:
            Текстовый фрагмент для каждого батча.

        Raises:
            ExtractionError: При ошибке чтения.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ExtractionError(
                self.file_path, "Библиотека 'pyarrow' не установлена."
            ) from exc

        try:
            pf = pq.ParquetFile(self.file_path)
            for batch in pf.iter_batches(batch_size=self._csv_chunk_size):
                df = batch.to_pandas()
                chunk_text = self._dataframe_to_text(df)
                if chunk_text:
                    yield chunk_text
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Ошибка чтения Parquet: {exc}"
            ) from exc


    @classmethod
    def _dataframe_to_text(cls, df: object) -> str:
        """Преобразует DataFrame в текстовое представление.

        Только строковые/категориальные столбцы и столбцы из
        ``_PII_NUMERIC_COLUMN_KEYWORDS`` включаются в результат.
        Значения ``NaN`` и ``None`` пропускаются.

        Args:
            df: ``pandas.DataFrame`` для конвертации.

        Returns:
            Строки, объединённые символом новой строки.
        """
        import pandas as pd

        text_columns: list[str] = []
        for col in df.columns:
            dtype = df[col].dtype
            col_lower = str(col).lower()
            is_text_dtype = pd.api.types.is_string_dtype(dtype) or str(dtype) in (
                "object", "category", "string"
            )
            is_pii_numeric = any(kw in col_lower for kw in _PII_NUMERIC_COLUMN_KEYWORDS)
            if is_text_dtype or is_pii_numeric:
                text_columns.append(col)

        if not text_columns:
            # Если не нашли текстовых столбцов — берём все (на всякий случай)
            text_columns = df.columns.tolist()

        selected = df[text_columns].fillna("").astype(str)

        rows: list[str] = []
        for _, row in selected.iterrows():
            row_text = " ".join(v.strip() for v in row.values if v.strip())
            if row_text:
                rows.append(row_text)

        return "\n".join(rows)