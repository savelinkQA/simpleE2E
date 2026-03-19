from behave import *
import time
from helpers.check import ClassCheck
from helpers.prepare import prepare_text

use_step_matcher("cfparse")


@then('Вижу текст "{text}"')
def step_see_text(context, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_text_visibility(text)


@then('НЕ Вижу текст "{text}"')
def step_not_see_text(context, text):
    exist = True
    text = prepare_text(text)
    page = ClassCheck(context)
    for i in range(0, 10):
        exist = page.check_exists_text(text)
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@then('Вижу "{name}"/"{selector}"')
def step_element_to_selector(context, selector, name):
    page = ClassCheck(context)
    page.check_visibility(context.page.locator(selector=selector), name=name)


@then('Жду "{name}"/"{selector}". Жду="{time}" мс')
def step_element_to_selector_with_time(context, selector, name, time):
    page = ClassCheck(context)
    page.check_visibility(context.page.locator(selector=selector), name=name, timeout=float(time))


@then('Жду исчезновения прелоадера "{selector}"')
def step_waiting_preloader_custom(context, selector):
    exist = True
    page = ClassCheck(context)
    for i in range(0, 60):
        exist = page.check_exists(context.page.locator(selector=selector), name="Прелоадер")
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@then('НЕ Вижу "{name}"/"{selector}"')
def step_not_contain_element_to_selector(context, selector, name):
    exist = True
    page = ClassCheck(context)
    for i in range(0, 10):
        exist = page.check_exists(context.page.locator(selector=selector), name=name)
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@then('Вижу кнопку "{name}"/"{selector}"')
def step_button_to_selector(context, selector, name):
    page = ClassCheck(context)
    page.check_button(context.page.locator(selector=selector), name=name)


@then('Вижу в "{name}"/"{selector}" текст ~ "{text}"')
def step_chunk_text_to_selector(context, selector, name, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_contain_all_text(context.page.locator(selector=selector), name=name, texts=text)


@then('Вижу в "{name}"/"{selector}" текст = "{text}"')
def step_full_text_to_selector(context, selector, name, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_have_all_text(context.page.locator(selector=selector), name=name, text=text)


@then('Вижу в "{name}"/"{selector}" класс "{value}"')
def step_check_attr(context, selector, name, value):
    page = ClassCheck(context)
    page.check_have_class(context.page.locator(selector=selector), name=name, class_name=value)


@then('Скрытый "{name}"/"{selector}"')
def step_hidden_element_to_selector(context, selector, name):
    page = ClassCheck(context)
    page.check_hidden(context.page.locator(selector), name=name)


@then('Текущий URL ~ "{url}"')
def step_check_current_url(context, url):
    page = ClassCheck(context)
    page.check_current_url(context.host + url)


@then('Текущий URL = "{url}"')
def step_check_current_url_full(context, url):
    page = ClassCheck(context)
    page.check_current_url(url)


@then('Вижу прелоадер')
def step_see_preloader(context):
    page = ClassCheck(context)
    selector = '[data-test-id="page-loader"]'
    name = "Прелоадер"
    page.check_visibility(context.page.locator(selector=selector), name=name)


@then('Вижу диалоговое окно')
def step_open_dialog(context):
    page = ClassCheck(context)
    selector = '[role="dialog"]'
    name = "Диалоговое окно"
    page.check_visibility(context.page.locator(selector=selector), name=name)


@then('НЕ Вижу диалоговое окно')
def step_close_dialog(context):
    page = ClassCheck(context)
    selector = '[role="dialog"]'
    name = "Диалоговое окно"
    page.check_not_visibility(context.page.locator(selector=selector), name=name)


@then('Вижу аллерт окно')
def step_open_alert_dialog(context):
    page = ClassCheck(context)
    selector = '[role="alertdialog"]'
    name = "Аллерт окно"
    page.check_visibility(context.page.locator(selector=selector), name=name)


@then('НЕ Вижу аллерт окно')
def step_close_alert_dialog(context):
    page = ClassCheck(context)
    selector = '[role="alertdialog"]'
    name = "Аллерт окно"
    page.check_not_visibility(context.page.locator(selector=selector), name=name)
