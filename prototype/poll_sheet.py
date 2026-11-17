"""Опрос Google Таблицы с ответами формы: каждые N секунд читает таблицу и добавляет новые строки в систему.
Не требует публичного адреса: таблица должна быть открыта «всем, у кого есть ссылка» (просмотр).
Запуск:  python poll_sheet.py mapping.json --source intern [--every 5]
В mapping.json у источника задаются url таблицы и сопоставление колонок так же, как для файла. Повторные строки отсекаются по хэшу строки.
"""
import argparse
import time

import core
import ingest_tools as it


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mapping")
    ap.add_argument("--source", required=True, help="имя источника из mapping.json")
    ap.add_argument("--every", type=float, default=5)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    mapping, base = it.load_mapping(a.mapping)
    spec = next(s for s in mapping["sources"] if s["name"] == a.source)
    con = core.connect()
    print(f"Опрос источника {a.source} каждые {a.every} с. Остановка: Ctrl+C")
    while True:
        try:
            df = it.read_source(spec, base)
            new = 0
            for _, r in df.iterrows():
                row = {k: v for k, v in r.to_dict().items()}
                res = it.ingest_row(con, spec, row, mapping)
                new += res["status"] == "new"
                if res["status"] == "rejected":
                    print("  отклонено:", res.get("reason"))
            if new:
                print(f"  новых ответов: {new}; разобрано комментариев: {core.analyze_pending(con)}")
        except Exception as e:  # сеть или временная недоступность таблицы не должны останавливать показ
            print("  ошибка чтения таблицы:", e)
        if a.once:
            break
        time.sleep(a.every)


if __name__ == "__main__":
    main()
