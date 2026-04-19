# ../tests_module4-5/test_report_generator.py
"""
Тест 5-го этапа (ReportGenerator) на pytest
"""

import sys
from pathlib import Path

import pytest

current_dir = Path(__file__).resolve().parent        # папка tests_module4-5/
project_root = current_dir.parent                     # корневая папка проекта

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from report.generators import ReportGenerator


@pytest.fixture
def test_results():
    """Тестовые данные для проверки генератора отчетов."""
    return [
        {
            "path": "/ПДнDataset/employees.pdf",
            "file_format": "pdf",
            "pii_categories": {"ФИО": 12, "EMAIL": 8, "ТЕЛЕФОН": 5},
            "total_findings": 25,
            "uz_level": "УЗ-4"
        },
        {
            "path": "/ПДнDataset/passports.docx",
            "file_format": "docx",
            "pii_categories": {"ПАСПОРТ": 3, "СНИЛС": 2},
            "total_findings": 5,
            "uz_level": "УЗ-3"
        },
        {
            "path": "/ПДнDataset/payments.xlsx",
            "file_format": "xlsx",
            "pii_categories": {"НОМЕР_КАРТЫ": 45},
            "total_findings": 45,
            "uz_level": "УЗ-2"
        },
        {
            "path": "/ПДнDataset/photo.jpg",
            "file_format": "jpg",
            "pii_categories": {"БИОМЕТРИЯ": 1},
            "total_findings": 1,
            "uz_level": "УЗ-1"
        },
        {
            "path": "/ПДнDataset/empty.csv",
            "file_format": "csv",
            "pii_categories": {},
            "total_findings": 0,
            "uz_level": "УЗ-4"
        },
        {
            "path": "/ПДнDataset/health_report.pdf",
            "file_format": "pdf",
            "pii_categories": {"ЗДОРОВЬЕ": 7},
            "total_findings": 7,
            "uz_level": "УЗ-1"
        }
    ]


def test_report_generator_creates_all_formats(test_results, tmp_path):
    """Проверяем, что ReportGenerator создает CSV, JSON и Markdown файлы."""
    output_dir = tmp_path / "reports"
    
    saved = ReportGenerator.generate(
        results=test_results,
        output_dir=str(output_dir),
        report_name="test_report_module5",
        formats=["csv", "json", "md"]
    )

    # Проверяем, что метод вернул словарь с тремя файлами
    assert isinstance(saved, dict)
    assert "csv" in saved
    assert "json" in saved
    assert "md" in saved

    # Проверяем существование файлов
    csv_file = Path(saved["csv"])
    json_file = Path(saved["json"])
    md_file = Path(saved["md"])

    assert csv_file.exists(), "CSV-файл не создан"
    assert json_file.exists(), "JSON-файл не создан"
    assert md_file.exists(), "Markdown-файл не создан"

    # Проверяем содержимое CSV (заголовок и количество строк)
    with open(csv_file, encoding="utf-8") as f:
        content = f.read()
    assert "путь;категории_ПДн;количество_находок;УЗ;формат_файла" in content
    assert content.count("\n") >= 7  # заголовок + 6 тестовых строк

    # Проверяем JSON
    with open(json_file, encoding="utf-8") as f:
        import json as json_lib
        data = json_lib.load(f)
    assert "generated_at" in data
    assert data["total_files"] == 6
    assert "uz_distribution" in data
    assert len(data["results"]) == 6

    # Проверяем Markdown
    with open(md_file, encoding="utf-8") as f:
        md_content = f.read()
    assert "# Отчет по обнаружению персональных данных" in md_content
    assert "УЗ-1" in md_content
    assert "УЗ-2" in md_content
    assert "УЗ-3" in md_content
    assert "УЗ-4" in md_content


def test_report_generator_empty_results(tmp_path):
    """Проверяем работу с пустым списком результатов."""
    saved = ReportGenerator.generate(
        results=[],
        output_dir=str(tmp_path / "empty"),
        report_name="empty_test",
        formats=["csv", "json", "md"]
    )

    assert saved["csv"] is not None
    assert saved["json"] is not None
    assert saved["md"] is not None

    # CSV должен содержать только заголовок
    with open(saved["csv"], encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert "путь;категории_ПДн" in lines[0]