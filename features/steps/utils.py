import uuid
import time
import allure
import SimpleITK as sitk
import os
from allure_commons.types import AttachmentType
from helpers.action import ClassAction
from helpers.check import ClassCheck
from helpers.prepare import allure_attach_png
from helpers.ui_recorder import enable_ui_recording, process_screenshot_queue

from behave import *

use_step_matcher("cfparse")


@when('Я чищу куки')
def step_clean_cookie(context):
    context.playwright_context.clear_cookies()
    # И дополнительно чистим localStorage / sessionStorage во всех открытых вкладках,
    # чтобы гарантированно сбросить авторизацию фронта
    try:
        for page in context.playwright_context.pages:
            try:
                page.evaluate(
                    "() => { "
                    "window.localStorage.clear(); "
                    "window.sessionStorage.clear(); "
                    "}"
                )
            except Exception:
                pass
    except Exception:
        pass
    step_screen(context)


@Given('Дефект "{short_name}"/"{url}"')
def step_allure(context, url, short_name):
    allure.dynamic.issue(url=url, name=short_name)


@when('Я перезагружаю страницу')
def step_reload_page(context):
    context.page.reload()
    step_screen(context)


@when('Пауза "{sec}"')
def step_pause(context, sec):
    deadline = time.time() + int(sec)
    page = getattr(context, "page", None)
    while time.time() < deadline:
        # evaluate даёт Playwright обработать CDP (binding от "Эталонный скрин")
        if page:
            try:
                page.evaluate("1")
            except Exception:
                pass
        time.sleep(0.15)
        process_screenshot_queue(context)
    step_screen(context)


@when('Жду исчезновения прелоадера')
def step_waiting_preloader(context):
    selector = '[data-test-id="page-loader"]'
    exist = True
    page = ClassCheck(context)
    for _ in range(0, 60):
        exist = page.check_exists(context.page.locator(selector=selector), name="Прелоадер")
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@when('Жду исчезновения прелоадера "{selector}"')
def step_waiting_preloader_custom(context, selector):
    exist = True
    page = ClassCheck(context)
    for _ in range(0, 60):
        exist = page.check_exists(context.page.locator(selector=selector), name="Прелоадер")
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@Given("Я включаю запись действий в браузере")
@when("Я включаю запись действий в браузере")
def step_enable_ui_recording(context):
    """
    Включает запись кликов/ввода текста в текущем браузерном окне.
    Использовать вместе с:
    -D HEADLESS=0  (чтобы был видимый браузер)
    -D RECORD=1    (чтобы в конце сохранился новый .feature)
    """
    enable_ui_recording(context)


@when('Я скролю до "{name}"/"{selector}"')
def step_scroll_to_element(context, selector, name):
    page = ClassAction(context)
    page.scroll_to_element(context.page.locator(selector=selector), name)
    step_screen(context)


@when('Я скролю "{count}" раз по "{point}"')
def step_scroll_point(context, count, point):
    page = ClassAction(context)
    page.scroll_point(count, point)
    step_screen(context)


@when('Скрин')
def step_screen(context):
    name = str(uuid.uuid4())
    allure.attach(context.page.screenshot(path=f"{name}.png"), name=f"{name}.png", attachment_type=AttachmentType.PNG)


@then('Сравнить со скрином "{path_screen}"')
def step_assert_screen(context, path_screen):
    directory_expect = os.path.dirname(os.path.dirname(__file__)) + "/screens/"

    name_new_screen = str(uuid.uuid4())
    name_expect_screen = path_screen.split("/")[-1]
    context.page.screenshot(path=f"{name_new_screen}.png")

    with allure.step(f'Скрин текущего состояния'):
        allure_attach_png(f"{name_new_screen}.png", name_new_screen)
    with allure.step(f'Скрин эталонный ' + path_screen):
        allure_attach_png(directory_expect + path_screen, name_expect_screen)

    img1 = sitk.ReadImage(directory_expect + path_screen, sitk.sitkUInt8)
    img2 = sitk.ReadImage(f"{name_new_screen}.png", sitk.sitkUInt8)

    name_diff = str(uuid.uuid4())

    # Вычисление разницы между изображениями
    diff = sitk.Abs(img1 - img2)
    sitk.WriteImage(diff, f'{name_diff}.png')
    with allure.step(f'Разница изображений'):
        allure_attach_png(f'{name_diff}.png', name_diff)

    # Вычисление среднего значения разницы
    minMaxFilter = sitk.StatisticsImageFilter()
    minMaxFilter.Execute(diff)

    # Проверка условия сравнения
    if minMaxFilter.GetMean() > 0.1:
        assert 1 == 2, 'Ошибка сравнения скриншотов'


@When('Я загружаю файл через браузер. Локальный путь="{path_local}", "{name}"/"{selector}"')
def step_load_file_browser_when(context, path_local, name, selector):
    page = ClassAction(context)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw_path = str(path_local or "").strip()
    candidates = []
    if os.path.isabs(raw_path):
        candidates.append(raw_path)
    candidates.extend(
        [
            os.path.abspath(os.path.join(project_root, raw_path)),
            os.path.abspath(os.path.join(project_root, "Database", raw_path)),
            os.path.abspath(os.path.join(project_root, "Database", "File", raw_path)),
        ]
    )
    full_path = next((p for p in candidates if os.path.exists(p)), None)
    if not full_path:
        raise FileNotFoundError(f"Файл не найден. Проверены пути: {candidates}")
    trigger_locator = context.page.locator(selector=selector)
    page.upload_file_via_chooser(file_path=full_path, trigger_locator=trigger_locator, name=name)
    step_screen(context)
