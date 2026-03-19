from behave import *
from helpers.action import ClassAction
from features.steps.utils import step_screen
from helpers.prepare import prepare_text

use_step_matcher("cfparse")


@when('Я перехожу по ссылке = "{url}"')
def step_visit_link_full(context, url):
    context.page = context.playwright_context.new_page()
    page = ClassAction(context)
    page.visit(url)


@when('Я перехожу по ссылке ~ "{url}"')
def step_visit_link(context, url):
    context.page = context.playwright_context.new_page()
    page = ClassAction(context)
    page.visit(context.host + url)


@when('Я перехожу на страницу "{url}"')
def step_go_to_page(context, url):
    if getattr(context, "page", None) is None:
        context.page = context.playwright_context.new_page()
    page = ClassAction(context)
    page.visit(url)


@when('Я нажимаю "{name}"/"{selector}"')
def step_click_button(context, selector, name):
    page = ClassAction(context)
    page.click(context.page.locator(selector=selector), name=str(name))
    step_screen(context)


@when('Я навожу на "{name}"/"{selector}"')
def step_hover_button(context, selector, name):
    page = ClassAction(context)
    page.hover(context.page.locator(selector=selector), name=str(name))
    step_screen(context)


@when('Я нажимаю+ctrl "{name}"/"{selector}"')
def step_click_with_ctrl_button(context, selector, name):
    page = ClassAction(context)
    page.click(context.page.locator(selector=selector), name=str(name), modifiers=["Control"])
    step_screen(context)


@when('Я нажимаю "{button}" на клавиатуре')
def step_ctrl_a_button(context, button):
    page = ClassAction(context)
    page.press(key=button)
    step_screen(context)


@when('Я нажимаю дважды "{name}"/"{selector}"')
def step_dbclick_button(context, selector, name):
    page = ClassAction(context)
    page.dblclick(context.page.locator(selector=selector), name=str(name))
    step_screen(context)


@when('Я нажимаю ПКМ на "{name}"/"{selector}"')
def step_click_rigth_click_button(context, selector, name):
    page = ClassAction(context)
    page.click(context.page.locator(selector=selector), name=str(name), button="right")
    step_screen(context)


@when('Я нажимаю на текст "{text}"')
def step_click_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.click_on_text(text)
    step_screen(context)


@when('Я нажимаю дважды на текст "{text}"')
def step_dbclick_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.db_click_on_text(text)
    step_screen(context)


@when('Я нажимаю ПКМ на текст "{text}"')
def step_rigth_click_text(context, text):
    text = prepare_text(text)
    page = ClassAction(context)
    page.rigth_click_on_text(text)
    step_screen(context)


@when('Я ввожу "{text}" в "{name}"/"{selector}"')
def step_fill_input_dialog(context, text, selector, name):
    text = prepare_text(text)
    page = ClassAction(context)
    page.fill(context.page.locator(selector=selector), text=text, name=name)
    step_screen(context)


@when('Я тащу "{name}"/"{selector1}" в "{selector2}"')
def step_click_button(context, selector1, selector2, name):
    page = ClassAction(context)
    page.drag_and_drop(locator1=context.page.locator(selector=selector1),
                       locator2=context.page.locator(selector=selector2), name=str(name))
    step_screen(context)


@when('Клик по координатам "{x}", "{y}"')
def step_click_coordinate(context, x, y):
    page = ClassAction(context)
    page_context = context.page
    page.mouse_click_coordinate(page=page_context, coordinate={"x": int(x), "y": int(y)})
    step_screen(context)


@when('Кликнуть и тянуть "{x1}", "{y1}" - "{x2}", "{y2}"')
def step_click_coordinate_with_move(context, x1, y1, x2, y2):
    page = ClassAction(context)
    page_context = context.page
    page.mouse_click_move(page=page_context,
                          coordinate_start={"x": int(x1), "y": int(y1)},
                          coordinate_end={"x": int(x2), "y": int(y2)})
    step_screen(context)


@when('Я ввожу большой текст в "{name}"/"{selector}"')
def step_fill_input_dialog_big(context, selector, name):
    text = prepare_text(context.text)
    page = ClassAction(context)
    page.fill(context.page.locator(selector=selector), text=text, name=name)
    step_screen(context)
