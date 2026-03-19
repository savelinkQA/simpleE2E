import os
import time
import uuid

import allure
from allure_commons.types import AttachmentType
import SimpleITK as sitk
from behave import *

from helpers.action import ClassAction
from helpers.check import ClassCheck
from helpers.prepare import (
    allure_attach_png,
    global_selector_for_iframe,
    prepare_text,
)

from features.steps.utils import step_screen

use_step_matcher("cfparse")


def _step_screen_iframe(context):
    name = str(uuid.uuid4())
    try:
        screenshot_timeout = 30  # секунд
        start_time = time.time()

        png_bytes = context.page.locator(selector=global_selector_for_iframe).screenshot(path=f"{name}.png")

        if time.time() - start_time > screenshot_timeout:
            raise TimeoutError(f"Создание скриншота iframe заняло более {screenshot_timeout} секунд")

        if not os.path.exists(f"{name}.png"):
            raise FileNotFoundError(f"Скриншот iframe {name}.png не был создан")

        if os.path.getsize(f"{name}.png") == 0:
            raise ValueError(f"Скриншот iframe {name}.png пустой")

        if png_bytes is not None:
            allure.attach(png_bytes, name=f"{name}.png", attachment_type=AttachmentType.PNG)
        else:
            allure_attach_png(f"{name}.png", name)
    except Exception:
        allure_attach_png(f"{name}.png", name)


def _assert_iframe_screen_matches(context, path_screen: str):
    directory_expect = os.path.dirname(os.path.dirname(__file__)) + "/screens/"

    name_new_screen = str(uuid.uuid4())
    name_expect_screen = path_screen.split("/")[-1]

    context.page.locator(selector=global_selector_for_iframe).screenshot(path=f"{name_new_screen}.png")

    with allure.step("Скрин текущего состояния (iframe)"):
        allure_attach_png(f"{name_new_screen}.png", name_new_screen)

    with allure.step("Скрин эталонный " + path_screen):
        allure_attach_png(directory_expect + path_screen, name_expect_screen)

    img1 = sitk.ReadImage(directory_expect + path_screen, sitk.sitkUInt8)
    img2 = sitk.ReadImage(f"{name_new_screen}.png", sitk.sitkUInt8)

    name_diff = str(uuid.uuid4())
    diff = sitk.Abs(img1 - img2)
    sitk.WriteImage(diff, f"{name_diff}.png")

    with allure.step("Разница изображений (iframe)"):
        allure_attach_png(f"{name_diff}.png", name_diff)

    minMaxFilter = sitk.StatisticsImageFilter()
    minMaxFilter.Execute(diff)

    if minMaxFilter.GetMean() > 0.1:
        assert 1 == 2, "Ошибка сравнения скриншотов (iframe)"


@when('iframe. Я нажимаю "{name}"/"{selector}"')
def step_iframe_click_button(context, selector, name):
    page = ClassAction(context)
    page.click(context.page.frame_locator(selector=global_selector_for_iframe).locator(selector), name=str(name))
    step_screen(context)


@when('iframe. Я навожу "{name}"/"{selector}"')
def step_iframe_hover_button(context, selector, name):
    page = ClassAction(context)
    page.hover(context.page.frame_locator(selector=global_selector_for_iframe).locator(selector), name=str(name))
    step_screen(context)


@when('iframe. Клик по координатам ("{x}", "{y}") в "{name}"/"{selector}"')
def step_iframe_click_coord(context, selector, name, x, y):
    page = ClassAction(context)
    page.click(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=str(name),
        position={"x": int(x), "y": int(y)},
        force=True,
    )
    step_screen(context)


@when('iframe. Я нажимаю дважды "{name}"/"{selector}"')
def step_iframe_dbclick_button(context, selector, name):
    page = ClassAction(context)
    page.dblclick(context.page.frame_locator(selector=global_selector_for_iframe).locator(selector), name=str(name))
    step_screen(context)


@when('iframe. Я нажимаю ПКМ на "{name}"/"{selector}"')
def step_iframe_click_rigth_click_button(context, selector, name):
    page = ClassAction(context)
    page.click(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=str(name),
        button="right",
    )
    step_screen(context)


@when('iframe. Я ввожу "{text}" в "{name}"/"{selector}"')
def step_iframe_fill_input_dialog(context, text, selector, name):
    page = ClassAction(context)
    text = prepare_text(text)
    page.fill(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        text=text,
        name=name,
    )
    step_screen(context)


@when('iframe. Я очищаю поле "{name}"/"{selector}"')
def step_iframe_clear_input(context, selector, name):
    page = ClassAction(context)
    page.fill(context.page.frame_locator(selector=global_selector_for_iframe).locator(selector), text="", name=name)
    step_screen(context)


@when('iframe. Я ввожу большой текст в "{name}"/"{selector}"')
def step_iframe_fill_input_big(context, selector, name):
    page = ClassAction(context)
    text = prepare_text(context.text)
    page.fill(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        text=text,
        name=name,
    )
    step_screen(context)


@when('iframe. Я нажимаю на текст "{text}"')
def step_iframe_click_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.click_iframe_on_text(frame_selector=global_selector_for_iframe, text=text)
    step_screen(context)


@when('iframe. Я навожу на текст "{text}"')
def step_iframe_hover_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.hover_iframe_on_text(frame_selector=global_selector_for_iframe, text=text)
    step_screen(context)


@when('iframe. Я нажимаю дважды на текст "{text}"')
def step_iframe_dbclick_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.db_click_iframe_on_text(frame_selector=global_selector_for_iframe, text=text)
    step_screen(context)


@when('iframe. Я нажимаю ПКМ на текст "{text}"')
def step_iframe_rigth_click_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.rigth_click_iframe_on_text(frame_selector=global_selector_for_iframe, text=text)
    step_screen(context)


@when('iframe. Я перезагружаю страницу')
def step_iframe_reload_page(context):
    page = ClassCheck(context)
    context.page.reload()
    selector = "app-headers"
    name = "Панель расширения"
    page.check_visibility(context.page.locator(selector=selector), name=name)
    step_screen(context)


@when('iframe. Скрин')
def step_iframe_screen(context):
    _step_screen_iframe(context)


@then('iframe. Вижу "{name}"/"{selector}"')
def step_iframe_element_to_selector(context, selector, name):
    page = ClassCheck(context)
    page.check_visibility(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
    )


@then('iframe in iframe. Вижу "{name}"/"{selector}"')
def step_iframe_element_to_selector_in_double_iframe(context, selector, name):
    page = ClassCheck(context)
    page.check_visibility(
        context.page.frame_locator(selector=global_selector_for_iframe).frame_locator("iframe").locator(selector),
        name=name,
    )


@then('iframe. Жду "{name}"/"{selector}". Жду="{time}" мс')
def step_iframe_element_to_selector_with_time(context, selector, name, time):
    page = ClassCheck(context)
    page.check_visibility(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
        timeout=float(time),
    )


@then('iframe. НЕ Вижу "{name}"/"{selector}"')
def step_iframe_not_see_element_to_selector(context, selector, name):
    exist = True
    page = ClassCheck(context)
    for _ in range(0, 10):
        exist = page.check_exists(
            context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
            name=name,
        )
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@then('iframe. Вижу кнопку "{name}"/"{selector}"')
def step_iframe_button_to_selector(context, selector, name):
    page = ClassCheck(context)
    page.check_button(context.page.frame_locator(selector=global_selector_for_iframe).locator(selector), name=name)


@then('iframe. Вижу в "{name}"/"{selector}" текст ~ "{text}"')
def step_iframe_chunk_text_to_selector(context, selector, name, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_contain_all_text(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
        texts=text,
    )


@then('iframe. Вижу в "{name}"/"{selector}" текст = "{text}"')
def step_iframe_full_text_to_selector(context, selector, name, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_have_all_text(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
        text=text,
    )


@then('iframe. Вижу текст "{text}"')
def step_iframe_text(context, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_iframe_text_visibility(frame_selector=global_selector_for_iframe, text=text)


@then('iframe. НЕ Вижу текст "{text}"')
def step_iframe_not_see_text(context, text):
    exist = True
    text = prepare_text(text)
    page = ClassCheck(context)
    for _ in range(0, 10):
        exist = page.check_iframe_exists_text(frame_selector=global_selector_for_iframe, text=text)
        if exist:
            time.sleep(1)
        else:
            break
    if exist:
        assert 1 == 2, "Элемент существует"


@then('iframe. Вижу в "{name}"/"{selector}" класс "{value}"')
def step_iframe_check_attr(context, selector, name, value):
    page = ClassCheck(context)
    page.check_have_class(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
        class_name=value,
    )


@then('iframe. Скрытый "{name}"/"{selector}"')
def step_iframe_hidden_element_to_selector(context, selector, name):
    page = ClassCheck(context)
    page.check_hidden(context.page.frame_locator(selector=global_selector_for_iframe).locator(selector), name=name)


@then('iframe. Вижу в инпуте "{name}"/"{selector}" текст = "{text}"')
def step_iframe_check_input_text_to_selector(context, selector, name, text):
    text = prepare_text(text)
    page = ClassCheck(context)
    page.check_content_input(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
        text=text,
    )


@then('iframe. Вижу в "{name}"/"{selector}" css "{css_style}":"{css_value}"')
def step_iframe_check_css_style_to_selector(context, selector, name, css_style, css_value):
    page = ClassCheck(context)
    page.check_css_style(
        context.page.frame_locator(selector=global_selector_for_iframe).locator(selector),
        name=name,
        css_style=css_style,
        css_value=css_value,
    )


@then('iframe. Сравнить со скрином "{path_screen}"')
def step_iframe_assert_screen(context, path_screen):
    _assert_iframe_screen_matches(context, path_screen)

