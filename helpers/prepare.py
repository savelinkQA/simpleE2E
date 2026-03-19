import allure
import time
from allure_commons.types import AttachmentType
import random
import re
import json

global_selector_for_iframe = '[data-test-id="extension-adapter-frame"]'


def get_prefics():
    return "Autotest"


def get_long_name(count=255):
    Name = "eiaqtzuejxpyyhzvsttqjvcxangombokndqwlfcghvkxydkmzkhixfrnbyluvvhenxhnwrjntimpulkcanjqdtzxbavlfeioetqcjumvaktyaumudrgalweswrdinmqvknxbhkhjftkcgeausaljlvatyvionsxrcyzyzrvuhiswoosfnpsfrwypkjfplullyikvrntdnrldvausgsicovdwawrpnessxjhatymswoqrngfczekqkbgmzhsrhuczkekkanodzglgkkpbmlnorpbdipcceuacivqhfwsijlhpmupgpdjcpgsaklahaouvuawehjbaypgqksqzmbnt"
    return Name[0:count]


def prepare_text(text):
    """
    Метод преобразования текста
    :param text: текст для преобразования
    :return text: текст после преобразования
    Преобразует ключевые слова в текст
    Возможные ключевые слова: random, longName\((\d+)\)
    """
    if "random" in text:
        tmp = get_prefics() + str(time.time_ns()) + str(random.randint(10000, 99000))
        text = text.replace('random', tmp)
    if "longName" in text:
        pattern = r"longName\((\d+)\)"
        match = re.search(pattern, text)
        if match:
            count_symbol = int(match.group(1))
            text = text.replace(f'longName({count_symbol})', get_long_name(count_symbol))
    return text


def allure_attach_png(path, name):
    with open(path, "rb") as image:
        f = image.read()
        b = bytearray(f)
        allure.attach(b, name=name, attachment_type=AttachmentType.PNG)


def is_json_request(content):
    try:
        content = json.loads(content.decode('utf-8'))
    except:
        content = "No json content"
    return content


def is_json_response(content):
    try:
        content = content.json()
    except:
        content = "No json content"
    return content


def pretty_json_content(content):
    try:
        content = json.dumps(content, ensure_ascii=False, indent=4)
    except:
        content = "No json content"
    return content


def func_allure_req(response):
    request = {}
    request["method"] = str(response.request.method)
    request["url"] = str(response.request.url)
    request["path_url"] = str(response.request.path_url)
    request["0"] = "================================================="
    request["headers"] = dict(response.request.headers)
    request["1"] = "================================================="
    request["Body"] = "no body"
    if response.request.body is not None:
        request["Body"] = is_json_request(response.request.body)
    request = pretty_json_content(request)
    allure.attach(request, name=f'{response.request.method}_request.json', attachment_type=AttachmentType.JSON)

    response_result = {}
    response_result["status"] = str(response.status_code)
    response_result["0"] = "================================================="
    response_result["headers"] = dict(response.headers)
    response_result["1"] = "================================================="
    response_result["body"] = is_json_response(response)

    response_result = pretty_json_content(response_result)
    allure.attach(response_result, name=f'{response.request.method}_response.json',
                  attachment_type=AttachmentType.JSON)
