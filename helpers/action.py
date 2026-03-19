import allure
from playwright.sync_api import Locator


class ClassAction:
    def __init__(self, context):
        self.page = context.page

    def visit(self, url, **kwargs):
        """
        Метод перехода по сслыке
        :param url: адрес перехода
        :param kwargs: опции метода goto()
        """
        with allure.step(f'Переход по url={url}'):
            self.page.goto(url, **kwargs)

    def click(self, locator: Locator, name='', **kwargs):
        """
        Метод клика по элементу
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода click()
        """
        with allure.step(f'Клик по кнопке {name}'):
            locator.click(**kwargs)

    def click_last_button(self, locator: Locator, name='', **kwargs):
        """
        Метод клика по элементу
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода click()
        """
        with allure.step(f'Клик по последней кнопке {name}'):
            locator.last.click(**kwargs)

    def dblclick(self, locator: Locator, name='', **kwargs):
        """
        Метод двойного клика по элементу
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода dblclick()
        """
        with allure.step(f'Двойной клик по кнопке {name}'):
            locator.dblclick(**kwargs)

    def hover(self, locator: Locator, name='', **kwargs):
        """
        Метод ховера на элемент
        :param locator: локатор элемента
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода hover()
        """
        with allure.step(f'Ховер на элемент {name}'):
            locator.hover(**kwargs)

    def mouse_click_coordinate(self, page, coordinate, **kwargs):
        """
        Метод ховера на элемент
        :param page: контекст playwright
        :param name: имя действия. Только для allure
        :param coordinate: координата для клика
        """
        with allure.step(f'Клик мышкой по координатам ({str(coordinate)})'):
            page.mouse.click(coordinate["x"], coordinate["y"], **kwargs)

    def mouse_click_move(self, page, coordinate_start, coordinate_end, **kwargs):
        """
        Метод ховера на элемент
        :param page: контекст playwright
        :param name: имя действия. Только для allure
        :param coordinate_start: координата 1ого клика
        :param coordinate_end: координата отпускания мыши
        """
        with allure.step(f'Клик мышкой и потянуть по координатам ({str(coordinate_start)}) до {str(coordinate_end)}'):
            page.mouse.move(coordinate_start["x"], coordinate_start["y"])
            page.mouse.down()
            page.mouse.move(coordinate_end["x"], coordinate_end["y"])
            page.mouse.up()

    def press(self, key: str, **kwargs):
        """
        Метод нажатия кноп(ки/ок) с клавиатуры
        :param key: указатель кноп(ки/ок), документация по доступным значениям
        https://playwright.dev/python/docs/api/class-keyboard#keyboard-press
        :param kwargs: опции метода press()
        """
        with allure.step(f'Нажатие кнопки {key}'):
            self.page.keyboard.press(key=key, **kwargs)

    def fill(self, locator: Locator, text: str, name='', **kwargs):
        """
        Метод введения текста
        :param locator: локатор элемента
        :param text: вводимый текст
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода fill()
        """
        with allure.step(f'Ввод текста {text} в поле {name}'):
            locator.fill(value=text, **kwargs)

    def fill_on_dialog_text(self, selector_dialog, selector, text: str, name=''):
        """
        Метод клика по тексту
        :param selector_dialog: селектор диалогового окна
        :param selector: селектор элемента внутри диалогового окна
        :param text: текст для ввода
        :param name: имя элемента. Только для allure
        """
        with allure.step(f'Ввожу {text} в диалоговом окне {name}'):
            locator = self.page.locator(selector=selector_dialog).locator(selector)
            locator.fill(value=text)

    def hover_on_text(self, text):
        """
        Метод наведения курсора по тексту
        :param text: текст на который нужно навести
        """
        with allure.step(f'Наведение курсора на текст {text}'):
            locator = self.page.get_by_text(text=text).last
            self.hover(locator=locator)

    def click_on_text(self, text):
        """
        Метод клика по тексту
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Клик по тексту {text}'):
            locator = self.page.get_by_text(text=text).last
            self.click(locator=locator)

    def db_click_on_text(self, text):
        """
        Метод двойного клика по тексту
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Двойной клик по тексту {text}'):
            locator = self.page.get_by_text(text=text).last
            self.dblclick(locator=locator)

    def click_iframe_on_text(self, frame_selector, text):
        """
        Метод клика по тексту в iframe
        :param frame_selector: селектор iframe
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Клик в iframe по тексту {text}'):
            locator = self.page.frame_locator(frame_selector).get_by_text(text=text).last
            self.click(locator=locator)

    def db_click_iframe_on_text(self, frame_selector, text):
        """
        Метод двойного клика по тексту в iframe
        :param frame_selector: селектор iframe
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Двойной клик в iframe по тексту {text}'):
            locator = self.page.frame_locator(frame_selector).get_by_text(text=text).last
            self.dblclick(locator=locator)

    def hover_iframe_on_text(self, frame_selector, text):
        """
        Метод наведения курсора по тексту
        :param frame_selector: селектор iframe
        :param text: текст на который нужно навести
        """
        with allure.step(f'Наведение курсора на текст {text}'):
            locator = self.page.frame_locator(frame_selector).get_by_text(text=text).last
            self.hover(locator=locator)

    def rigth_click_on_text(self, text):
        """
        Метод клика правой кнопкой по тексту
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Клик ПКМ по тексту {text}'):
            locator = self.page.get_by_text(text=text).last
            self.click(locator=locator, button="right")

    def rigth_click_iframe_on_text(self, frame_selector, text):
        """
        Метод клика правой кнопкой по тексту iframe
        :param frame_selector: селектор iframe
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Клик ПКМ в iframe по тексту {text}'):
            locator = self.page.frame_locator(frame_selector).get_by_text(text=text).last
            self.click(locator=locator, button="right")

    def click_on_dialog_text(self, selector, text: str):
        """
        Метод клика по тексту
        :param selector: селектор диалогового окна
        :param text: текст по которому нужно кликнуть
        """
        with allure.step(f'Клик по тексту {text} в диалоговом окне'):
            locator = self.page.locator(selector=selector).get_by_text(text=text).last
            self.click(locator=locator)

    def scroll_to_element(self, locator: Locator, name='', **kwargs):
        with allure.step(f'Скролл до элемента {name}'):
            while locator.is_visible() is False:
                self.page.mouse.wheel(0, 100)

    def scroll_point(self, count, point, **kwargs):
        with allure.step(f'Скролл {count} раз по {point} точек'):
            for i in range(0, int(count)):
                self.page.mouse.wheel(0, int(point))

    def drag_and_drop(self, locator1: Locator, locator2: Locator, name='', **kwargs):
        """
        Метод клика по элементу
        :param locator1: локатор элемента откуда
        :param locator2: локатор элемента куда
        :param name: имя элемента. Только для allure
        :param kwargs: опции метода click()
        """
        with allure.step(f'drag_and_drop {name}'):
            locator1.drag_to(locator2)

    def upload_file_via_chooser(self, file_path: str, trigger_locator: Locator, name='Загрузка файла'):
        """
        Загрузка файла через FileChooser (диалог выбора файла).
        :param file_path: абсолютный путь к файлу
        :param trigger_locator: локатор кнопки, открывающей диалог выбора файла
        :param name: имя элемента для allure
        """
        with allure.step(f'{name}: {file_path}'):
            with self.page.expect_file_chooser() as fc_info:
                trigger_locator.click()
            file_chooser = fc_info.value
            file_chooser.set_files(file_path)