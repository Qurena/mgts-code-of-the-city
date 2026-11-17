"""Демонстрационные данные. Всё выдумано: имена, оценки и комментарии не относятся к МГТС.
Данные проходят через тот же приём ответов (ingest), что и новые ответы из формы.
Запуск: python seed.py [--reset]
"""
import sys

import core

N = None
PEOPLE = [(1, "Алексей К.", "И. Орлов"), (2, "Мария С.", "Е. Фомина"), (3, "Артём Л.", "Д. Громов"), (4, "Ирина Д.", "Т. Белова"), (5, "Павел Н.", "С. Ким")]
# оценки по 6 месяцам: (стажёр, наставник) для каждого вопроса
SCORES = {
    1: {"goals": ([7, 7, 8, 8, 8, 8], [7, 8, 8, 8, 8, 8]), "feedback": ([7, 8, 8, 8, 7, 8], [8] * 6), "resources": ([8, 8, 8, 7, 8, 8], [8] * 6), "growth": ([7, 7, 8, 8, 8, 9], [7, 8, 8, 8, 9, 9])},
    2: {"goals": ([8, 8, 7, 7, 7, 7], [8] * 6), "feedback": ([8, 7, 7, 7, 7, 6], [8] * 6), "resources": ([8, 8, 7, 5, 4, 4], [8] * 6), "growth": ([7, 7, 7, 7, 6, 6], [8] * 6)},
    3: {"goals": ([7] * 6, [7] * 6), "feedback": ([7] * 6, [7] * 6), "resources": ([8] * 6, [8] * 6), "growth": ([8, 8, 7, 5, 4, 4], [8] * 6)},
    4: {"goals": ([7] * 6, [7] * 6), "feedback": ([8, 7, 6, 6, 6, 6], [8] * 6), "resources": ([8] * 6, [8] * 6), "growth": ([7] * 6, [7] * 6)},
    5: {"goals": ([6, 7, 7, 7, 7, N], [7] * 6), "feedback": ([7, 7, 7, 7, 7, N], [7] * 6), "resources": ([7, 7, 7, 7, 7, N], [7] * 6), "growth": ([6, 6, 7, 7, 7, N], [7] * 6)},
}
COMMENTS = {  # (стажёр, месяц, сторона) -> текст
    (2, 4, "intern"): "Не понимаю, к кому обратиться за доступом в систему заявок, уже вторую неделю жду доступ.",
    (2, 6, "intern"): "Доступа до сих пор нет, задачи делаю в тестовой среде.",
    (2, 6, "mentor"): "Мария быстро включилась, вопросов по работе нет.",
    (3, 6, "intern"): "Задания однотипные, нового мало.",
    (3, 6, "mentor"): "Справляется отлично, готов к более сложным задачам.",
    (4, 5, "intern"): "За месяц так и не получилось обсудить работу с наставником.",
    (1, 6, "intern"): "Всё устраивает, нравится команда.",
}


def seed(con) -> int:
    n = 0
    for iid, name, mentor in PEOPLE:
        con.execute("INSERT OR IGNORE INTO participants VALUES(?,?,?)", (iid, name, mentor))
    con.commit()
    for iid, dims in SCORES.items():
        for side_i, side in enumerate(core.SIDES):
            for p in range(1, core.N_PERIODS + 1):
                scores = {d: v[side_i][p - 1] for d, v in dims.items()}
                comment = COMMENTS.get((iid, p, side))
                if all(v is None for v in scores.values()) and not comment:
                    continue  # ответа нет: пропуск остаётся пропуском
                r = core.ingest({"response_id": f"seed-{side}-{iid}-{p}", "source": side, "intern_id": iid, "period": p, "scores": scores, "comment": comment}, con=con)
                n += r["status"] == "new"
    return n


if __name__ == "__main__":
    if "--reset" in sys.argv and core.DB_PATH.exists():
        for ext in ("", "-wal", "-shm"):
            core.DB_PATH.with_name(core.DB_PATH.name + ext).unlink(missing_ok=True)
    con = core.connect()
    print("добавлено ответов:", seed(con), "· разобрано комментариев:", core.analyze_pending(con))
