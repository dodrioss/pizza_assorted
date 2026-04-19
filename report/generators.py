"""
5-й этап: Формирование отчета (CSV / JSON / Markdown / HTML + result.csv для хакатона)
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter


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
        formats: list = ("csv", "json", "md", "html")
    ) -> dict:
        """
        results — список словарей от pii_detector + UZClassifier
        """
        if not report_name:
            report_name = f"pdn_report_{datetime.now():%Y%m%d_%H%M%S}"

        ReportGenerator._ensure_dir(output_dir)
        base_path = Path(output_dir) / report_name
        saved = {}

        if "csv" in formats:
            saved["csv"] = ReportGenerator._to_csv(results, f"{base_path}.csv")
        if "json" in formats:
            saved["json"] = ReportGenerator._to_json(results, f"{base_path}.json")
        if "md" in formats:
            saved["md"] = ReportGenerator._to_markdown(results, f"{base_path}.md")
        if "html" in formats:
            saved["html"] = ReportGenerator._to_html(results, f"{base_path}.html")

        result_csv_path = ReportGenerator._to_hackathon_result_csv(results, output_dir)
        if result_csv_path:
            saved["result_csv"] = str(result_csv_path)

        print(f"✅ Отчет сгенерирован: {len(results)} файлов обработано")
        print(f"📊 Форматы: {', '.join(saved.keys())}")
        if "result_csv" in saved:
            print(f"🎯 result.csv для сдачи создан: {saved['result_csv']}")
        
        return saved

    @staticmethod
    def _to_hackathon_result_csv(results: List[Dict], output_dir: str) -> Path | None:
        """Создаёт result.csv строго по требованиям хакатона."""
        hackathon_rows = []

        for r in results:
            if r.get("total_findings", 0) == 0:
                continue

            file_path = Path(r["path"])
            if not file_path.exists():
                continue

            size = file_path.stat().st_size
            mtime = file_path.stat().st_mtime
            time_str = datetime.fromtimestamp(mtime).strftime("%b %d %H:%M").lower()

            hackathon_rows.append({
                "size": size,
                "time": time_str,
                "name": file_path.name
            })

        if not hackathon_rows:
            print("⚠️  result.csv не создан — не найдено файлов с персональными данными")
            return None

        result_file = Path(output_dir) / "result.csv"

        with open(result_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["size", "time", "name"])
            writer.writeheader()
            writer.writerows(hackathon_rows)

        print(f"✅ result.csv успешно создан ({len(hackathon_rows)} файлов с ПДн)")
        return result_file

    @staticmethod
    def _to_csv(results: List[Dict], filepath: str) -> str:
        """CSV с разделителем ; и правильным экранированием."""
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerow([
                "путь", "категории_ПДн", "количество_находок", "УЗ", "формат_файла", "ошибка"
            ])
            for r in results:
                cats_str = ", ".join(
                    f"{cat}({cnt})" for cat, cnt in r["pii_categories"].items() if cnt > 0
                ) or "—"
                writer.writerow([
                    r["path"],
                    cats_str,
                    r["total_findings"],
                    r["uz_level"],
                    r.get("file_format", ""),
                    r.get("error", "")
                ])
        return filepath

    @staticmethod
    def _to_json(results: List[Dict], filepath: str) -> str:
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_files": len(results),
            "files_with_pii": sum(1 for r in results if r["total_findings"] > 0),
            "files_with_errors": sum(1 for r in results if r.get("error")),
            "uz_distribution": dict(Counter(r["uz_level"] for r in results)),
            "error_summary": dict(Counter(r.get("error", "нет") for r in results if r.get("error"))),
            "results": results
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    @staticmethod
    def _to_markdown(results: List[Dict], filepath: str) -> str:
        """Улучшенный Markdown с цветными бейджами и сводкой ошибок."""
        lines = [
            "# 🔍 Отчет по обнаружению персональных данных (152-ФЗ)",
            f"🕐 Сгенерировано: `{datetime.now():%d.%m.%Y %H:%M}`",
            f"📁 Всего файлов: **{len(results)}**",
            f"✅ Обработано успешно: **{sum(1 for r in results if not r.get('error'))}**",
            f"❌ Ошибок: **{sum(1 for r in results if r.get('error'))}**\n",
            
            "## 📊 Сводка по уровням защиты",
            "| Уровень | Файлов | Статус |",
            "|---------|--------|--------|",
        ]
        
        uz_status = {
            "УЗ-1": "🔴 Критично",
            "УЗ-2": "🟠 Высокий риск", 
            "УЗ-3": "🟡 Средний риск",
            "УЗ-4": "🟢 Нет ПДн"
        }
        
        uz_count = Counter(r["uz_level"] for r in results)
        for uz in ["УЗ-1", "УЗ-2", "УЗ-3", "УЗ-4"]:
            cnt = uz_count.get(uz, 0)
            status = uz_status.get(uz, "❓")
            lines.append(f"| {uz} | {cnt} | {status} |")

        # Сводка ошибок
        errors = [r for r in results if r.get("error")]
        if errors:
            lines.extend([
                "\n## ⚠️ Ошибки обработки",
                "| Файл | Формат | Ошибка |",
                "|------|--------|--------|",
            ])
            for r in errors[:20]:  # первые 20 ошибок
                err_short = (r["error"][:80] + "…") if len(r["error"]) > 80 else r["error"]
                lines.append(f"| `{Path(r['path']).name}` | {r.get('file_format', '?')} | `{err_short}` |")
            if len(errors) > 20:
                lines.append(f"\n_… и ещё {len(errors) - 20} ошибок (см. полный отчет)_")

        # Детальная таблица (только файлы с ПДн или ошибками)
        filtered = [r for r in results if r["total_findings"] > 0 or r.get("error")]
        if filtered:
            lines.extend([
                "\n## 📋 Детальный результат (только значимые файлы)",
                "| Путь | Формат | Категории ПДн | Находок | УЗ | Статус |",
                "|------|--------|---------------|---------|-----|--------|",
            ])
            for r in filtered:
                cats = ", ".join(f"`{k}`({v})" for k, v in r["pii_categories"].items() if v > 0) or "—"
                status = "❌ Ошибка" if r.get("error") else "✅ OK"
                lines.append(
                    f"| `{Path(r['path']).name}` | {r.get('file_format', '')} | {cats} | **{r['total_findings']}** | **{r['uz_level']}** | {status} |"
                )

        lines.extend([
            "\n---",
            "### 🛡️ Рекомендации",
            "- 🔴 **УЗ-1**: Немедленная изоляция и шифрование",
            "- 🟠 **УЗ-2**: Обязательное логирование доступа", 
            "- 🟡 **УЗ-3**: Регулярный аудит",
            "- 🟢 **УЗ-4**: Стандартные меры защиты",
            "\n> _Отчет сгенерирован автоматически. Требуется ручная проверка критичных файлов._"
        ])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    @staticmethod
    def _to_html(results: List[Dict], filepath: str) -> str:
        """Интерактивный HTML-отчет с диаграммами и фильтрацией."""
        
        # Подготовка данных для графиков
        uz_counts = dict(Counter(r["uz_level"] for r in results))
        error_counts = dict(Counter(r.get("error", "нет") for r in results if r.get("error")))
        
        # Категории ПДн
        pii_categories = Counter()
        for r in results:
            for cat, cnt in r["pii_categories"].items():
                pii_categories[cat] += cnt
        
        # Файлы с ошибками для детального просмотра
        error_files = [r for r in results if r.get("error")]
        
        html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔍 Отчет по ПДн — {datetime.now():%d.%m.%Y}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --accent: #3b82f6;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #334155;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
            margin-bottom: 2rem;
        }}
        h1 {{ font-size: 1.8rem; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--bg-secondary);
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
            border: 1px solid var(--border);
        }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: var(--accent); }}
        .stat-label {{ color: var(--text-secondary); font-size: 0.9rem; }}
        .charts {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
            margin-bottom: 2rem;
        }}
        .chart-card {{
            background: var(--bg-secondary);
            padding: 1.5rem;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        .chart-card h3 {{ margin-bottom: 1rem; color: var(--text-primary); }}
        .filters {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}
        .filters select, .filters input {{
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            padding: 0.5rem 1rem;
            border-radius: 6px;
            min-width: 200px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-secondary);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{ background: rgba(59, 130, 246, 0.1); font-weight: 600; }}
        tr:hover {{ background: rgba(255,255,255,0.05); }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .badge-uz1 {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); }}
        .badge-uz2 {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); }}
        .badge-uz3 {{ background: rgba(59, 130, 246, 0.2); color: var(--accent); }}
        .badge-uz4 {{ background: rgba(34, 197, 94, 0.2); color: var(--success); }}
        .badge-error {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); }}
        .badge-ok {{ background: rgba(34, 197, 94, 0.2); color: var(--success); }}
        .error-details {{
            background: rgba(239, 68, 68, 0.1);
            border-left: 3px solid var(--danger);
            padding: 0.5rem 1rem;
            margin: 0.5rem 0;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }}
        .search-box {{
            margin-bottom: 1rem;
        }}
        .search-box input {{
            width: 100%;
            max-width: 400px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            padding: 0.5rem 1rem;
            border-radius: 6px;
        }}
        .hidden {{ display: none; }}
        footer {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 0.9rem;
            text-align: center;
        }}
        @media (max-width: 768px) {{
            .charts {{ grid-template-columns: 1fr; }}
            header {{ flex-direction: column; gap: 1rem; text-align: center; }}
            .filters {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 Отчет по обнаружению ПДн</h1>
            <div style="color: var(--text-secondary)">
                {datetime.now():%d.%m.%Y %H:%M} • {len(results)} файлов
            </div>
        </header>

        <!-- Статистика -->
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{sum(1 for r in results if r["total_findings"] > 0)}</div>
                <div class="stat-label">Файлов с ПДн</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{uz_counts.get("УЗ-1", 0)}</div>
                <div class="stat-label" style="color: var(--danger)">УЗ-1 (критично)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(error_files)}</div>
                <div class="stat-label" style="color: var(--warning)">Ошибок</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{sum(1 for r in results if not r.get("error"))}</div>
                <div class="stat-label" style="color: var(--success)">Успешно</div>
            </div>
        </div>

        <!-- Диаграммы -->
        <div class="charts">
            <div class="chart-card">
                <h3>📊 Распределение по УЗ</h3>
                <canvas id="uzChart"></canvas>
            </div>
            <div class="chart-card">
                <h3>🏷️ Категории ПДн</h3>
                <canvas id="piiChart"></canvas>
            </div>
        </div>

        <!-- Ошибки (если есть) -->
        {f'''
        <div class="chart-card" style="margin-bottom: 2rem;">
            <h3>⚠️ Ошибки обработки ({len(error_files)})</h3>
            <div class="filters">
                <select id="errorFilter" onchange="filterErrors()">
                    <option value="all">Все ошибки</option>
                    {"".join(f'<option value="{err}">{err[:50]}…</option>' for err in set(e.get("error", "") for e in error_files))}
                </select>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Файл</th>
                        <th>Формат</th>
                        <th>Ошибка</th>
                    </tr>
                </thead>
                <tbody id="errorTable">
                    {"".join(f'''
                    <tr class="error-row" data-error="{r.get('error', '')}">
                        <td><code>{Path(r["path"]).name}</code></td>
                        <td>{r.get("file_format", "?")}</td>
                        <td>
                            <div class="error-details">{r.get("error", "")[:100]}{"…" if len(r.get("error", "")) > 100 else ""}</div>
                        </td>
                    </tr>
                    ''' for r in error_files)}
                </tbody>
            </table>
        </div>
        ''' if error_files else ''}

        <!-- Детальная таблица -->
        <div class="chart-card">
            <h3>📋 Все результаты</h3>
            <div class="filters">
                <select id="uzFilter" onchange="filterTable()">
                    <option value="all">Все УЗ</option>
                    <option value="УЗ-1">УЗ-1</option>
                    <option value="УЗ-2">УЗ-2</option>
                    <option value="УЗ-3">УЗ-3</option>
                    <option value="УЗ-4">УЗ-4</option>
                </select>
                <select id="formatFilter" onchange="filterTable()">
                    <option value="all">Все форматы</option>
                    {"".join(f'<option value="{fmt}">{fmt}</option>' for fmt in sorted(set(r.get("file_format", "") for r in results if r.get("file_format"))))}
                </select>
                <select id="piiFilter" onchange="filterTable()">
                    <option value="all">Все</option>
                    <option value="with_pii">Только с ПДн</option>
                    <option value="no_pii">Без ПДн</option>
                    <option value="errors">Только ошибки</option>
                </select>
            </div>
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 Поиск по имени файла…" oninput="filterTable()">
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Файл</th>
                        <th>Формат</th>
                        <th>Категории ПДн</th>
                        <th>Находок</th>
                        <th>УЗ</th>
                        <th>Статус</th>
                    </tr>
                </thead>
                <tbody id="resultsTable">
                    {"".join(f'''
                    <tr class="result-row" 
                        data-uz="{r["uz_level"]}" 
                        data-format="{r.get("file_format", "")}" 
                        data-pii="{r["total_findings"] > 0}" 
                        data-error="{bool(r.get("error"))}"
                        data-name="{Path(r["path"]).name.lower()}">
                        <td><code title="{r["path"]}">{Path(r["path"]).name}</code></td>
                        <td>{r.get("file_format", "—")}</td>
                        <td>{", ".join(f'<span class="badge" style="background:rgba(59,130,246,0.2)">{k}</span>' for k in r["pii_categories"].keys()) or "—"}</td>
                        <td><strong>{r["total_findings"]}</strong></td>
                        <td><span class="badge badge-{r["uz_level"].lower().replace("-", "")}">{r["uz_level"]}</span></td>
                        <td>{'<span class="badge badge-error">❌ Ошибка</span>' if r.get("error") else '<span class="badge badge-ok">✅ OK</span>'}</td>
                    </tr>
                    ''' for r in results)}
                </tbody>
            </table>
            <div id="noResults" class="hidden" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                Нет результатов по выбранным фильтрам
            </div>
        </div>

        <footer>
            <p>🛡️ Рекомендации: УЗ-1 — немедленная обработка | УЗ-2 — обязательная защита | УЗ-3 — аудит | УЗ-4 — стандартные меры</p>
            <p style="margin-top: 0.5rem; opacity: 0.7;">Отчет сгенерирован автоматически • Требуется ручная проверка критичных файлов</p>
        </footer>
    </div>

    <script>
        // Диаграмма УЗ
        new Chart(document.getElementById('uzChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(list(uz_counts.keys()))},
                datasets: [{{
                    data: {json.dumps(list(uz_counts.values()))},
                    backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#22c55e'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'bottom', labels: {{ color: '#94a3b8' }} }},
                    tooltip: {{ callbacks: {{ label: ctx => `${{ctx.label}}: ${{ctx.parsed}} файлов` }} }}
                }},
                cutout: '60%'
            }}
        }});

        // Диаграмма ПДн
        new Chart(document.getElementById('piiChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(list(pii_categories.keys())[:10])},
                datasets: [{{
                    label: 'Количество находок',
                    data: {json.dumps(list(pii_categories.values())[:10])},
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{ callbacks: {{ label: ctx => `${{ctx.parsed.y}} находок` }} }}
                }},
                scales: {{
                    y: {{ 
                        beginAtZero: true, 
                        grid: {{ color: '#334155' }},
                        ticks: {{ color: '#94a3b8' }}
                    }},
                    x: {{ 
                        grid: {{ display: false }},
                        ticks: {{ color: '#94a3b8', maxRotation: 45, minRotation: 45 }}
                    }}
                }}
            }}
        }});

        // Фильтрация таблицы
        function filterTable() {{
            const uz = document.getElementById('uzFilter').value;
            const format = document.getElementById('formatFilter').value;
            const pii = document.getElementById('piiFilter').value;
            const search = document.getElementById('searchInput').value.toLowerCase();
            
            const rows = document.querySelectorAll('#resultsTable .result-row');
            let visible = 0;
            
            rows.forEach(row => {{
                const rowUz = row.dataset.uz;
                const rowFormat = row.dataset.format;
                const rowPii = row.dataset.pii === 'true';
                const rowError = row.dataset.error === 'true';
                const rowName = row.dataset.name;
                
                const matchUz = uz === 'all' || rowUz === uz;
                const matchFormat = format === 'all' || rowFormat === format;
                const matchPii = pii === 'all' || 
                                (pii === 'with_pii' && rowPii) ||
                                (pii === 'no_pii' && !rowPii && !rowError) ||
                                (pii === 'errors' && rowError);
                const matchSearch = !search || rowName.includes(search);
                
                if (matchUz && matchFormat && matchPii && matchSearch) {{
                    row.classList.remove('hidden');
                    visible++;
                }} else {{
                    row.classList.add('hidden');
                }}
            }});
            
            document.getElementById('noResults').classList.toggle('hidden', visible > 0);
        }}

        // Фильтрация ошибок
        function filterErrors() {{
            const filter = document.getElementById('errorFilter').value;
            const rows = document.querySelectorAll('.error-row');
            
            rows.forEach(row => {{
                if (filter === 'all' || row.dataset.error === filter) {{
                    row.classList.remove('hidden');
                }} else {{
                    row.classList.add('hidden');
                }}
            }});
        }}

        // Инициализация
        document.addEventListener('DOMContentLoaded', () => {{
            filterTable();
            if (document.getElementById('errorFilter')) filterErrors();
        }});
    </script>
</body>
</html>'''
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return filepath