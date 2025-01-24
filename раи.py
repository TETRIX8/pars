import os
import sys

def main():
    if len(sys.argv) != 2:
        print("Использование: python3 run_parser.py START:END")
        print("Где START и END - номера начальной и конечной страницы.")
        sys.exit(1)

    pages = sys.argv[1]
    try:
        start_page, end_page = map(int, pages.split(":"))
        if start_page > end_page or start_page <= 0:
            raise ValueError
    except ValueError:
        print("Ошибка: Неверный формат диапазона страниц. Используйте START:END (например, 1:5).")
        sys.exit(1)

    # Формируем команду для запуска основного файла
    command = f"nohup python3 akparser.py {pages} > output.log &"
    print(f"Запуск парсинга страниц {start_page} по {end_page} в фоне...")
    print(f"Логи работы будут сохранены в 'output.log'.")

    # Выполняем команду
    os.system(command)
    print("Процесс запущен.")

if __name__ == "__main__":
    main()