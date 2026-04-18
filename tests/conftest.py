from pathlib import Path
import pytest

@pytest.fixture(scope="session")
def project_root() -> Path:
    """Корень проекта"""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def fixtures_dir(project_root) -> Path:
    """Папка с тестовыми файлами"""
    path = project_root / "fixtures"
    path.mkdir(exist_ok=True)
    return path


@pytest.fixture(scope="session")
def documents_dir(fixtures_dir) -> Path:
    """Документы (PDF, DOCX, HTML)"""
    (fixtures_dir / "documents").mkdir(exist_ok=True)
    return fixtures_dir / "documents"


@pytest.fixture(scope="session")
def data_dir(fixtures_dir) -> Path:
    """Табличные данные"""
    (fixtures_dir / "data").mkdir(exist_ok=True)
    return fixtures_dir / "data"


@pytest.fixture(scope="session")
def media_dir(fixtures_dir) -> Path:
    """Медиафайлы"""
    (fixtures_dir / "media").mkdir(exist_ok=True)
    return fixtures_dir / "media"