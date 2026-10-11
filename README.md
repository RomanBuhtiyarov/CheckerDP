# CheckerDP

Скрипт мониторит электронную очередь паспортного сервиса «ДП Документ» в Берлине
(<https://berlin.pasport.org.ua/solutions/e-queue>) и присылает уведомление в Telegram,
когда на сайте появляются свободные места.

## Как это работает

Раз в `CHECK_INTERVAL` (по умолчанию 10 минут) скрипт:

1. Открывает сайт в Chrome через `undetected_chromedriver` (проходит проверку Cloudflare).
2. Выбирает услугу «Закордонний паспорт та (або) ID-картка» (`SERVICE_VALUE = "4"`).
3. Ждёт результат до 40 секунд:
   - появилось сообщение «всі місця зайняті» → мест нет, тихий звуковой сигнал;
   - в списке дат (`#date`) появились варианты → **есть места**: громкий сигнал,
     скриншот `slots_found.png` и сообщение в Telegram;
   - не дождался ни того, ни другого → предупреждение в логе, уведомление **не** отправляется;
     скриншот и текст страницы сохраняются в `unknown_result.png` и `unknown_result.txt`
     для диагностики.

## Требования

- Windows (используется `winsound`)
- Python 3.12
- Google Chrome, установленный в `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Telegram-бот (токен от @BotFather) и ID чата для уведомлений

## Установка

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Настройка

Скопируйте `.env.example` в `.env` и заполните:

```
TELEGRAM_TOKEN=токен_бота
TELEGRAM_CHAT_ID=id_чата
```

Переменные можно задать и в окружении, они имеют приоритет над `.env`.
Файл `.env` в git не попадает, не коммитьте токен.

Остальные параметры (`URL`, `CHECK_INTERVAL`, `SERVICE_VALUE`, `NO_SLOTS_KEYWORDS`)
находятся в начале `new_update.py`.

## Запуск

```powershell
.venv\Scripts\python.exe new_update.py
```

Остановка: `Ctrl+C`. Не запускайте две копии одновременно, иначе уведомления будут дублироваться.

## Возможные проблемы

- **`session not created: This version of ChromeDriver only supports Chrome version X`**:
  версию драйвера скрипт подбирает сам по установленному Chrome. Если ошибка осталась,
  проверьте путь к `chrome.exe` в `create_driver()`.
- **«Не вдалося визначити результат після вибору послуги»**: сайт не показал ожидаемого
  результата за 40 секунд. Посмотрите `unknown_result.png` и `unknown_result.txt`;
  возможно, изменился текст сообщения (`NO_SLOTS_KEYWORDS`) или сайт ответил ошибкой.
- **Уведомления в Telegram не приходят**: проверьте `TELEGRAM_TOKEN` и `TELEGRAM_CHAT_ID`
  в `.env`, а также что бот добавлен в чат.

## Файлы

| Файл | Назначение |
| --- | --- |
| `new_update.py` | основной скрипт мониторинга |
| `main.py` | шаблон PyCharm, не используется |
| `requirements.txt` | зависимости |
| `.env.example` | шаблон настроек Telegram |
