from typing import Union
import allure
from playwright.sync_api import Locator, expect
import re

class ClassCheck:
    def __init__(self, context):
        self.page = context.page

    def check_button(self, locator: Locator, disabled: bool = False, name=''):
        """
        Метод для проверки кнопок
        :param locator: локатор элемента
        :param disabled: доступность кнопки
        :param name: имя элемента. Только для allure
        """
        with allure.step(f'Проверка кнопки {name}'):
            if disabled:
                self.check_disabled(locator)
            else:
                self.check_not_disabled(locator)
            self.check_visibility(locator)

    def check_button_multiple(self, locators: Union[list, tuple], name=''):
        """
        Метод для проверки нескольких кнопок
        :param locators: locators: tuple или list с локаторами и значениями disabled
        следующего вида: ((Locator, Disabled), ...)
        :param name: имя элемента. Только для allure
        """
        with allure.step(f'Проверка группы кнопок {name}'):
            for btn, disb in locators:
                self.check_button(locator=btn, disabled=disb)

    def check_not_disabled(self, locator: Locator, name='', **kwargs):
        """
        Метода проверки на доступность
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода not_to_be_disabled()
        """
        with allure.step(f'Проверка доступности элемента {name}'):
            expect(locator).not_to_be_disabled(**kwargs)

    def check_disabled(self, locator: Locator, name='', **kwargs):
        """
        Метода проверки на недоступность
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_be_disabled()
        """
        with allure.step(f'Проверка недоступности элемента {name}'):
            expect(locator).to_be_disabled(**kwargs)

    def check_visibility(self, locator: Locator, name='', **kwargs):
        """
        Метод проверки видимости элемента
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_be_visible()
        """
        with allure.step(f'Проверка видимости элемента {name}'):
            expect(locator).to_be_visible(**kwargs)

    def check_exists(self, locator: Locator, name=''):
        """
        Метод проверки существавания элемента
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :returns boolean: возвращает boolean существования элемента
        """
        with allure.step(f'Проверка НЕ существования элемента {name}'):
            try:
                expect(locator).to_be_attached(timeout=1)
                return True
            except:
                return False

    def check_not_visibility(self, locator: Locator, name='', **kwargs):
        """
        Метод проверки невидимости элемента
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода not_to_be_visible()
        """
        with allure.step(f'Проверка невидимости элемента {name}'):
            expect(locator).not_to_be_visible(**kwargs)

    def check_not_visibility_multiple(self, locators: Union[list, tuple], name='', **kwargs):
        """
        Метод проверки невидимости нескольких элементов
        :param locators: tuple или list с локаторами
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода not_to_be_visible()
        """
        with allure.step(f'Проверка невидимости группы элементов {name}'):
            for item in locators:
                self.check_not_visibility(locator=item, **kwargs)

    def check_visibility_multiple(self, locators: Union[list, tuple], name='', **kwargs):
        """
        Метод проверки видимости нескольких элементов
        :param locators: tuple или list с локаторами
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_be_visible()
        """
        with allure.step(f'Проверка видимости группы элементов {name}'):
            for item in locators:
                self.check_visibility(locator=item, **kwargs)

    def check_contain_text(self, locator: Locator, text: str, name='', **kwargs):
        """
        Метод проверки текста у элемента по вхождению
        :param locator: локатор элемента
        :param text: текст который нужно проверить
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_contain_text()
        """
        with allure.step(f'Проверка наличия текста {text} по вхождению у элемента {name}'):
            expect(locator).to_contain_text(text, **kwargs)

    def check_have_class(self, locator: Locator, class_name: str, name='', **kwargs):
        """
        Метод проверки текста у элемента по вхождению
        :param locator: локатор элемента
        :param class_name: имя класса для проверки
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_have_class()
        """
        with allure.step(f'Проверка наличия класса {class_name} у элемента {name}'):
            expect(locator).to_have_class(re.compile(class_name), **kwargs)

    def check_contain_text_multiple(self, locators: Union[list, tuple], name='', **kwargs):
        """
        Метод проверки текста элемента по вхождению у нескольких элементов
        :param locators: tuple или list с локаторами и текстами следующего вида: ((Locator, Text), ...)
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_contain_text()
        """
        with allure.step(f'Проверка текста по вхождению у группы элементов {name}'):
            for loc, txt in locators:
                self.check_contain_text(locator=loc, text=txt, **kwargs)

    def check_contain_all_text(self, locator: Locator, texts: Union[list, tuple], name='', **kwargs):
        """
        Метод проверки текста элемента по вхождению для локатора который возвращает несколько элементов
        :param locator: локатор элементов
        :param texts: tuple или list с ожидаемыми текстами в последовательном порядке
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_contain_text()
        """
        with allure.step(f'Проверка наличия текстов по вхождению у элементов {name}'):
            expect(locator).to_contain_text(texts)

    def check_have_all_text(self, locator: Locator, text: str, name='', **kwargs):
        """
        Метод проверки текста элемента (по строгому совпадению) для локатора который возвращает несколько элементов
        :param locator: локатор элементов
        :param text: str с ожидаемыми текстом
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_have_text()
        """
        with allure.step(f'Проверка наличия текста {text} по строгому совпадению в элементе {name}'):
            expect(locator).to_have_text(text)

    def check_count(self, locator: Locator, count: int, name='', **kwargs):
        """
        Метод проверки количества элементов
        :param locator: локатор элементов
        :param count: ожидаемое количество
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода to_have_count()
        """
        with allure.step(f'Проверка количества элементов {name}'):
            expect(locator).to_have_count(count)

    def check_text_visibility(self, text):
        """
        Метод проверки видимости текста
        :param text: текст который нужно проверить
        """
        with allure.step(f'Проверка видимости текста {text}'):
            locator = self.page.get_by_text(text=text).last
            self.check_visibility(locator=locator)

    def check_iframe_text_visibility(self, frame_selector, text):
        """
        Метод проверки видимости текста
        :param frame_selector: селектор iframe
        :param text: текст который нужно проверить
        """
        with allure.step(f'Проверка видимости текста в iframe {text}'):
            locator = self.page.frame_locator(frame_selector).get_by_text(text=text).last
            self.check_visibility(locator=locator)

    def check_exists_text(self, text):
        """
        Метод проверки существавания текста
        :param text: текст проверки
        :returns boolean: возвращает boolean существования элемента
        """
        with allure.step(f'Проверка существования текста {text}'):
            try:
                locator = self.page.get_by_text(text=text).last
                self.check_visibility(locator=locator)
                return True
            except:
                return False

    def check_iframe_exists_text(self, frame_selector, text):
        """
        Метод проверки существавания текста
        :param frame_selector: селектор iframe
        :param text: текст проверки
        :returns boolean: возвращает boolean существования элемента
        """
        with allure.step(f'Проверка существования текста {text}'):
            try:
                locator = self.page.frame_locator(frame_selector).get_by_text(text=text).last
                self.check_visibility(locator=locator)
                return True
            except:
                return False

    def check_content_input(self, locator: Locator, name='', text: str = '', **kwargs):
        """
        Метод проверки значения инпута (value).
        """
        with allure.step(f'Проверка текста в инпуте {name}'):
            expect(locator).to_have_value(text, **kwargs)

    def check_css_style(self, locator: Locator, name='', css_style: str = '', css_value: str = '', **kwargs):
        """
        Метод проверки CSS свойства у элемента.
        """
        with allure.step(f'Проверка css стиля {name}'):
            expect(locator).to_have_css(name=css_style, value=css_value, **kwargs)

    def check_hidden(self, locator, name):
        """
        Метод проверки видимости элемента
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        """
        with allure.step(f'Проверка скрытия элемента {name}'):
            expect(locator).to_be_hidden()

    def check_current_url(self, url):
        """
        Метод проверки url
        :param url: url для проверки
        """
        with allure.step(f'Проверка url {url}'):
            expect(self.page).to_have_url(url)
