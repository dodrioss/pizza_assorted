"""
Настройка логирования + удобный прогресс-бар с tqdm.
"""

import logging
import sys
from pathlib import Path
from tqdm import tqdm

def setup_logging(log_file: str = "pdn_scanner.log", level: int = logging.INFO):
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ],
        force=True  
    )

def get_progress_bar(iterable, desc: str = "Обработка", unit: str = "файл", **kwargs):
    """Возвращает tqdm-прогресс-бар с удобными настройками по умолчанию."""
    return tqdm(
        iterable,
        desc=desc,
        unit=unit,
        dynamic_ncols=True,
        smoothing=0.1,
        **kwargs
    )