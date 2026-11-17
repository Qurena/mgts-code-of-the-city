"""Пакетная загрузка данных по mapping.json.
Запуск:  python import_data.py mapping.json [--dry-run] [--reset] [--no-analyze]
  --dry-run    только прочитать и показать отчёт, базу не трогать
  --reset      сначала удалить базу (удобно при исправлении сопоставления)
По умолчанию после загрузки разбираются комментарии (ANALYZER=keywords или llm, см. README).
"""
import argparse

import core
import ingest_tools as it


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mapping")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--watch", type=float, metavar="СЕК", help="повторять загрузку каждые СЕК секунд: новые строки в файле или таблице подхватываются сами (повторы отсекаются)")
    a = ap.parse_args()
    mapping, base = it.load_mapping(a.mapping)
    if a.reset and not a.dry_run:
        for ext in ("", "-wal", "-shm"):
            core.DB_PATH.with_name(core.DB_PATH.name + ext).unlink(missing_ok=True)
    con = core.connect()
    rep = it.import_mapping(con, mapping, base, dry_run=a.dry_run)
    it.print_report(rep)
    if not a.dry_run and not a.no_analyze:
        print("Разобрано комментариев:", core.analyze_pending(con))
    if a.dry_run:
        print("(пробный запуск: в базу ничего не записано)")
    while a.watch and not a.dry_run:
        import time

        time.sleep(a.watch)
        try:
            mapping, base = it.load_mapping(a.mapping)  # mapping.json можно править на ходу
            rep = it.import_mapping(con, mapping, base)
            if rep["status"]["new"]:
                print(f"новых ответов: {rep['status']['new']}; разобрано комментариев: {core.analyze_pending(con)}")
        except Exception as e:  # файл может быть занят или недописан: следующая попытка через интервал
            print("ошибка чтения:", e)


if __name__ == "__main__":
    main()
