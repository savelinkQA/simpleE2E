import os
import re

import argparse

parser = argparse.ArgumentParser(description='Simple parser custom argument')
parser.add_argument('--output', type=str, default='available_steps')
args = parser.parse_args()
output = args.output


def getData():
    dir = os.path.dirname(os.path.abspath(__file__)) + r"/features/steps"
    results = []
    for filename in os.listdir(dir):
        if filename.endswith('.py'):  # Фильтруем только .py файлы
            file_path = os.path.join(dir, filename)

            # Открываем файл и читаем его содержимое
            with open(file_path, 'r', encoding='utf-8') as file:
                file_content = file.read()

                # Ищем все функции, помеченные декораторами @when/@given/@then
                # в любом регистре (when/When, given/Given, then/Then).
                pattern = r'@(?i:(when|given|then))\(["\'](.*?)["\']\)'
                matches = re.findall(pattern, file_content)

                item = {"name_file": filename}
                # Добавляем найденные шаги в результат
                steps = []
                for match in matches:
                    step_type, step_text = match
                    step_type = step_type.lower()
                    is_param = "{" in step_text and "}" in step_text  # Проверяем наличие фигурных скобок
                    tmp = {
                        "type": step_type,
                        "text": step_text,
                        "is_param": is_param
                    }
                    steps.append(tmp)
                item["steps"] = steps
                results.append(item)
    return results


def generate_html_from_results(results, ):
    # Открываем файл для записи
    with open(output + "/index.html", "w", encoding="utf-8") as html_file:
        # Начало HTML-документа
        html_file.write('<!DOCTYPE html>\n')
        html_file.write('<html lang="en">\n')
        html_file.write('<head>\n')
        html_file.write('    <meta charset="UTF-8">\n')
        html_file.write('    <title>Доступные шаги тестов</title>\n')
        html_file.write('    <style>\n')
        html_file.write('        table {\n')
        html_file.write('            border-collapse: collapse;\n')
        html_file.write('            width: 50%;\n')
        html_file.write('            margin: auto;\n')
        html_file.write('        }\n')
        html_file.write('\n')
        html_file.write('        th, td {\n')
        html_file.write('            border: 1px solid black;\n')
        html_file.write('            padding: 8px;\n')
        html_file.write('            text-align: left;\n')
        html_file.write('        }\n')
        html_file.write('\n')
        html_file.write('        th {\n')
        html_file.write('            background-color: #f2f2f2;\n')
        html_file.write('        }\n')
        html_file.write('\n')
        html_file.write('        h1 {\n')
        html_file.write('            text-align: center;\n')
        html_file.write('        }\n')
        html_file.write('\n')
        html_file.write('        h2 {\n')
        html_file.write('            font-size: 1.2em;\n')
        html_file.write('        }\n')
        html_file.write('    </style>\n')
        html_file.write('</head>\n')
        html_file.write('<body>\n')
        html_file.write('    <h1>Доступные шаги тестов</h1>\n')

        # Вставляем данные из results
        for item in results:
            html_file.write(f'    <h1>{item["name_file"]}</h2>\n')
            html_file.write('    <table>\n')
            html_file.write('        <tr>\n')
            html_file.write('            <th>Тип шага</th>\n')
            html_file.write('            <th>Текст шага</th>\n')
            html_file.write('            <th>Наличие параметров</th>\n')
            html_file.write('        </tr>\n')

            for step in item["steps"]:
                html_file.write('        <tr>\n')
                html_file.write(f'            <td>{step["type"]}</td>\n')
                html_file.write(f'            <td>{step["text"]}</td>\n')
                html_file.write(f'            <td>{step["is_param"]}</td>\n')
                html_file.write('        </tr>\n')

            html_file.write('    </table>\n')

        # Завершаем HTML-документ
        html_file.write('</body>\n')
        html_file.write('</html>\n')


results = getData()
generate_html_from_results(results)
