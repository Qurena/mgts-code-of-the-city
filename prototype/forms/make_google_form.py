"""Генератор Google Apps Script, который за минуту создаёт обе анкеты в Google Формах и подключает отправку ответов в систему.
Названия вопросов берутся из mapping.json (поля columns.person/other, оценки, комментарии), поэтому ответы формы сопоставляются без ручной работы.

Запуск:   python forms/make_google_form.py mapping.json --receiver-url https://ваш-сервер --token ТОКЕН [--out forms/google_forms.gs]
Дальше:   открыть script.google.com -> новый проект -> вставить содержимое файла -> запустить createForms (разрешить доступ один раз).
          В журнале выполнения появятся ссылки на формы. Каждый новый ответ уходит на <receiver-url>/form/<имя источника>.
Без публичного адреса (receiver-url) используйте опрос таблицы: poll_sheet.py (см. FINALS_PLAYBOOK.md).
"""
import argparse
import json
from pathlib import Path


def js(s: object) -> str:
    return json.dumps(s, ensure_ascii=False)


def build(mapping: dict, periods: list[str], scale: tuple[int, int], receiver_url: str, token: str, people: list[tuple[str, str]] | None = None) -> str:
    """people: пары (стажёр, наставник) из базы. С ними поля имён становятся выпадающими списками, и опечаток в именах не будет."""
    out = [
        "// Создано make_google_form.py. Вставьте в script.google.com и запустите createForms().",
        f"var RECEIVER_URL = {js(receiver_url.rstrip('/'))};",
        f"var TOKEN = {js(token)};",
        "",
        "function send_(name, e) {",
        "  var values = {};",
        "  e.response.getItemResponses().forEach(function (ir) { values[ir.getItem().getTitle()] = ir.getResponse(); });",
        "  values['Отметка времени'] = e.response.getTimestamp().toISOString();",
        "  UrlFetchApp.fetch(RECEIVER_URL + '/form/' + name, {",
        "    method: 'post', contentType: 'application/json', muteHttpExceptions: true,",
        "    headers: {'x-token': TOKEN, 'x-delivery-id': e.response.getId()},",
        "    payload: JSON.stringify({values: values})",
        "  });",
        "}",
        "",
    ]
    creators = []
    for spec in mapping["sources"]:
        name, cols = spec["name"], spec.get("columns", {})
        who = "стажёра" if spec["side"] == "intern" else "наставника"
        fn = "form_" + "".join(ch if ch.isalnum() else "_" for ch in name)
        lines = [f"function onSubmit_{name}(e) {{ send_({js(name)}, e); }}", "", f"function {fn}() {{", f"  var f = FormApp.create({js('Анкета ' + who + ' (' + name + ')')});"]
        interns = [p[0] for p in people or []]
        mentors = sorted({p[1] for p in people or [] if p[1] and p[1] != "—"})
        mine, theirs = (interns, mentors) if spec["side"] == "intern" else (mentors, interns)

        def name_item(title: str, choices: list[str]) -> str:
            if choices:
                return f"  f.addListItem().setTitle({js(title)}).setChoiceValues({js(choices)}).setRequired(true);"
            return f"  f.addTextItem().setTitle({js(title)}).setRequired(true);"

        if cols.get("person"):
            lines.append(name_item(cols["person"], mine))
        if cols.get("other"):
            lines.append(name_item(cols["other"], theirs))
        p = spec.get("period") or {}
        if p.get("column") and "from_date" not in p:
            lines.append(f"  f.addListItem().setTitle({js(p['column'])}).setChoiceValues({js(periods)}).setRequired(true);")
        seen = set()
        for sc in spec.get("scores", []):
            if sc["column"] in seen:
                continue
            seen.add(sc["column"])
            a, b = sc.get("scale") or scale
            lines.append(f"  f.addScaleItem().setTitle({js(sc['column'])}).setBounds({a}, {b}).setLabels('хуже', 'лучше').setRequired(true);")
        for c in spec.get("comments", []):
            lines.append(f"  f.addParagraphTextItem().setTitle({js(c)});")
        lines += [f"  ScriptApp.newTrigger('onSubmit_{name}').forForm(f).onFormSubmit().create();",
                  f"  Logger.log({js(name)} + ': ссылка для ответов ' + f.getPublishedUrl() + ' | редактирование ' + f.getEditUrl());", "}", ""]
        out += lines
        creators.append(fn)
    out += ["function createForms() {"] + [f"  {c}();" for c in creators] + ["}", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mapping")
    ap.add_argument("--receiver-url", required=True)
    ap.add_argument("--token", default="")
    ap.add_argument("--out", default=str(Path(__file__).with_name("google_forms.gs")))
    ap.add_argument("--from-db", action="store_true", help="взять имена стажёров и наставников из базы (после import_data.py): поля имён станут списками")
    a = ap.parse_args()
    import core  # читает survey.json: месяцы и шкала по умолчанию

    mapping = json.loads(Path(a.mapping).read_text(encoding="utf-8"))
    people = None
    if a.from_db:
        p = core.participants(core.connect())
        people = list(zip(p.name, p.mentor_name))
    code = build(mapping, core.PERIODS, (core.SCALE_MIN, core.SCALE_MAX), a.receiver_url, a.token, people)
    Path(a.out).write_text(code, encoding="utf-8")
    print(f"Готово: {a.out}\nВставьте в script.google.com и запустите createForms().")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
