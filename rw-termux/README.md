# rw-termux — скачивалка билетов БЧ для Android

Одно нажатие на виджет → активные билеты скачиваются в папку Downloads.

## Как работает

1. Запускается локальный HTTP-сервер на порту 8765
2. Открывается браузер с формой логина
3. После входа скрипт обращается к мобильному API БЧ (`apicast.rw.by`)
4. Скачивает все активные билеты и объединяет в один PDF
5. Сохраняет файл в `/sdcard/Download/tickets_YYYY-MM-DD.pdf`
6. Завершает работу

JWT-токен кешируется в `~/.rw-ticket.conf` и живёт ~10 дней — повторные запуски не требуют ввода логина.

## Установка

**1. Установи [Termux](https://f-droid.org/packages/com.termux/) из F-Droid**

**2. Перекинь файлы на телефон** (`rw-ticket.py` и `setup.sh`) — через Telegram, почту и т.д.

**3. В Termux:**
```bash
termux-setup-storage
cp ~/storage/downloads/rw-ticket.py ~/
cp ~/storage/downloads/setup.sh ~/
bash ~/setup.sh
```

**4. Установи [Termux:Widget](https://f-droid.org/packages/com.termux.widget/) из F-Droid**, добавь виджет на рабочий стол и выбери скрипт `rw-ticket.sh`.

**5. Разреши Termux показывать поверх других приложений:**
Настройки → Приложения → Termux → Другие разрешения → Всегда сверху → Включить

## Зависимости

```
requests
PyPDF2
```

Устанавливаются автоматически через `setup.sh`.

## API

Скрипт использует мобильный API `apicast.rw.by` — тот же, что использует официальное приложение БЧ. Все запросы делаются от имени Android-клиента (`okhttp/4.9.0`).

`user_key` — захардкоженный ключ из APK приложения `by.rw.client`, идентифицирует клиента на сервере.

---

### 1. Авторизация

`POST https://apicast.rw.by/v1/rwauth`

Тело — form-encoded (не JSON).

```bash
curl -X POST https://apicast.rw.by/v1/rwauth \
  -H "User-Agent: okhttp/4.9.0" \
  -H "Accept: application/json" \
  -d "login=your@email.com" \
  -d "password=yourpassword" \
  -d "user_key=c0f1de1cbcf6c517baa7c95ab7d0509e" \
  -d "device_token=" \
  -d "refresh_token=false"
```

Ответ:
```json
{
  "status": 200,
  "auth": {
    "jwt": "eyJhbGciOiJSUzI1NiJ9..."
  },
  "user": { ... }
}
```

JWT живёт ~10 дней. Кешируется в `~/.rw-ticket.conf`.

---

### 2. Список активных заказов

`GET https://apicast.rw.by/v1/unnumbered/orders`

```bash
curl "https://apicast.rw.by/v1/unnumbered/orders?user_key=c0f1de1cbcf6c517baa7c95ab7d0509e&orderType=UPCOMING" \
  -H "User-Agent: okhttp/4.9.0" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9..."
```

Параметры:
- `orderType` — `UPCOMING` (активные) или `PAST` (прошлые)

Ответ:
```json
[
  {
    "id": 15612244,
    "ticketId": 14369842,
    "etsNum": "17162398",
    "departureDate": "2026-06-17",
    "depStationCode": "2100001",
    "arrStationCode": "2100865",
    ...
  }
]
```

Поля `id` и `ticketId` используются для скачивания PDF.

---

### 3. Скачивание билета (PDF)

`GET https://apicast.rw.by/v1/unnumbered/orders/{id}/tickets/{ticketId}.pdf`

```bash
curl "https://apicast.rw.by/v1/unnumbered/orders/15612244/tickets/14369842.pdf?user_key=c0f1de1cbcf6c517baa7c95ab7d0509e" \
  -H "User-Agent: okhttp/4.9.0" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9..." \
  -o ticket.pdf
```

Возвращает PDF-файл (~40 KB).

---

## Примечание

Работает стабильно на мобильных данных. Некоторые Wi-Fi сети могут блокировать запросы к белорусским серверам — в таком случае переключись на мобильный интернет.
