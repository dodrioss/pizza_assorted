import subprocess
import logging

logger = logging.getLogger(__name__)

def extract_legacy_doc(file_path: str) -> str:
    """
    Извлекает текст из старого .doc файла через antiword.
    
    Returns:
        Текст документа или пустую строку при ошибке.
    """
    try:
        result = subprocess.run( #тут установка antiword
            ["antiword", "-i", "1", "-s", "1", file_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        logger.warning("antiword не установлен — установите: sudo apt install antiword")
        return ""
    except subprocess.TimeoutExpired:
        logger.warning("antiword таймаут для %s", file_path)
        return ""
    except subprocess.CalledProcessError as e:
        logger.warning("antiword ошибка для %s: %s", file_path, e.stderr)
        return ""
    except Exception as e:
        logger.warning("Неожиданная ошибка legacy-экстрактора: %s", e)
        return ""