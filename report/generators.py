# report/generators.py
"""
5-й этап: Формирование отчета (CSV / JSON / Markdown)
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class ReportGenerator:
    """Генератор отчетов по результатам сканирования."""

    @staticmethod
    def _ensure_dir(path: str) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate(
        results: List[Dict[str, Any]],
        output_dir: str = "output/reports",
        report_name: str = None,
        formats: list = ("csv", "json", "md")
    ) -> dict:
        """
        results — список словарей от pii_detector + UZClassifier
        """
        if not report_name:
            report_name = f"pdn_report_{datetime.now():%Y%m%d_%H%M%S}"

        ReportGenerator._ensure_dir(output_dir)
        base_path = os.path.join(output_dir, report_name)

        saved = {}

        if "csv" in formats:
            saved["csv"] = ReportGenerator._to_csv(results, f"{base_path}.csv")
        if "json" in formats:
            saved["json"] = ReportGenerator._to_json(results, f"{base_path}.json")
        if "md" in formats:
            saved["md"] = ReportGenerator._to_markdown(results, f"{base_path}.md")

        print(f"Отчет сгенерирован: {len(results)} файлов обработано")
        return saved

    @staticmethod
    def _to_csv(results: List[Dict], filepath: str) -> str:
        """Исправленная версия CSV: delimiter=';' + правильное экранирование полей"""
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

            # Заголовок
            writer.writerow([
                "путь",
                "категории_ПДн",
                "количество_находок",
                "УЗ",
                "формат_файла"
            ])

            for r in results:
                # Категории через запятую (внутри поля — Excel/RU корректно обработает)
                cats_str = ", ".join(
                    f"{cat}({cnt})" for cat, cnt in r["pii_categories"].items() if cnt > 0
                ) or "—"

                writer.writerow([
                    r["path"],
                    cats_str,
                    r["total_findings"],
                    r["uz_level"],
                    r.get("file_format", "")
                ])
        return filepath

    @staticmethod
    def _to_json(results: List[Dict], filepath: str) -> str:
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_files": len(results),
            "files_with_pii": sum(1 for r in results if r["total_findings"] > 0),
            "uz_distribution": {},
            "results": results
        }

        for r in results:
            uz = r["uz_level"]
            data["uz_distribution"][uz] = data["uz_distribution"].get(uz, 0) + 1

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    @staticmethod
    def _to_markdown(results: List[Dict], filepath: str) -> str:
        lines = [
            "# Отчет по обнаружению персональных данных",
            f"Сгенерировано: {datetime.now():%d.%m.%Y %H:%M}",
            f"Всего файлов: {len(results)}\n",
            "## Сводка",
            "| УЗ | Количество файлов |",
            "|----|-------------------|",
        ]

        uz_count = {}
        for r in results:
            uz_count[r["uz_level"]] = uz_count.get(r["uz_level"], 0) + 1

        for uz, cnt in sorted(uz_count.items()):
            lines.append(f"| {uz} | {cnt} |")

        lines.extend([
            "\n## Детальный результат\n",
            "| Путь | Формат | Категории ПДн | Кол-во находок | УЗ |",
            "|------|--------|---------------|----------------|----|",
        ])

        for r in results:
            cats = ", ".join(f"{k}({v})" for k, v in r["pii_categories"].items() if v > 0) or "—"
            lines.append(
                f"| `{r['path']}` | {r.get('file_format', '')} | {cats} | **{r['total_findings']}** | **{r['uz_level']}** |"
            )

        lines.append("\nРекомендации:")
        lines.append("• Файлы УЗ-1 — немедленная обработка")
        lines.append("• Файлы УЗ-2 — обязательная защита")
        lines.append("• Остальные — согласно политике компании")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath