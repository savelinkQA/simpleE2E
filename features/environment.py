import sys
import os
import allure
import uuid
from allure_commons.types import AttachmentType
from playwright.sync_api import sync_playwright
from steps.preconditional import step_visit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../../')

from helpers.step_recording import (
    init_recording_for_scenario,
    mark_step_executed,
    record_after_step,
    save_recorded_feature,
)

# def before_all(context):
#     pass


def before_step(context, step):
    """Пробрасывает docstring (JSON) и таблицу шага в context."""
    context._step_text = step.text if hasattr(step, "text") and step.text else None
    context._step_table = step.table if hasattr(step, "table") and step.table else None


def before_scenario(context, scenario):
    with allure.step('------------------Старт Сценария------------------'):
        if 'HOST' in context.config.userdata.keys():
            context.host = context.config.userdata['HOST']
        else:
            context.host = ""

        # behave -D BROWSER=chrome
        if 'BROWSER' in context.config.userdata.keys():
            BROWSER = context.config.userdata['BROWSER']
        else:
            BROWSER = 'chrome'

        p = sync_playwright().start()
        context.playwright = p

        # behave -D HEADLESS
        HEADLESS = True if 'HEADLESS' in context.config.userdata.keys() else False

        if BROWSER == 'chrome':
            context.browser = p.chromium.launch(headless=HEADLESS)
        elif BROWSER == 'firefox':
            context.browser = p.firefox.launch(headless=HEADLESS)

        context.playwright_context = context.browser.new_context()
        context.playwright_context.tracing.start(screenshots=True, snapshots=True, sources=True)

        # Если передали хост, то сразу начинаем с визита на него
        if context.host != "":
            step_visit(context, context.host)

        # --- MVP: запись выполненных шагов в отдельный .feature ---
        try:
            feature_file_path = scenario.feature.filename
            relative_path = os.path.relpath(feature_file_path, os.getcwd())
        except Exception:
            relative_path = None
        init_recording_for_scenario(context, scenario, feature_relpath=relative_path)


def after_step(context, step):
    """
    MVP: фиксируем ФАКТИЧЕСКИ выполненные шаги, как они были в .feature.
    Это обеспечивает 100% соответствие библиотеке шагов (вариант B).
    """
    record_after_step(context, step)
    mark_step_executed(context, step)
    # Обработка очереди скриншотов (Эталонный скрин из панели записи)
    if context.__dict__.get("_ui_recorder_enabled"):
        try:
            page = getattr(context, "page", None)
            if page:
                try:
                    page.evaluate("1")  # дать Playwright обработать CDP (binding)
                except Exception:
                    pass
            from helpers.ui_recorder import process_screenshot_queue

            process_screenshot_queue(context)
        except Exception:
            pass


def after_scenario(context, scenario):
    with allure.step('------------------Финиш Сценария------------------'):
        try:
            name = str(uuid.uuid4())
            allure.attach(context.page.screenshot(path=f"{name}.png"), name=f"{name}.png",
                          attachment_type=AttachmentType.PNG)
            allure.attach(context.playwright_context.tracing.stop(path=f'{name}.zip'), name=f'{name}.zip')
            context.browser.close()
            context.playwright.stop()
        except:
            context.browser.close()
            context.playwright.stop()

        # --- MVP: сохраняем .feature с записанными шагами ---
        if getattr(context, "_record_steps_enabled", False):
            try:
                out_path = save_recorded_feature(context)
                # Чтобы легко найти в отчётах — приложим путь текстом
                if out_path:
                    allure.attach(out_path, name="recorded_feature_path", attachment_type=allure.attachment_type.TEXT)
            except Exception as e:
                allure.attach(
                    f"Не удалось сохранить recorded feature: {e}",
                    name="recorded_feature_error",
                    attachment_type=allure.attachment_type.TEXT,
                )

# def after_all(context):
#     Example for clean data after autotest:
#     """
#     from helpers.api import Api
#     from helpers.prepare import get_prefics
#
#     api = Api(context.host)
#     for i in range(0, 300):
#         response = api.get(context.host + 'api/v1/entity'),
#                                 params={"name": get_prefics()})
#         if responce.status_code > 299:
#             continue
#         rows = response.json()['rows']
#         if len(rows) < 1:
#             return
#         for row in rows:
#             api.delete(context.host + 'api/v1/entity/' + str(row['id']), params={"hard": True}
#
#     """
