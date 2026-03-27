import os
import re
import uuid
from datetime import datetime

_UI_TAG_PREFIX = "# ui:"  # внутренний маркер для удаления шагов; в файл не пишем


def is_record_enabled(context) -> bool:
    """
    Включение записи шагов.
    Запуск: behave -D RECORD=1
    """
    val = str(context.config.userdata.get("RECORD", "")).strip().lower()
    return val in ("1", "true", "yes", "y", "on")


def record_out_dir(context) -> str:
    """
    Директория для записанных feature.
    Можно переопределить: -D RECORD_OUT=/abs/path или относительный путь от корня autotests.
    """
    out = context.config.userdata.get("RECORD_OUT")
    if out:
        return str(out)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # autotests/
    return os.path.join(project_root, "recorded_features")


def init_recording_for_scenario(context, scenario, feature_relpath: str | None = None) -> None:
    """
    Инициализирует структуры записи на сценарий.
    """
    enabled = is_record_enabled(context)
    context.__dict__["_record_steps_enabled"] = enabled

    # Для UI-панели: шаги сценария нужны всегда (не только при RECORD=1)
    try:
        steps = []
        for idx, s in enumerate(getattr(scenario, "steps", []) or []):
            kw = (getattr(s, "keyword", "") or "").strip() or "When"
            nm = (getattr(s, "name", "") or "").strip()
            ln = getattr(s, "line", None)
            steps.append({"idx": idx, "keyword": kw, "name": nm, "line": ln})
        context.__dict__["_scenario_steps_index"] = steps
        line_map = {}
        for it in steps:
            if it.get("line") is not None:
                line_map[int(it["line"])] = int(it["idx"])
        context.__dict__["_scenario_step_line_map"] = line_map
    except Exception:
        context.__dict__["_scenario_steps_index"] = []
        context.__dict__["_scenario_step_line_map"] = {}

    if not enabled:
        return
    context.__dict__["_record_steps"] = []
    context.__dict__["_record_feature_relpath"] = feature_relpath
    context.__dict__["_record_feature_name"] = getattr(scenario.feature, "name", None) or "Recorded feature"
    context.__dict__["_record_scenario_name"] = scenario.name or "Recorded scenario"
    context.__dict__["_record_started_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")


def mark_step_executed(context, step) -> None:
    """
    Отмечает шаг сценария как выполненный в UI-панели (если панель активна).
    """
    try:
        page = getattr(context, "page", None)
        if not page:
            return
        idx = None
        line = getattr(step, "line", None)
        if line is not None:
            idx = context.__dict__.get("_scenario_step_line_map", {}).get(int(line))
        if idx is None:
            kw = (getattr(step, "keyword", "") or "").strip()
            nm = (getattr(step, "name", "") or "").strip()
            target = f"{kw} {nm}".strip()
            for it in context.__dict__.get("_scenario_steps_index", []) or []:
                if f"{it.get('keyword','').strip()} {it.get('name','').strip()}".strip() == target:
                    idx = int(it.get("idx"))
                    break
        if idx is None:
            return
        page.evaluate(
            "(i) => { try { window.___uiRecorderMarkScenarioStepDone && window.___uiRecorderMarkScenarioStepDone(i); } catch (e) {} }",
            idx,
        )
    except Exception:
        return


def record_after_step(context, step) -> None:
    """
    Фиксируем ФАКТИЧЕСКИ выполненные шаги, как они были в .feature.
    Плюс docstring и таблицы, если есть (их прокидывает environment.before_step).
    """
    if not context.__dict__.get("_record_steps_enabled", False):
        return
    try:
        keyword = (getattr(step, "keyword", "") or "").strip() or "When"
        name = (getattr(step, "name", "") or "").strip()
        line = f"{keyword} {name}".rstrip()

        indent = "    "
        context.__dict__.setdefault("_record_steps", []).append(indent + line)

        ds = context.__dict__.get("_step_text")
        tb = context.__dict__.get("_step_table")
        context.__dict__.setdefault("_record_steps", []).extend(_gherkin_docstring(ds, indent))
        context.__dict__.setdefault("_record_steps", []).extend(_gherkin_table(tb, indent))
    except Exception:
        return


def append_recorded_step_line(context, line: str) -> None:
    """
    Добавляет строку шага в записываемый сценарий.
    line должен быть уже в формате: 'When ...' / 'Then ...' / 'Given ...'
    """
    if not context.__dict__.get("_record_steps_enabled", False):
        return
    indent = "    "
    text = (line or "").strip()
    if not text:
        return
    context.__dict__.setdefault("_record_steps", []).append(indent + text)


def append_ui_step_line(context, step_id: str, step_text: str) -> None:
    """
    Добавляет шаг, созданный UI-рекордером, с идентификатором.
    Это нужно, чтобы можно было удалить шаг в панели и исключить его при сохранении.
    """
    if not context.__dict__.get("_record_steps_enabled", False):
        return
    sid = (step_id or "").strip()
    txt = (step_text or "").strip()
    if not sid or not txt:
        return
    indent = "    "
    context.__dict__.setdefault("_record_steps", []).append(f"{indent}{txt}  {_UI_TAG_PREFIX}{sid}")


def mark_ui_step_deleted(context, step_id: str) -> None:
    if not context.__dict__.get("_record_steps_enabled", False):
        return
    sid = (step_id or "").strip()
    if not sid:
        return
    context.__dict__.setdefault("_record_ui_deleted", set()).add(sid)


def save_recorded_feature(context) -> str | None:
    """
    Сохраняет записанные шаги в отдельный .feature.
    Возвращает путь к файлу или None.
    """
    if not context.__dict__.get("_record_steps_enabled", False):
        return None
    out_dir = record_out_dir(context)
    os.makedirs(out_dir, exist_ok=True)

    scenario_name = _sanitize_filename(context.__dict__.get("_record_scenario_name") or "scenario")
    feature_name = _sanitize_filename(context.__dict__.get("_record_feature_name") or "feature")
    ts = context.__dict__.get("_record_started_at") or datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    file_name = f"record_{feature_name}__{scenario_name}__{ts}.feature"
    out_path = os.path.join(out_dir, file_name)

    lines: list[str] = []
    lines.append("# savetest_status: new")
    lines.append("# savetest_author: auto")
    lines.append(f"# savetest_created_at: {datetime.utcnow().strftime('%Y-%m-%d')}")
    lines.append(f"@suite:{uuid.uuid4()}")
    lines.append("")
    lines.append(f"Feature: {context.__dict__.get('_record_feature_name', 'Recorded feature')}")
    lines.append("")
    lines.append(f"  @tms:{uuid.uuid4()}")
    lines.append("  @severity:high")
    lines.append("  @tag:ui")
    lines.append(f"  Scenario: {context.__dict__.get('_record_scenario_name', 'Recorded scenario')}")
    lines.append("")
    steps = context.__dict__.get("_record_steps", [])
    deleted = context.__dict__.get("_record_ui_deleted") or set()
    if steps:
        for s in steps:
            if _UI_TAG_PREFIX in s:
                try:
                    sid = s.split(_UI_TAG_PREFIX, 1)[1].strip()
                except Exception:
                    sid = ""
                if sid and sid in deleted:
                    continue
                # Убираем артефакт # ui:id_... из вывода
                line = s.split(_UI_TAG_PREFIX, 1)[0].rstrip()
                lines.append(line)
    else:
        lines.append("    Given Пустой шаг")
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def _sanitize_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^A-Za-zА-Яа-я0-9 _.-]", "_", name)
    name = name.strip(" ._-")
    return name or "scenario"


def _gherkin_docstring(text: str | None, indent: str) -> list[str]:
    if text is None:
        return []
    raw = str(text)
    if not raw.strip():
        return []
    lines = [indent + '"""']
    for ln in raw.splitlines():
        lines.append(indent + ln)
    lines.append(indent + '"""')
    return lines


def _gherkin_table(table, indent: str) -> list[str]:
    if not table:
        return []
    out: list[str] = []
    try:
        headings = getattr(table, "headings", None)
        if headings:
            out.append(indent + "| " + " | ".join(str(x) for x in headings) + " |")
        for row in table.rows:
            out.append(indent + "| " + " | ".join(str(x) for x in row.cells) + " |")
    except Exception:
        return []
    return out

