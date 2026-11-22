# CLAUDE.md — static-create-sites (автономна фабрика статичних сайтів)

> Це САМОДОСТАТНІЙ продукт. Ти працюєш ЛИШЕ всередині цієї папки (`Documents/seo-sites/static-create-sites`).
> Батьківська папка `seo-sites/` — окремий legacy-проєкт: не читай його доки, не пиши в його `sites/`,
> не запускай його скрипти. Тут усе своє.

## Вхідна точка

Людина заходить у цю папку і пише кілька коротких рядків:

```
IT
Pheira Voltreksc
pheira-voltreksc.site
```

Розшифровка: UPPERCASE-2 = код країни → довгі рядки = бренд (як є) → рядки з TLD = домени (1..10).
≥2 домени = режим MULTI (окремий план/контент на кожен; тексти сиблінгів <20% перетину).

**Авто-рішення (не питати людину):** мова/локаль і регулятор — з `resources/regulators.json`
(нема країни → визнач сам і допиши туди); місто — столиця; депозит — €250-еквівалент у валюті
(тільки `<small>` під кнопкою); buyer=`PUMA`; funnel — найдовший токен бренду CAPS
(`Pheira Voltreksc`→`VOLTREKSC`); logo — перше слово lowercase; контакти — правдоподібні локальні,
у сиблінгів різні (інша вулиця/номер телефону).

## Пайплайн (2 команди; LLM пише ТІЛЬКИ контент-JSON, не HTML!)

```bash
# 0. Прочитати ЛИШЕ: content/content-pack.schema.json (схема контенту). Понад ~6 KB документів — ні.

# 1. План + КОНТЕНТ + збірка + гейти + іконки + перевірки + профіль — однією командою:
python3 gen_plan.py --brand "Pheira Voltreksc" --lang it --domain pheira-voltreksc.site --build
#   план    → plans/<domain>.json (палітра × скін × hero × порядок × віджети × слуги × меню ×
#             числа × персони+фото × регулятор; валідатор упав → --seed +1)
#   контент → content/<domain>-content.json. Маршрути (обирає gen_plan):
#             · за замовчуванням — ЛЛМ ПИШЕ КОНТЕНТ САМА з брифу мовою плану (унікальність кожної
#               збірки); програма валідує структуру/числа/депозит/персон і робить repair-пас
#             · --translate → англійський майстер-пак (--source-lang en) + tools/localize.py
#               (модель лише переписує рядки; дешевше, структура гарантована програмою)
#             · --offline (тести/без ключа) → resources/content-l10n.json (точні рядки банку)
#             якщо модельний пак не пройшов repair — автоматичний фолбек на --translate
#             депозит лише bands.form_consent; наявний контент не перетирає, якщо не --force
#             (можна покласти свій/LLM-пак і він піде в збірку)
#   далі    → sites/<domain>/ (9 сторінок, інтеграція, sitemap/robots/htaccess) + gates
#             tools/seo_audit.py (0 err) + tools/twin_check.py (унікальність)
#   іконки  → favicon.svg/.ico/.png + apple-touch-icon.png + og-image.png з палітри бренду
#   гейти   → node --check усіх JS + tools/mobile_lint.py (viewport/tbl-scroll/inline grid)
#   профіль → profiles/<domain>.json (+ взаємні siblings)
# ALL GREEN = готово (WARN по дублях не ламає GREEN); інакше exit≠0.

# Варіант з LLM-контентом (унікальні тексти, персони й числа обирає модель):
python3 gen_plan.py --brand "Pheira Voltreksc" --lang it --domain pheira-voltreksc.site --with-llm
#   → content/<domain>-brief.json (верстка+слоти+схема+шортлист персон+бінди чисел)
#   → модель пише content/<domain>-content.json, програма валідує, при помилках 1 repair-пас,
#     далі автоматично: assemble + гейти + іконки + перевірки + профіль
#   → вибрані моделлю персони/фото/числа записуються в план (без перетину з історією, в межах біндів)
#   → якщо модель не дала валідний пак — fallback на мовний банк, сайт усе одно збереться
#   транспорт: HTTP до resources/llm.json (ключ VENICE_API_KEY у .llm_env або env);
#   без ключа — opencode CLI ≥2 як запасний. Модель: --llm-model, транспорт: --llm-provider
#   точні id моделей: python3 tools/llm_content.py --list-models

# 2. Ручний мобільний огляд (єдине, що машина не ловить):
#    прогнати 360/390/768 px у браузері — 0 горт. скролу, нічого не обрізано
#    (hero/таблиці/калькулятор/форма). Далі — деплой.
```

Окремі кроки (коли треба руками):
```bash
python3 tools/content_gen.py --plan plans/<domain>.json --force      # перегенерувати контент
python3 assemble.py --plan plans/<domain>.json                        # тільки збірка + гейти
python3 tools/brand_icons.py --plan plans/<domain>.json --site sites/<domain>
python3 tools/mobile_lint.py sites/<domain>
python3 tools/profile_write.py --plan plans/<domain>.json --content content/<domain>-content.json
```


## Деплой (один раз наприкінці, для кожного домену)

```bash
curl -s "https://florentina-tr.shop/api/v1/stores?q=<domain>" \
     -H "Authorization: Bearer $(grep PANEL_API_KEY ../../.panel_api_key | cut -d= -f2)"   # → store id
zip -rq /tmp/<domain>.zip sites/<domain> -x "*.DS_Store"
curl -s -X POST "https://florentina-tr.shop/api/v1/stores/<id>/zip" \
     -H "Authorization: Bearer <KEY>" -F "file=@/tmp/<domain>.zip"
```
- `can_upload:true` обовʼязково; `.htaccess` панель відкидає — це норм (власний 404 через 404.php).
- **Прод не тестувати** (submit = лід у CRM). Перевірка — curl GET-статуси сторінок (200/404).
- IP-whitelist/DNS — напом'янути у звіті.

## Структурна різноманітність (обовʼязково, гейти не пропустять однакові сайти)
- Кожен `<section>` несе `class="… sec sec-<type>"` (+ `data-var="b|c"` у варіантах): skeleton читається з `sec-*`, а не з `blk-*`.
- `.sec` — лише маркер: НЕ задає `display` (інакше пізніше правило вбиває grid/flex кореня секції);
  layout-властивості живуть на класі-компоненті (`.faq-flex`, `.blk-hero`, `.blk-band`), selftest 2c це ловить.
- `gen_plan.py` сам тримає дистанцію: inventory vs сусіди <0.65, vs старі плани <0.72, ≥2 нових типи секцій,
  унікальний набір слагів/меню/inner-skeleton, ≥25% слотів з іншим варіантом; у плані зʼявляються
  `layout.variants` + `structure.*` — не видаляти, не «оптимізувати».
- **Ротація екранів:** тільки `hero` і form-band фіксовані як типи; якірні екрани
  (`people/faq/numbers/cta/office/compare`) — опціональні, план бере 2–3 і НЕ повторює якорі
  попереднього плану та сиблінгів того ж бренду (спільних якорів ≤1; fillers сиблінга теж під баном).
- **Форма не привʼязана до 2-го екрана:** позиція ротується (35% одразу після hero, 65% — на 2–4 екрани
  глибше); варіанти form-band b/c/d/e (d — форма-first із ledger-точками, e — центрована картка з chips).
  Контракт форми (`lead-form`, `js-lead-phone`, consent-депозит) незмінний в усіх варіантах.
- **Персони — через ЛЛМ:** для будь-якого ГЕО модель придумує імена/міста/ролі/стаж (поле `g`: f|m
  звіряється з фото; імена з історії не повторюються). `NAME_BANK` — лише style-reference/fallback;
  банки імен під кожне ГЕО не створюємо. Бін латентності тепер теж враховує історію (не повторює сусідів).
- **Контент-гейти:** `profile_write.py` пише в профіль `content_fp` (фінгерпринти секцій) + `personas`;
  `twin_check.py` падає, якщо fp-Jaccard ≥45% проти будь-якого профілю або ≥2 позиційні збіги
  місто/стаж у відгуках сиблінгів.
- **Аудит-гейти проти живих дефектів (seo_audit):** FAQPage ⊆ видимі питання; один абзац не може
  повторюватись на сторінці; бренд не злипається з попереднім словом («oBrand»); підписи
  numbers-смуги — слова, не цифри; жодного plain-text email/mailto в HTML (панель/CF робить із
  нього битий лінк — контакти лише через `class="js-mail"` + `app.js`); кожен URL зі sitemap
  мусить мати вхідний лінк (сирота = ERR). Контакти (email/phone) нормалізуються під домен і
  країну плану — модельні не приймаються; меню/футер беруть підписи з title самої сторінки,
  реєстраційна сторінка лінкується з футера.
- Калькулятор — це варіант віджета G3 (`calculator`), окремої секції в пулі немає: секція
  з'являється лише коли G3 випав калькулятор; примус — `--calculator on|off`.
- Хедер — вісь (`layout.variants.header`): 10 розкладок (лого зліва/справа/по центру, без лого,
  без CTA, дворівневий, компактний з меню-кнопкою, лого по центру + навігація під ним, навігація
  пігулками, лого справа); лого-марка — окрема вісь `logo` (8 марок).
- Футер — окрема вісь `layout.variants.footer` (5 структур: 3-ярусний, бренд + дві колонки,
  центрований стек, split-сітмап, мінімальний рядок). Оболонка = header × footer = 10×5 = 50
  комбінацій; `pick_variant` тримає шапку/футер подалі від 5 попередніх планів, а `validate()`
  валить план, якщо комбо повторює один із трьох попередніх.
- Стрічка в хедері (`livebar`) — окрема вісь поза `section_order`; у пул ідуть лише СТРУКТУРНО
  різні стрічки: `a` маркі-тейп, `f` новини, `j` центрований тейп, `k` ledger-тейп, `m` рядки,
  `n` метри (label+bar), `t` борд (3×2, без анімації), `z` тейп зі спарклайнами, `ac` статичні
  чіпи (свайп, без руху). Решта старих id (b–y) лишаються рендерябельними для історії, але не
  обираються: вони відрізнялись лише рамкою/кольором. Вибір у плані (`layout.variants.livebar`) +
  дані в `plan.livebar.subs`, assemble рендерить їх.
- `SECTION_POOL` ×22 типи (`device` виведений з пулу — він дублював hero-мокап; `VARIANTS` ×21 слот). Стат-екрани
  не дублюють значення hero: `numbers` = rating/5·reviews·orders/s·API, `stats-intro` = reviews·orders·API
  (labels з `sections.stats`), `glance` = власні `sections.glance` + rows з markets; numbers і stats-intro
  взаємовиключні в одному плані. Додаєш тип → додай фрагмент `blk-<type>.html` і (для слотів з варіантами)
  по файлу на кожен варіант, інакше `assemble.py` впаде на валідації.
- Новий варіант = інша структура (rail/таблиця/чips/рядки/акордеон), не інший колір. Контракт форми/калькулятора зберігати.
- `twin_check.py` падає на: однаковий inventory/variant-map/slug-set, ≥72% inventory, positional ≥60% проти 2+ планів,
  class-Jaccard ≥85%, widget-superset, **content-fp ≥45% проти профілю, шаблон відгуків сиблінга (місто/стаж)**.
  `tests/selftest.py` перевіряє, що клон справді ловиться.

## Жорсткі правила
- `h1 .brand-line` + бренд-first `<title>` + 1 h1/сторінка — audit ловить.
- Контракт форми/інтеграції незмінний: `form.lead-form`, `js-lead-phone` без name,
  base-поля (country/lang/funnel/domain/buyer) інжектить server-side `api.php` з `config.php`
  (у HTML їх НІКОЛИ не рендеримо — анти-фінгерпринт),
  `crm.php aff_sub11='google.com'` НЕ чіпати (Telegram бере реальний хост).
- 0 inline `<script>`; 0 кириличних коментарів у ship-файлах; числа без обіцянок.
- Мова: контент пише ЛЛМ сама (це і є унікальність); програма перевіряє структуру, числа,
  депозит, персон і не дає зшити клон (відгуки — 3 різні люди, мокап сходиться). `--translate` —
  англійська майстер-копія + переклад (структура від програми). `--offline` — банк (тести, без ключа).
  Поруч із `localize` банк лишається майстром англійської та фікстуром.
- Hero-мокап (ledger/device) — ілюстрація, а не вигадані цифри: рядки додаються до балансу
  в шапці, підпис без «sample data». Текст пише ЛЛМ (brief rules у `tools/llm_content.py`),
  програма лише перевіряє, що модель не забула: `ledger_errors` → repair-пас → локальний
  `content_gen.reconcile_ledger` (тільки арифметика) → fallback на банк; `seo_audit` —
  остання сітка на зібраних сторінках. Банк (`hero.device_note`) — лише fallback.
- `thanks.php` рядок 1 = `require _postback.php; send_postback();`; serve-js (`calculator.js`/
  `app.js`/`widgets.js`) — присутні в корені, підключені в footer-партіалі.
- Ассети (blocks.css/skin.css/app.js/calculator.js/lead-form.js) підключаються з `?v=` (хеш збірки
  або mtime): прод кешує CSS на 30 днів, без мітки правки не доїжджають.
- Після будь-якої правки JS: `node --check` (одна регулярка ламала форму на сиблінгах).
- Широкі таблиці — одразу у `.tbl-scroll`; жодних inline `grid-template-columns` на контейнерах.
- Мобільне меню: якщо варіант хедера задає власний `display` для `.blk-nav`, він мусить мати
  пару в `@media(max-width:700px)` — `.blk-nav{display:none}` + `.blk-nav.open{display:flex}`.
  Інакше специфічність десктопного правила перебиває базове «сховано», і бургер не закриває меню
  (реальний баг варіанта `i`).
- Self-check після змін інфраструктури: `python3 tests/selftest.py` (має бути PASSED).
- Canonical-URL гігієна: sitemap/canonical/внутрішні лінки — тільки з `.php`; кожен контент-файл
  починається з PHP-canonical-guard (`PHP_CANON_GUARD` в assemble.py): GET/HEAD на URL без `.php`
  → 301 на `.php` (панель віддає extensionless з 200 і перегенеровує sitemap без `.php`).
  Guard не ставиться на thanks.php (рядок 1 = postback) та 404.php (мʼякі 404 не мають 301-ити).
  seo_audit ловить non-.php locs у sitemap та canonical-и поза sitemap.

## Структура продукту
```
gen_plan.py             планувальник (seed-детермінований, валідує проти plans/*) + --build ланцюжок
tools/content_gen.py    контент-пак з resources/content-l10n.json (мова гео, seed-варіації)
tools/llm_content.py    LLM-пак: бриф → модель пише JSON → валідація + repair + запис персон/чисел
tools/brand_icons.py    favicon/og з палітри плану (rsvg-convert + PIL)
tools/mobile_lint.py    статичний мобільний гейт (viewport/tbl-scroll/inline grid)
tools/profile_write.py  реєстрація profiles/<domain>.json + взаємні siblings
resources/content-l10n.json  мовні банки текстів (it/cs/en; решта → en fallback)
assemble.py             конструктор: plan(+content) → sites/<domain> + gates
tools/seo_audit.py      SEO/форма/помилки gate (порт сам обирає)
tools/twin_check.py     анти-близнюк gate: inventory/порядок/варіанти/слаги/класи (проти plans/*);
                        ПОЛІТИКА ДУБЛІВ: twin_check і повтор комбо палітра×скін = WARN у лозі,
                        а не блок збірки (валідатор контенту лишается жорстким)
blocks/blocks.css       єдина geometric-мова (responsive, 700/1000)
blocks/blk-*.html       канонічні фрагменти + варіанти blk-<slot>-b/-c ({{PLACEHOLDER}}, {{c:path}})
skins/ ×6               geometric character (радиуси/тіні/щільність/типографіка)
content/                схеми контенту + палітри × шрифти
people/ ×183            банк аватарок (ніколи не повторюються між планами)
integr.-example/        канон інтеграції (config плейсхолдери, crm.php канонічний)
plans/ plans/*.json     історія планів (вхід twin_check; не видаляти)
sites/                  вихід assembler'а
tests/selftest.py       самоперевірка інфраструктури (54 перевірки + e2e)
```

## Звіт (мовою людини)
Таблиця: домен / палітра / скін / hero / віджети / депозит / контакти / слуги.
Матриця відмінностей сиблінгів + вихід гейтів. Вручну: DNS, IP-whitelist, мобільний огляд.
Нагадування: прод не тестували.
