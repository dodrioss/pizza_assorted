"""
Точка входа (CLI) — параллельная обработка файлов + цветной вывод
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from utils.logging_utils import setup_logging
from utils.text_utils import clean_text, quick_skip_text
from utils.performance import log_memory_usage
from utils.parallel import process_files_parallel, get_worker_info, optimal_workers

from scanner import FileScanner
from extractors import get_extractor
from detectors import PIIDetector
from classifiers import UZClassifier
from report import ReportGenerator

import logging
from rich.console import Console
from rich.text import Text
from rich.style import Style
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TaskProgressColumn, TimeRemainingColumn, MofNCompleteColumn,
)

console = Console()
logger = logging.getLogger(__name__)

_detector: PIIDetector | None = None
_classifier: UZClassifier | None = None

_LOGO_WIDE = [
    ("  ██████╗ ██╗███████╗███████╗ █████╗      █████╗ ███████╗███████╗ ██████╗ ██████╗ ████████╗███████╗██████╗ ", "bold bright_blue"),
    ("  ██╔══██╗██║╚══███╔╝╚══███╔╝██╔══██╗    ██╔══██╗██╔════╝██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝██╔══██╗", "bold blue"),
    ("  ██████╔╝██║  ███╔╝   ███╔╝ ███████║    ███████║███████╗███████╗██║   ██║██████╔╝   ██║   █████╗  ██║  ██║", "bold bright_cyan"),
    ("  ██╔═══╝ ██║ ███╔╝   ███╔╝  ██╔══██║    ██╔══██║╚════██║╚════██║██║   ██║██╔══██╗   ██║   ██╔══╝  ██║  ██║", "bold cyan"),
    ("  ██║     ██║███████╗███████╗██║  ██║    ██║  ██║███████║███████║╚██████╔╝██║  ██║   ██║   ███████╗██████║", "bold bright_white"),
    ("  ╚═╝     ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═════╝ ", "bold dim"),
]

_LOGO_COMPACT = [
    [
        ("  ██████╗ ██╗███████╗███████╗ █████╗ ", "bold bright_blue"),
        ("  ██╔══██╗██║╚══███╔╝╚══███╔╝██╔══██╗", "bold blue"),
        ("  ██████╔╝██║  ███╔╝   ███╔╝ ███████║", "bold bright_cyan"),
        ("  ██╔═══╝ ██║ ███╔╝   ███╔╝  ██╔══██║", "bold cyan"),
        ("  ██║     ██║███████╗███████╗██║  ██║", "bold bright_white"),
        ("  ╚═╝     ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝", "bold dim"),
    ],
    [
        ("   █████╗ ███████╗███████╗ ██████╗ ██████╗ ████████╗███████╗██████╗ ", "bold bright_blue"),
        ("  ██╔══██╗██╔════╝██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝██╔══██╗", "bold blue"),
        ("  ███████║███████╗███████╗██║   ██║██████╔╝   ██║   █████╗  ██║  ██║", "bold bright_cyan"),
        ("  ██╔══██║╚════██║╚════██║██║   ██║██╔══██╗   ██║   ██╔══╝  ██║  ██║", "bold cyan"),
        ("  ██║  ██║███████║███████║╚██████╔╝██║  ██║   ██║   ███████╗██████╗", "bold bright_white"),
        ("  ╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═════╝ ", "bold dim"),
    ],
]


def print_logo() -> None:
    console.print()
    if console.width >= 110:
        for line, color in _LOGO_WIDE:
            console.print(Text(line, style=Style.parse(color)))
    else:
        for block in _LOGO_COMPACT:
            for line, color in block:
                console.print(Text(line, style=Style.parse(color)))
            console.print()
    console.print(Text("  152-ФЗ · PII Scanner · v1.0", style="dim"))
    console.print()


# ── CI/CD ─────────────────────────────────────────────────────────────────────
# Exit code отражает максимальный найденный уровень УЗ:
#   0 → чисто (только УЗ-4)
#   1 → найдены ПДн уровня УЗ-3
#   2 → найдены ПДн уровня УЗ-2
#   3 → найдены ПДн уровня УЗ-1  ← по умолчанию блокирует pipeline
CI_EXIT_CODES = {"УЗ-1": 3, "УЗ-2": 2, "УЗ-3": 1, "УЗ-4": 0}


def get_ci_exit_code(results: list[dict]) -> int:
    worst = 0
    for r in results:
        code = CI_EXIT_CODES.get(r.get("uz_level", "УЗ-4"), 0)
        if code > worst:
            worst = code
    return worst


def parse_args():
    parser = argparse.ArgumentParser(
        description="Автоматическое обнаружение персональных данных (152-ФЗ)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dir", default=".", help="Путь к папке для сканирования")
    parser.add_argument("--formats", nargs="+", choices=["csv", "json", "md"], default=["csv"])
    parser.add_argument("--output-dir", default="output/reports")
    parser.add_argument("--log", default="pdn_scanner.log")

    parser.add_argument("--max-ocr-attempts", type=int, default=5)
    parser.add_argument("--paddle-fallback", action="store_true")
    parser.add_argument("--aggressive-ocr", action="store_true")
    parser.add_argument("--no-skip", action="store_true")

    parser.add_argument(
        "--workers", type=int, default=None,
        help="Число потоков (по умолчанию: авто, cpu*4 для I/O). "
             "Можно задать через PDN_WORKERS."
    )
    parser.add_argument(
        "--ci", action="store_true",
        help=(
            "CI/CD режим: exit code отражает уровень найденных ПДн. "
            "0=чисто, 1=УЗ-3, 2=УЗ-2, 3=УЗ-1. "
            "Пример: python main.py --ci --fail-on УЗ-2"
        )
    )
    parser.add_argument(
        "--fail-on",
        choices=["УЗ-1", "УЗ-2", "УЗ-3"],
        default="УЗ-1",
        help="Минимальный уровень УЗ, при котором pipeline упадёт (только с --ci)."
    )

    return parser.parse_args()


def build_process_fn(args):
    """
    Замыкание: возвращает потокобезопасную функцию обработки одного файла.
    Все объекты внутри — read-only (детектор, классификатор, args).
    """
    detector = _detector
    classifier = _classifier

    def process_file(path_str: str) -> dict | None:
        path = Path(path_str)
        try:
            extractor = get_extractor(
                str(path),
                extra_kwargs={
                    "max_ocr_attempts": args.max_ocr_attempts,
                    "paddle_fallback": args.paddle_fallback,
                }
            )
            if extractor is None:
                return None

            extraction = extractor.extract()
            text = clean_text(getattr(extraction, "text", ""))

            if not args.no_skip and quick_skip_text(text, min_chars=30):
                return None

            detection = detector.detect_all_pii(text, str(path))

            if hasattr(detection, "findings") and detection.findings:
                findings_counter = Counter(
                    f.pattern_name for f in detection.findings if hasattr(f, "pattern_name")
                )
                pii_categories = dict(findings_counter)
                pii_count = len(detection.findings)
            else:
                pii_categories = {}
                pii_count = 0

            uz_level = classifier.classify(pii_categories) if pii_count > 0 else "УЗ-4"

            return {
                "path": str(path),
                "file_format": path.suffix[1:].lower(),
                "pii_categories": pii_categories,
                "total_findings": pii_count,
                "uz_level": uz_level,
            }

        except Exception as e:
            err_str = str(e).lower()
            err_full = str(e)

            if any(kw in err_str for kw in [
                "не удалось открыть изображение",
                "unidentifiedimageerror",
                "cannot identify image file"
            ]):
                console.print(f"  [yellow]⚠  Повреждённое изображение[/yellow]  {path.name}")
                return {
                    "path": str(path), "file_format": path.suffix[1:].lower(),
                    "pii_categories": {}, "total_findings": 0, "uz_level": "УЗ-4",
                    "ocr_failed": True, "error": "Повреждённое изображение",
                }

            elif any(kw in err_str for kw in [
                "ocr не смог", "ocr failed", "tesseract вернул пустой",
                "easyocr", "paddleocr"
            ]):
                console.print(f"  [bold red]✗  OCR fail[/bold red]  {path.name}")
                return {
                    "path": str(path), "file_format": path.suffix[1:].lower(),
                    "pii_categories": {}, "total_findings": 0, "uz_level": "УЗ-4",
                    "ocr_failed": True, "error": "OCR не смог извлечь текст",
                }

            else:
                console.print(f"  [bold red]✗  Критическая ошибка[/bold red]  {path.name}")
                logger.error(f"Ошибка обработки файла {path}", exc_info=True)
                return {
                    "path": str(path), "file_format": path.suffix[1:].lower(),
                    "pii_categories": {}, "total_findings": 0, "uz_level": "УЗ-4",
                    "error": f"Критическая ошибка: {err_full[:200]}",
                }

    return process_file


def _make_progress() -> Progress:
    """
    Прогресс-бар:
      ⣾ dots2-спиннер  |  цветная полоса  |  N/M  |  %  |  ETA
    """
    return Progress(
        SpinnerColumn(spinner_name="dots2", style="bold bright_cyan"),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(
            bar_width=36,
            style="bright_black",
            complete_style="bold bright_green",
            finished_style="bold green",
            pulse_style="bold cyan",
        ),
        MofNCompleteColumn(),
        TaskProgressColumn(style="dim"),
        TimeRemainingColumn(compact=True),
        console=console,
        transient=False,
    )


def main():
    global _detector, _classifier

    start_time = time.perf_counter()
    args = parse_args()

    setup_logging(log_file=args.log, level=20)
    print_logo()

    target_dir = Path(args.dir).resolve()

    console.print("[bold cyan]ЗАПУСК СКАНИРОВАНИЯ[/bold cyan]")
    console.rule(style="bright_black")
    console.print(f"  Директория  [blue]{target_dir}[/blue]")

    if args.ci:
        console.print(
            f"  [bold yellow]CI/CD режим[/bold yellow]  "
            f"pipeline упадёт при [bold]{args.fail_on}[/bold] и выше"
        )

    if args.aggressive_ocr:
        args.paddle_fallback = True
        if args.max_ocr_attempts < 6:
            args.max_ocr_attempts = 6
        console.print("  ⚡ [bold yellow]Агрессивный OCR[/bold yellow]")

    n_workers = args.workers if args.workers is not None else optimal_workers("io")
    worker_info = get_worker_info()
    console.print(
        f"  Потоки      [bold green]{n_workers}[/bold green]"
        f"  [dim]cpu={worker_info['cpu_count']}  авто-io={worker_info['io_workers']}[/dim]"
    )
    if worker_info["env_override"]:
        console.print(f"  [dim]↳ PDN_WORKERS={worker_info['env_override']}[/dim]")

    try:
        file_paths = FileScanner(root_dir=str(target_dir)).scan()
    except Exception as e:
        console.print(f"[bold red]Ошибка сканирования: {e}[/bold red]")
        sys.exit(1)

    console.print(f"  Файлов      [bold]{len(file_paths)}[/bold]")
    console.rule(style="bright_black")
    console.print()

    _detector = PIIDetector()
    _classifier = UZClassifier()

    process_fn = build_process_fn(args)

    with _make_progress() as progress:
        task = progress.add_task(
            f"Обработка  [{n_workers} потоков]",
            total=len(file_paths),
        )
        results, errors_count = process_files_parallel(
            file_paths,
            process_fn,
            workers=n_workers,
            progress=progress,
            task_id=task,
            console=console,
        )

    ocr_failed_count = sum(1 for r in results if r.get("ocr_failed"))

    log_memory_usage(message="Перед генерацией отчётов")

    saved = {}
    try:
        saved = ReportGenerator.generate(
            results=results,
            output_dir=args.output_dir,
            formats=args.formats
        )
    except Exception as e:
        console.print(f"[bold red]Ошибка генерации отчётов: {e}[/bold red]")

    log_memory_usage(message="Финальное потребление памяти")

    elapsed = time.perf_counter() - start_time

    console.print()
    console.print("[bold cyan]ГОТОВО[/bold cyan]")
    console.rule(style="bright_black")
    console.print(f"  Обработано    [bold green]{len(results)}[/bold green] файлов")
    if errors_count:
        console.print(f"  Ошибок        [bold red]{errors_count}[/bold red]")
    if ocr_failed_count:
        console.print(f"  OCR провалов  [bold red]{ocr_failed_count}[/bold red]")
    console.print(f"  Потоков       [bold]{n_workers}[/bold]")
    console.print(f"  Время         [bold]{elapsed:.1f} сек[/bold]")
    console.rule(style="bright_black")
    for fmt, path in saved.items():
        console.print(f"  [dim]↳[/dim] {fmt.upper():4}  [blue]{Path(path).name}[/blue]")

    if args.ci:
        exit_code = get_ci_exit_code(results)
        fail_threshold = CI_EXIT_CODES.get(args.fail_on, 3)

        uz_summary = Counter(r.get("uz_level", "УЗ-4") for r in results)
        console.print()
        console.print("[bold cyan]CI/CD ИТОГ[/bold cyan]")
        console.rule(style="bright_black")
        level_styles = {
            "УЗ-1": "bold bright_red",
            "УЗ-2": "bold red",
            "УЗ-3": "bold yellow",
            "УЗ-4": "bold green",
        }
        for level in ["УЗ-1", "УЗ-2", "УЗ-3", "УЗ-4"]:
            count = uz_summary.get(level, 0)
            if count:
                s = level_styles[level]
                console.print(f"  [{s}]{level}[/{s}]  {count} файл(ов)")
        console.rule(style="bright_black")

        if exit_code >= fail_threshold:
            console.print(
                f"\n  [bold bright_red]✗  PIPELINE FAILED[/bold bright_red]"
                f"  найден уровень {args.fail_on} или выше  [dim]exit {exit_code}[/dim]"
            )
            sys.exit(exit_code)
        else:
            console.print(
                f"\n  [bold bright_green]✓  PIPELINE PASSED[/bold bright_green]"
                f"  ПДн выше {args.fail_on} не найдено  [dim]exit 0[/dim]"
            )
            sys.exit(0)


if __name__ == "__main__":
    main()