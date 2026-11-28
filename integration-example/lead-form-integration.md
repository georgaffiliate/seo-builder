# Форма зворотного звʼязку (lead form) — інструкція з підключення

Цей документ описує, як підключити нашу форму заявки на **свій** сайт: що скопіювати, що
заповнити, як виглядає контракт форми й API, і як перевірити, що все працює.

Комплект, який передається:

```
integration-example/   ← усе, що потрібно; всередині:
                         ├── lead-form.js        клієнтський скрипт форми
                         ├── thanks-example.php  приклад сторінки «дякуємо»
                         └── integration/        серверна частина (api.php, config.php, lib/)
thanks-example.php     ← (дубль у корені пакета, якщо передаєте не папкою)
```

---

## 1. Що всередині папки `integration-example/`

Саме цю папку ви отримуєте (не «api») — назва збережена як у нашій фабриці. PHP-файли
лежать у вкладеній папці `integration/`:

```
integration-example/
├── lead-form.js          ← клієнтський скрипт форми (КОПІЮВАТИ В КОРІНЬ САЙТУ)
├── thanks-example.php    ← приклад «дякуємо» (перейменувати в thanks.php)
└── integration/          ← оце і є серверна частина, яку треба розмістити
    ├── api.php           ← приймає заявку (POST JSON), відправляє в CRM і Telegram
    ├── config.php        ← ВСІ налаштування (CRM, Telegram, buyer, країна/мова/воронка)
    ├── thx.php           ← хелпер для сторінки «дякуємо» (autologin-редірект)
    ├── job_status.php    ← не потрібен (api.php синхронний); можна не використовувати
    ├── header.php        ← пікселі в <head>, потрібен лише якщо вмикаєте Keitaro/FB
    ├── header_pageview.php ← те саме, окремий випадок
    ├── footer.php        ← підключає intl-tel-input + lead-form.js
    └── lib/
        ├── crm.php       ← формування payload і відправка в CRM  ← НЕ РЕДАГУВАТИ aff_sub11
        ├── telegram.php  ← повідомлення в Telegram
        ├── crm-bu.php    ← альтернативний CRM-бекенд (якщо у вас інший)
        ├── crm-tb.php    ← альтернативний CRM-бекенд
        ├── buyers.php    ← мапа buyer → токени/чати
        ├── frod.php      ← антифрод (перевірка заявки)
        ├── frod-bu.php   ← антифрод для альтернативного бекенду
        ├── keitaro.php   ← оновлення sub_id у Keitaro (опційно)
        └── jobs.php      ← черга job-файлів (legacy, не потрібна)
```

Мінімум, який реально потрібен: `api.php`, `config.php`, `lib/crm.php`, `lib/telegram.php`,
`lib/buyers.php`, `lib/frod.php`.

### Куди класти

Найпростіше:

1. **`lead-form.js`** із пакета → у **корінь сайту** (поруч з `index.php`). Без нього форма
   не валідує поля й не відправляє нічого — це найчастіша причина «скрипта форми бракує».
2. **`integration-example/integration`** → перейменувати в **`api_local/integration`** у корені
   сайту:

```
public_html/
├── index.php
├── thanks.php
├── lead-form.js            ← скрипт форми (лежить у корені)
└── api_local/
    └── integration/        ← вміст integration-example/integration/
        ├── api.php
        ├── config.php
        └── lib/…
```

Тоді `action` форми — `api_local/integration/api.php`, і `footer.php` знаходить
`lead-form.js` штатно (`__DIR__ . '/../../lead-form.js'`).

Якщо структуру міняти не хочете (папка лишається `integration-example/integration/`):
1) у формі вкажіть `action="integration-example/integration/api.php"`;
2) у `footer.php` поправте шлях `__DIR__ . '/../../lead-form.js'` на фактичний
   (скрипт має лежати в корені сайту або поруч).

---

## 2. Заповніть `config.php`

Файл повертає масив; обовʼязкові поля:

| ключ | що це | приклад |
|---|---|---|
| `crm_api_url` | endpoint CRM | `https://yourleads.org/api/affiliates/v2/leads` |
| `fixed_api_key` | ключ CRM (може перекриватися `buyers[KEY].crm_token`) | `a91aa258-…` |
| `tg_bot_token` | токен Telegram-бота для сповіщень | `8374261466:AAE…` |
| `country` | ISO2 країни | `SK` |
| `lang` | код мови | `sk` |
| `funnel` | токен воронки, CAPS, без гео й TLD | `MAJETDVOR` |
| `domain` | `''` = брати реальний хост; інакше — фіксований домен | `''` |
| `buyer` | покупець трафіку | `PUMA` |
| `buyers` | мапа buyer → `crm_token`, `chat_id`, `chat_team_id`, `show_crm_log` | див. приклад у файлі |
| `default_buyer` | fallback, якщо `buyer` не з мапи | `PUMA` |
| `autologin_redirect` | редірект на `auto_login_url` з CRM на сторінці «дякуємо» | `true` |
| `job_polling` | залишити `false` (api синхронний) | `false` |
| `keitaro` | `true`, якщо треба оновлювати sub_id у Keitaro | `false` |

Важливо: **`country`, `lang`, `funnel`, `buyer` задаються тільки тут**, на сервері.
У HTML їх рендерити не потрібно (див. §6).

---

## 3. HTML-контракт форми

Мінімальний робочий приклад (класи — обовʼязкові, це селектори скрипта):

```html
<form class="lead-form" action="api_local/integration/api.php" method="post" novalidate>
  <h3>Заявка</h3>

  <div class="form-group">
    <label for="lf-first">Імʼя
      <input id="lf-first" name="first_name" required autocomplete="given-name" placeholder="Jana">
    </label>
    <div class="form-error" role="alert"></div>
  </div>

  <div class="form-group">
    <label for="lf-last">Прізвище
      <input id="lf-last" name="last_name" required autocomplete="family-name" placeholder="Nováková">
    </label>
    <div class="form-error" role="alert"></div>
  </div>

  <div class="form-group">
    <label for="lf-email">Email
      <input id="lf-email" name="email" type="email" required autocomplete="email" placeholder="jana@email.com">
    </label>
    <div class="form-error" role="alert"></div>
  </div>

  <div class="form-group">
    <label for="lf-phone">Телефон
      <!-- ВАЖЛИВО: у поля НЕМАЄ name — його підставляє intl-tel-input -->
      <input id="lf-phone" type="tel" required autocomplete="tel" class="js-lead-phone" placeholder="+421 900 000 000">
    </label>
    <div class="form-error" role="alert"></div>
  </div>

  <button class="blk-btn form-submit" type="submit">Надіслати <span>↗</span></button>

  <small class="form-consent">
    Надсилаючи, ви погоджуєтесь на обробку даних згідно з політикою конфіденційності.
  </small>

  <p class="form-status" role="status" aria-live="polite"
     data-msg-sending="Надсилаємо…"
     data-msg-fix="Перевірте виділені поля."
     data-msg-fail="Не вдалося надіслати, спробуйте ще раз."
     data-msg-ok="Готово, перенаправляємо…"></p>
</form>
```

Обовʼязкові елементи:

| елемент | навіщо |
|---|---|
| `form.lead-form` | корінь, до нього чіпляється обробник |
| `input[name="first_name"]`, `input[name="last_name"]`, `input[name="email"]` | валідація + дані заявки |
| `input.js-lead-phone` **без `name`** | поле телефону; номер у E.164 пише intl-tel-input у прихований `input[name="phone"]` |
| `.form-submit` | кнопка; на час відправки блокується |
| `.form-error` (по одному під полем) | куди писати помилку поля |
| `.form-status` з `data-msg-*` | статуси («надсилаємо», «перевірте поля», «помилка», «ок») |
| `small.form-consent` | дисклеймер/згода; суму депозиту (якщо є) — тільки тут і в `<small>` |

Додатково можна лишати `input[name="phone"]` прихованим вручну — скрипт його синхронізує.

---

## 4. Підключення скриптів

У кінці `<body>`:

```html
<!-- перевірте, що файл реально доступний: GET /lead-form.js → 200 -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.15/css/intlTelInput.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.15/js/intlTelInput.min.js"></script>

<script src="/lead-form.js?v=1"
        data-country="SK"
        data-thanks="./thanks.php"
        data-poll="false"
        data-tsid="{ts_id}"></script>
```

Атрибути `lead-form.js`:

| атрибут | значення | що робить |
|---|---|---|
| `data-country` | `SK` або `auto` | початкова країна в телефонному полі; `auto` — визначення за IP (ipapi.co) |
| `data-thanks` | `./thanks.php` | куди редіректити після успішної заявки |
| `data-poll` | `false` | залишити `false` (api синхронний) |
| `data-tsid` | `{ts_id}` або ваш id | прокидається в URL «дякуємо» як `ts_id` (для партнерських пікселів) |

Якщо CDN заборонений — покладіть `intlTelInput.min.js`/`.css` локально; без бібліотеки
форма не провалідує телефон і покаже повідомлення «Телефон не завантажився».

Мову повідомлень скрипт бере з `<html lang="…">` (є словники для `cs, sk, hu, pl, de, nl,
it, es, fr, pt, ro, en`, інакше — англійська).

---

## 5. Серверні вимоги

- PHP **7.4+** (перевірено на 8.x), розширення `curl` (без нього частина відправок піде
  через `file_get_contents`, але повільно й менш надійно);
- вхідний трафік має бути **на тому ж домені**, що й форма (CORS у `api.php` не налаштований);
- права: `api.php` має читати `config.php` і писати нічого не повинен (синхронний режим);
- HTTPS обовʼязковий;
- якщо хостинг — наша панель: `.htaccess` вона ігнорує, тому не покладайтесь на нього
  (див. §8).

---

## 6. API-контракт

### Запит

`POST api_local/integration/api.php`, `Content-Type: application/json`:

```json
{
  "post":    { "first_name": "Jana", "last_name": "Nováková",
               "email": "jana@email.com", "phone": "+421900123456" },
  "session": { "_subid": "…", "utm_source": "…" },
  "server":  { "ua": "Mozilla/5.0 …", "lang": "sk-SK" },
  "rawclick": { "utm_source": "…", "pixel": "…" }
}
```

`post` збирається з полів форми (`lead-form.js` відправляє все, що має `name`).
`session`, `server`, `rawclick` — необовʼязкові, але корисні для атрибуції й антифроду.

### Відповідь

```json
{
  "ok": true,
  "crm_ok": true,
  "crm_http_code": 200,
  "crm_response": { "auto_login_url": "https://…" },
  "fire_lead_pixel": true
}
```

| поле | значення |
|---|---|
| `ok` | запит прийнято (навіть якщо CRM відмовив) |
| `crm_ok` | чи CRM прийняв лід |
| `crm_response` | відповідь CRM; `auto_login_url` використовується для редіректу на «дякуємо» |
| `fire_lead_pixel` | чи можна палити піксель ліда |
| `blocked: true` | антифрод заблокував лід (CRM не викликали) |

Помилки: `400 {"ok":false,"error":"empty_body"}` — порожнє тіло.

### Приклад перевірки без браузера

```bash
curl -s -X POST https://your-site.tld/api_local/integration/api.php \
  -H 'Content-Type: application/json' \
  -d '{"post":{"first_name":"Test","last_name":"Lead","email":"test@example.com","phone":"+421900123456"}}'
```

Очікувано: JSON з `"ok": true` (і `crm_ok` залежно від CRM).

---

## 7. Сторінка «дякуємо» та постбек

`thanks.php` (якщо використовуєте нашу панель): **перший рядок файлу**

```php
<?php require _postback.php; send_postback();
```

- `_postback.php` генерує панель і перезаписує після кожного апдейту — **не редагувати**;
- `send_postback()` фіксує лід у панелі; на сторонньому хостингу файлу немає — `api.php`
  це перевіряє й просто пропускає крок;
- якщо вмикати `autologin_redirect`, після заявки користувача редіректить на
  `auto_login_url` з CRM через `data-thanks` + `thx.php`.

Опційно: `job_status.php` і `job_polling` — legacy, для синхронного API не потрібні.

---

## 8. Каверзи хостингу (перевірено на практиці)

1. **Cloudflare / панель ламає plain-email.** Будь-який `mailto:` або текст `info@domain` у
   HTML перетворюється на «[email protected]» і веде в 404. Тому контакти на сторінці
   збираються JS-ом: `<a class="js-mail" data-u="info" data-d="domain.tld" href="#"></a>`.
2. **`.htaccess` панель відкидає** — не робіть на нього ставку.
3. **Кеш ассетів**: `lead-form.js` підключайте з `?v=<mtime або хеш>`, інакше правки
   не доїжджають (кеш 30 днів).
4. **Панель може перегенеровувати sitemap без `.php`** — якщо у вас ЧПУ, тримайте
   canonical із `.php` і 301-переадресацію (у наших сайтах це робить PHP-guard).
5. **intl-tel-input з CDN** може бути заблокований у деяких регіонах/корп-мережах —
   тоді телефон не валідується, форма покаже «телефон не завантажився».
6. `aff_sub11 = 'google.com'` у `lib/crm.php` — **не змінювати**: це вимога CRM, реальний
   домен іде тільки в Telegram.

---

## 9. Анти-фінгерпринт (важливо)

- Не рендеріть у HTML приховані поля з `country/lang/funnel/buyer/domain` — вони беруться
  з `config.php` на сервері. Інакше всі сайти мережі видно за однаковим блоком hidden-полів.
- Не дублюйте `aff_sub*` у розмітці.
- `phone` не має мати `name` на видимому полі (його ставить intl-tel-input) — інакше
  браузер відправить два різні формати номера.

---

## 10. Чекліст приймання

- [ ] `POST` на `api.php` з curl повертає `{"ok":true}`
- [ ] у браузері форма: порожні поля → червоні підсвітки + «перевірте поля»
- [ ] невалідний email → помилка біля поля
- [ ] телефон: вибір країни працює, номер стає E.164 (`+421…`)
- [ ] успішна заявка → редірект на `thanks.php`
- [ ] лід зʼявився в CRM; у Telegram прийшло повідомлення (якщо ввімкнено)
- [ ] повторний submit не створює дубль (кнопка блокується)
- [ ] на сторінці «дякуємо» перший рядок — `send_postback()` (якщо панель)
- [ ] на мобільному (390 px) поля не вилазять за екран, телефон відкриває цифрову клавіатуру

---

## 11. Траблшутинг

| симптом | причина | що робити |
|---|---|---|
| `{"ok":false,"error":"empty_body"}` | запит без JSON-тіла | перевірте `Content-Type` і `JSON.stringify` |
| форма «висить» на «надсилаємо…» | 500/404 на `api.php` | відкрийте шлях у браузері, гляньте `error_log` PHP |
| `crm_ok:false` | CRM відмовив/таймаут | перевірте `crm_api_url`, ключ, коди в `lib/crm.php` |
| телефон «не завантажився» | intl-tel-input не підвантажився | локальна копія бібліотеки |
| повідомлення англійською | у `<html>` немає `lang` або мови немає у словнику | додайте `lang="sk"` тощо |
| у Telegram немає ліда | не заповнений `tg_bot_token` або `chat_id` у `buyers` | перевірте config, права бота в чаті |
| email на сторінці — «[email protected]» | Cloudflare Email Obfuscation | контакти тільки через `class="js-mail"` |
| після деплою стара форма | кеш `lead-form.js` | додайте `?v=` з mtime |
| «клієнтського скрипта форми бракує», сторінка просто перезавантажується | `lead-form.js` не покладено в корінь або шлях у `<script src>` хибний (404) | покладіть файл у корінь і перевірте `/lead-form.js` у Network → 200 |

---

## 12. Що НЕ входить у комплект

- стилі форми (`blocks.css`) — форма працює без них, класи лише для вашого CSS;
- сторінки сайту, sitemap, іконки;
- Keitaro/FB-пікселі — вмикаються у `config.php` (`header_pixels`, `keitaro`) і вимагають
  `header.php`/`footer.php` з папки `integration-example/`.
