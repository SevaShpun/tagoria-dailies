"""
Tagoria Dailies Completer
Автоматизация ежедневных заданий в игре Tagoria
"""

import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from selenium.webdriver.firefox.service import Service
from splinter import Browser

# ============================================================================
# КОНФИГУРАЦИЯ БРАУЗЕРА
# ============================================================================

def get_browser_config() -> tuple[bool, bool]:
    """Запрашивает у пользователя настройки браузера."""
    
    def get_yes_no_input(prompt: str) -> bool:
        while True:
            answer = input(prompt).strip().upper()
            if answer in ('Y', 'YES'):
                return True
            elif answer in ('N', 'NO'):
                return False
            print("❌ Неверный ввод. Пожалуйста, введите Y или N.")
    
    use_snap = get_yes_no_input("🦊 Firefox установлен через Snap? (Ubuntu/Kubuntu) [Y/N]: ")
    use_extensions = get_yes_no_input("🔌 Использовать расширения Firefox? (требуется ublock_origin.xpi, noscript.xpi) [Y/N]: ")
    
    return use_snap, use_extensions


def initialize_browser(use_snap: bool, use_extensions: bool) -> Browser:
    """Инициализирует браузер с указанными настройками."""
    
    extensions = ['ublock_origin.xpi', 'noscript.xpi', 'fastproxy.xpi']
    capabilities = {'acceptInsecureCerts': True}
    
    browser_kwargs = {'capabilities': capabilities}
    
    if use_snap:
        browser_kwargs['service'] = Service(executable_path='/snap/bin/geckodriver')
        print('[✅] Используется Firefox, установленный через Snap.')
    
    if use_extensions:
        browser_kwargs['extensions'] = extensions
        print('[✅] Используется Firefox с расширениями.')
    
    print('[*] Загрузка браузера...')
    # 🔧 Ключевое исправление: браузер указывается первым позиционным аргументом
    browser = Browser('firefox', **browser_kwargs)
    time.sleep(3)
    return browser


# ============================================================================
# ГЛОБАЛЬНОЕ СОСТОЯНИЕ (лучше вынести в класс, но сохраняем логику)
# ============================================================================

class GameState:
    """Хранит состояние игры для избежания глобальных переменных."""
    
    def __init__(self, config: dict):
        self.username: str = config['USERNAME']
        self.password: str = config['PASSWORD']
        self.world: str = config['WORLD']
        self.amber_max: int = config['AMBER_MAX']
        
        # Прогресс
        self.days: int = 0
        self.new_day: bool = True
        self.quest_complete: bool = False
        
        # Ресурсы
        self.action_points: int = 6
        self.quest_points: int = 3
        self.skill_points: int = 0
        self.amber: int = 1
        
        # Квесты
        self.quest_location: str = f'/mountains/overview/zone/?w={self.world}&thiszone=5'
        
        # Прокачка характеристик
        self.stat_rotation: int = 1  # 1-4: STR/DEX/AGI/STA, сбрасывается
        self.stat_epoch: int = 0     # Счётчик циклов для ACC


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def wait_until(hours: int, minutes: int, seconds: int) -> None:
    """
    Приостанавливает выполнение до указанного времени.
    
    ИСПРАВЛЕНИЕ: убран некорректный вызов datetime.replace()
    """
    target_time = datetime.now() + timedelta(hours=hours, minutes=minutes, seconds=seconds)
    print(f'[*] Ожидание до: {target_time.strftime("%H:%M:%S")}')
    
    while True:
        remaining = (target_time - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        # Адаптивный сон для точности без нагрузки на CPU
        if remaining <= 0.1:
            time.sleep(0.001)
        elif remaining <= 0.5:
            time.sleep(0.01)
        elif remaining <= 1.5:
            time.sleep(0.1)
        else:
            time.sleep(1)


def safe_get_element_text(browser: Browser, css_selector: str, xpath: str) -> Optional[int]:
    """Безопасное получение числового значения из элемента."""
    try:
        if browser.is_element_present_by_css(css_selector):
            element = browser.find_by_xpath(xpath).first
            # ИСПРАВЛЕНИЕ: извлекаем всё число, а не последний символ
            import re
            match = re.search(r'\d+', element.text)
            return int(match.group()) if match else None
    except Exception:
        pass
    return None


# ============================================================================
# ИГРОВЫЕ ДЕЙСТВИЯ
# ============================================================================

def login(browser: Browser, state: GameState) -> bool:
    """Выполняет вход в игру, если пользователь не авторизован."""
    try:
        if browser.links.find_by_partial_href('/auth/loginform/'):
            print('[*] Выполняется вход...')
            browser.find_by_id('menuLink1').first.click()
            browser.find_by_name('world').select(state.world)
            browser.fill('username', state.username)
            browser.fill('password', state.password)
            browser.find_by_name('LABEL_LOGIN').click()
            time.sleep(6)
            return True
    except Exception as e:
        print(f'[⚠️] Ошибка при входе: {e}')
    return False


def collect_wages(browser: Browser) -> None:
    """Собирает зарплату с фермы, если доступна."""
    try:
        if (browser.is_element_present_by_id('leftNewsLink') and 
            browser.is_element_present_by_xpath("//*[contains(@href,'/town/farm/')]")):
            browser.find_by_id('leftNewsLink').click()
            browser.find_by_name('ACTION_COLLECT_WAGE').click()
            print('[✅] Зарплата с фермы получена.')
        else:
            print('[ℹ️] Зарплата ещё не доступна.')
    except Exception as e:
        print(f'[⚠️] Ошибка при сборе зарплаты: {e}')


def work_at_farm(browser: Browser, state: GameState) -> None:
    """Выполняет работу на ферме (3 цикла по 8 часов)."""
    print('[*] Переход на ферму...')
    browser.find_by_id('menuLink4').click()  # Village
    time.sleep(3)
    browser.find_by_id('menuLink14').click()  # Farm
    time.sleep(2)
    
    for work_cycle in range(1, 4):
        print(f'[*] Работа: цикл {work_cycle}/3 (8 часов)')
        browser.find_by_name('workHoursSelectList').select('8')
        browser.find_by_name('ACTION_BEGIN_WORK').click()
        
        # Случайная задержка для имитации человека
        time.sleep(random.randint(10, 21))
        
        print('[*] Выход из системы для "сна"...')
        browser.find_by_id('menuLink10').click()  # Logout
        
        # Имитация сна: 8 часов + случайные минуты/секунды
        print('[*] 💤 Сплю...')
        wait_until(8, random.randint(3, 6), random.randint(3, 52))
        
        print("[*] ☀️ Проснулся! Забираю награду...")
        login(browser, state)
        collect_wages(browser)
        print(f'[*] Отработано циклов: {work_cycle}/3')
    
    # Обновление состояния после дня
    state.days += 1
    state.new_day = True
    state.action_points = 6
    state.quest_points = 3
    print(f'[🌄] День {state.days}: легенда продолжается!')


def get_quest_location(browser: Browser, world: str) -> str:
    """Определяет локацию квеста и возвращает соответствующий URL."""
    location_map = {
        'valley': 1, 'river': 2, 'ruins': 3,
        'mine': 4, 'canyon': 5, 'volcano': 6
    }
    
    default_location = f'/mountains/overview/zone/?w={world}&thiszone=5'
    
    try:
        if browser.find_by_css('.mission_table'):
            location_text = browser.find_by_css('.mission_table').last.text.lower()
            for keyword, zone_id in location_map.items():
                if keyword in location_text:
                    print(f'[*] Локация квеста: {keyword.capitalize()}')
                    return f'/mountains/overview/zone/?w={world}&thiszone={zone_id}'
    except Exception:
        pass
    
    print('[*] Локация не определена, использую Canyon по умолчанию.')
    return default_location


def handle_quest(browser: Browser, state: GameState) -> None:
    """Управление квестами: сдача, получение, определение локации."""
    print('[*] Посещение друида...')
    browser.find_by_id('menuLink4').click()  # Village
    time.sleep(3)
    browser.find_by_id('menuLink11').click()  # Druid
    time.sleep(3)
    try:
        browser.find_by_id('druid_mission').click()
    except:
        print('Походу задание еще выполняется...')
    time.sleep(3)
    
    # Сдача завершённого квеста
    try:
        if browser.is_element_present_by_xpath("//*[contains(@id,'btn_complete_')]"):
            browser.find_by_xpath("//*[contains(@id,'btn_complete_')]").click()
            print('[✅] Квест сдан.')
            time.sleep(3)
            browser.find_by_id('druid_mission').click()
            state.quest_complete = False
        else:
            print('[ℹ️] Нет квеста для сдачи.')
    except Exception:
        pass
    
    # Проверка активного квеста
    if browser.is_element_present_by_id('btn_abandon'):
        print('[ℹ️] Квест уже активен.')
    
    # Обновление очков квестов из UI
    actual_qp = safe_get_element_text(
        browser, 
        '.mission_table2',
        '//*[@class="mission_table2"]/tbody/tr/th[text()="Quest points: "]/b'
    )
    if actual_qp is not None:
        state.quest_points = actual_qp
        print(f'[*] Очки квестов: {state.quest_points}')
    
    # Принятие нового квеста (если доступен)
    try:
        accept_link = browser.links.find_by_partial_href('/town/druid/accept/')
        if accept_link:
            print('[✅] Принят новый квест.')
            accept_link.click()
            time.sleep(3)
            state.quest_complete = False
    except Exception:
        pass
    
    # Проверка доступных очков действия
    if state.action_points == 0:
        state.new_day = False
        print('[ℹ️] Нет очков действия.')
        return
    if state.quest_points == 0:
        print('[ℹ️] Нет очков квестов.')
    
    # Определение и сохранение локации квеста
    state.quest_location = get_quest_location(browser, state.world)
    
    # Переход к выполнению
    plunder(browser, state)


def plunder(browser: Browser, state: GameState) -> None:
    """Выполнение квеста или грабежа до исчерпания очков действия."""
    try:
        browser.find_by_id('menuLink5').click()  # Mountains
        browser.links.find_by_href(state.quest_location).click()
        state.quest_complete = False
        
        while state.action_points > 0 and not state.quest_complete:
            # Определение доступного действия
            action = None
            if browser.is_element_present_by_name('MISSION_BUTTON'):
                action = 'MISSION_BUTTON'
                print('[*] Попытка выполнения квеста...')
            elif browser.is_element_present_by_name('EXPLORATION_BUTTON'):
                action = 'EXPLORATION_BUTTON'
                print('[*] Попытка исследования...')
            elif browser.is_element_present_by_name('PLUNDER_BUTTON'):
                action = 'PLUNDER_BUTTON'
                print('[*] Грабёж...')
            
            if not action:
                print('[⚠️] Нет доступных действий.')
                break
            
            # Выполнение действия
            browser.find_by_name(action).click()
            print('[*] ⚔️ Бой...')
            wait_until(0, 10, random.randint(25, 45))
            
            # Проверка результата боя
            if browser.is_text_present(f'Winner: {state.username}'):
                print('[✅] Победа!')
            else:
                print('[❌] Поражение.')
            print('-' * 20)
            
            # Проверка завершения квеста
            if (browser.is_text_present('Well done! You have accomplished your task.') or 
                browser.is_text_present('You have successfully explored the region.')):
                print('[✅] Квест завершён!')
                state.quest_complete = True
                time.sleep(9)
            else:
                # Возврат к локации для повторной попытки
                browser.links.find_by_href(state.quest_location).click()
            
            # Проверка повышения уровня
            check_level_up(browser)
            
            # Проверка порога янтаря для прокачки
            current_amber = get_amber(browser)
            if current_amber > state.amber_max:
                manage_skills(browser, state)
                # Возврат к локации после прокачки
                browser.find_by_id('menuLink5').click()
                browser.links.find_by_href(state.quest_location).click()
                
            # Обновление очков действия после каждого действия
            update_action_points(browser, state)
            
    except Exception as e:
        print(f'[⚠️] Ошибка при выполнении квеста: {e}')


def check_level_up(browser: Browser) -> None:
    """Проверяет и забирает награду за повышение уровня."""
    try:
        if (browser.is_element_present_by_id('leftNewsLink') and 
            browser.links.find_by_partial_href('/char/attributes/levelup/')):
            print('[*] 🎁 Получение награды за уровень...')
            browser.find_by_id('leftNewsLink').click()
            link = browser.links.find_by_partial_href('/char/attributes/levelup/')
            if link:
                link.click()
            time.sleep(9)
    except Exception:
        pass


def get_amber(browser: Browser) -> int:
    """Получает текущее количество янтаря."""
    try:
        if browser.find_by_id('spMoney'):
            text = browser.find_by_id('spMoney').first.text
            return int(''.join(filter(str.isdigit, text)))
    except Exception:
        pass
    return 0


def get_skill_points(browser: Browser) -> int:
    """Получает доступные очки навыков."""
    try:
        if browser.find_by_css('.skillreset_table'):
            xpath = '//*[@class="skillreset_table"]/tbody/tr/th'
            element = browser.find_by_xpath(xpath).first
            # ИСПРАВЛЕНИЕ: извлекаем число, а не последний символ
            import re
            match = re.search(r'\d+', element.text)
            return int(match.group()) if match else 0
    except Exception:
        pass
    return 0


def update_action_points(browser: Browser, state: GameState) -> None:
    """Обновляет значение очков действия из интерфейса."""
    actual_ap = safe_get_element_text(
        browser,
        '.buy_action_point_table',
        '//*[@class="buy_action_point_table"]/tbody/tr/td/b'
    )
    if actual_ap is not None:
        state.action_points = actual_ap
        print(f'[*] Очки действия: {state.action_points}')


def buy_skill_points(browser: Browser, state: GameState) -> int:
    """Покупает очки навыков, пока янтарь выше порога."""
    bought = 0
    print(f'[*] 💎 Янтарь: {get_amber(browser)} / {state.amber_max}')
    
    if get_amber(browser) <= state.amber_max:
        print('[ℹ️] Янтарь ниже порога, покупка не требуется.')
        return 0
    
    print('[*] Покупка очков навыков...')
    try:
        while get_amber(browser) > state.amber_max:
            browser.find_by_name('BUY_SKILL').first.click()
            bought += 1
            time.sleep(3)
        print(f'[✅] Куплено очков: {bought}')
        print(f'[*] 💎 Янтарь: {get_amber(browser)} / {state.amber_max}')
    except Exception as e:
        print(f'[⚠️] Ошибка при покупке навыков: {e}')
    
    return bought


def allocate_skill_points(browser: Browser, state: GameState) -> None:
    """Распределяет очки навыков по характеристикам в заданном порядке."""
    xpaths = {
        'STR': "//*[contains(@action,'/char/attributes/skillstr/')]",
        'DEX': "//*[contains(@action,'/char/attributes/skilldex/')]",
        'AGI': "//*[contains(@action,'/char/attributes/skillagi/')]",
        'STA': "//*[contains(@action,'/char/attributes/skillcst/')]",
        'ACC': "//*[contains(@action,'/char/attributes/skillacc/')]"
    }
    
    # Переход к экрану характеристик
    try:
        if browser.find_by_id('menuLink0'):
            browser.find_by_id('menuLink0').click()
        time.sleep(2)
    except Exception:
        return
    
    # Покупка очков навыков при необходимости
    bought = buy_skill_points(browser, state)
    state.skill_points = get_skill_points(browser)
    print(f'[*] Доступно очков навыков: {state.skill_points}')
    
    if state.skill_points == 0:
        return
    
    print('[*] 📈 Прокачка характеристик...')
    
    # Распределение очков по ротации
    while state.skill_points > 0:
        try:
            # Каждые 6 циклов добавляем точность
            if state.stat_epoch >= 6:
                if browser.is_element_present_by_xpath(xpaths['ACC']):
                    browser.find_by_xpath(xpaths['ACC']).click()
                    print('  → +Accuracy')
                    state.stat_epoch = 0
                    state.skill_points = get_skill_points(browser)
                time.sleep(3)
                continue
            
            # Основная ротация: STR → DEX → AGI → STA
            stat_order = [
                (1, 'STR', xpaths['STR']),
                (2, 'DEX', xpaths['DEX']),
                (3, 'AGI', xpaths['AGI']),
                (4, 'STA', xpaths['STA'])
            ]
            
            for next_rotation, stat_name, xpath in stat_order:
                if state.stat_rotation == next_rotation:
                    if browser.is_element_present_by_xpath(xpath):
                        browser.find_by_xpath(xpath).click()
                        print(f'  → +{stat_name}')
                        state.skill_points = get_skill_points(browser)
                        # Обновление счётчиков
                        if next_rotation == 4:
                            state.stat_rotation = 1
                            state.stat_epoch += 1
                        else:
                            state.stat_rotation = next_rotation + 1
                    time.sleep(3)
                    break
            else:
                # Защита от зацикливания
                break
                
        except Exception as e:
            print(f'[⚠️] Ошибка при прокачке: {e}')
            break


def manage_skills(browser: Browser, state: GameState) -> None:
    """Управление навыками: покупка и распределение очков."""
    allocate_skill_points(browser, state)


# ============================================================================
# ОСНОВНОЙ ЦИКЛ
# ============================================================================

def main():
    """Точка входа в программу."""
    print('--~={| 🎮 Tagoria Dailies Completer |}=~--\n')
    
    # Настройка браузера
    use_snap, use_extensions = get_browser_config()
    browser = initialize_browser(use_snap, use_extensions)
    
    # Загрузка конфигурации
    config_path = Path('config.yml')
    if not config_path.exists():
        print(f'[❌] Файл конфигурации {config_path} не найден!')
        browser.quit()
        return
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f'[❌] Ошибка чтения конфигурации: {e}')
        browser.quit()
        return
    
    # Инициализация состояния
    state = GameState(config)
    
    # Запуск игры
    print('[*] Подключение к Tagoria...')
    browser.visit('https://www.tagoria.net/?lang=en')
    time.sleep(5)
    
    try:
        while True:
            login(browser, state)
            collect_wages(browser)
            
            # Цикл квестов в течение дня
            while state.new_day and state.action_points > 0:
                handle_quest(browser, state)
            
            # Работа на ферме (завершает день)
            if not state.new_day:
                work_at_farm(browser, state)
                
    except KeyboardInterrupt:
        print('\n[⚠️] Прервано пользователем.')
    except Exception as e:
        print(f'\n[❌] Критическая ошибка: {e}')
    finally:
        print('[*] Завершение работы...')
        browser.quit()


if __name__ == '__main__':
    main()
