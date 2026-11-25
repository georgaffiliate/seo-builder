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
#   + --blog  → додає 3–5 статей з resources/blog-topics.json + teaser на головній.
#               Без --blog план/збірка байт-у-байт як раніше (блог-модуль не викликається).
#               Контент статей: tools/blog_content.py (один LLM-виклик) → content/<domain>-blog.json.
#               3 стилі (a|b|c) обирає план; header/footer/livebar/палітра — від основного сайту.
#               Усі блог-сторінки — у /blog/ (BLOG_DIR): головна /blog/index.php (BLOG_HUB),
#               статті /blog/<slug>.php; офферні сторінки лишаються в корені.
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
- **Hero — 5 композицій, без «трійки цифр»:** концепт у `HEROES` визначає фрагмент через
  `HERO_LETTER` (`variant`) — `d` заява (тип + 3 обіцянки), `e` доказ (мокап + відгук з іменем),
  `f` кроки 01/02/03, `g` компактна смуга, `h` картка відгуку. Доказ живе в `hero.proof`
  (claims×3 без цифр / quote / quote_by / steps×3), довжини тримає `proof_errors`, банк офлайну —
  `resources/hero-proof.json` (en/it/cs). Рейтинг/користувачі/латентність у hero більше НЕ
  рендеряться: їх показує смуга `numbers`, а `hero.stats` лишається каноном для `reconcile_numbers`.
  Концепт (`layout.hero`) і фрагмент (`layout.variants.hero`) тепер завжди збігаються — раніше
  7 концептів мапились у 3 фрагменти, тому всі hero виглядали однаково.
- **Форма не привʼязана до 2-го екрана:** позиція ротується (35% одразу після hero, 65% — на 2–4 екрани
  глибше); варіанти form-band b/c/d/e (d — форма-first із ledger-точками, e — центрована картка з chips).
  Контракт форми (`lead-form`, `js-lead-phone`, consent-депозит) незмінний в усіх варіантах.
- **Персони — через ЛЛМ:** для будь-якого ГЕО модель придумує імена/міста/ролі/стаж (поле `g`: f|m
  звіряється з фото; імена з історії не повторюються). `NAME_BANK` — лише style-reference/fallback;
  банки імен під кожне ГЕО не створюємо. Бін латентності тепер теж враховує історію (не повторює сусідів).
- **Контент-гейти:** `profile_write.py` пише в профіль `content_fp` (фінгерпринти секцій) + `personas`;
  `twin_check.py` падає, якщо fp-Jaccard ≥45% проти будь-якого профілю або ≥2 позиційні збіги
  місто/стаж у відгуках сиблінгів.
- **Скелет не несе мовних риб:** приклади з `content/content-pack.schema.json` — це заглушки
  («…» + українські підказки). `skeleton()` розмножує лише dict-шаблони, скалярні приклади стають
  порожніми слотами (раніше `units` перетворювались у «днів»×4), `_doc` не їде в пак, а
  `scrub_placeholders()` перед валідацією чистить значення-«тільки трикрапка». Перевірки
  `scarcity_errors()` (4 РІЗНІ підписи таймера, не заглушка) і `script_leaks()` (кирилиця в паку
  для не-кириличної мови = помилка) живуть і в `llm_content.validate()`, і в
  `assemble.validate_content()` — тобто валять саму збірку, яким би шляхом не йшов пак.
- **Аудит-гейти проти живих дефектів (seo_audit):** FAQPage ⊆ видимі питання; один абзац не може
  повторюватись на сторінці; бренд не злипається з попереднім словом («oBrand»); підписи
  numbers-смуги — слова, не цифри; жодного plain-text email/mailto в HTML (панель/CF робить із
  нього битий лінк — контакти лише через `class="js-mail"` + `app.js`); кожен URL зі sitemap
  мусить мати вхідний лінк (сирота = ERR); одна ціна на інструмент на сторінці (стрічка vs
  ticker/markets — інакше ERR). Контакти (email/phone) нормалізуються під домен і країну плану —
  модельні не приймаються; меню/футер беруть підписи з title самої сторінки, реєстраційна сторінка
  лінкується з футера. Числа звіряє `reconcile_numbers`: hero-stats — канон, стрічка/бенд/JSON-LD
  підганяються (orders/s — окрема метрика, не users//4). Гола трикрапка як заголовок/лід/кнопка =
  ERR («…» — це не копірайт); підписи таймера мусять бути РІЗНІ й у мові сторінки (ERR); кирилиця
  на не-кириличній сторінці — ERR, не WARN (живий баг ing-rendement.xyz: таймер з «днів»×4).
- Калькулятор — це варіант віджета G3 (`calculator`), окремої секції в пулі немає: секція
  з'являється лише коли G3 випав калькулятор; примус — `--calculator on|off`.
- Хедер — вісь (`layout.variants.header`): 12 розкладок (лого зліва/справа/по центру, без лого,
  без CTA, дворівневий, компактний з меню-кнопкою, лого по центру + навігація під ним, лого
  справа, `k` бренд зверху + дії другим рядком, `l` правий кластер меню→лінія→CTA, `m` док-
  навігація пігулкою). `b` (CTA опинявся посередині ряду) виведено з пулу — рендериться лише для
  історичних планів. Лого-марка — окрема вісь `logo` (8 марок).
- Футер — окрема вісь `layout.variants.footer` (5 структур: 3-ярусний, бренд + дві колонки,
  центрований стек, split-сітмап, мінімальний рядок). Оболонка = header × footer = 10×5 = 50
  комбінацій; `pick_variant` тримає шапку/футер подалі від 5 попередніх планів, а `validate()`
  валить план, якщо комбо повторює один із трьох попередніх.
- Стрічка в хедері (`livebar`) — окрема вісь поза `section_order`; у пул ідуть лише СТРУКТУРНО
  різні стрічки: `a` маркі-тейп, `f` новини, `j` центрований тейп, `k` ledger-тейп, `m` рядки,
  `n` метри (label+bar у рядок), `t` борд (шість клітинок у рядок, без анімації), `z` тейп зі
  спарклайнами, `ac` статичні чіпи (свайп, без руху), `ad` рядок-леджер (шість пар через
  волосяні лінії), `ae` лінійка (акцентна риска зверху, чотири цифри), `af` акорд-край (чорна
  смуга з акцентним корінцем). Решта старих id (b–y) лишаються рендерябельними для історії, але
  не обираються: вони відрізнялись лише рамкою/кольором. Вибір у плані
  (`layout.variants.livebar`) + дані в `plan.livebar.subs`, assemble рендерить їх.
- **Стрічка тонка — це закон, не смак:** вона стоїть над sticky-хедером, тому кожне сімейство
  (`n/t/m/w/u/x`) — ОДИН рядок (label + value + delta на одній базовій лінії, бар 2px під ними),
  висота 21–33px. Стовпчиковий борд/метри 3×2 з'їдали 157px першого екрана на jandervoq-it.xyz і
  виштовхували хедер із фолду. Клас сімейства L — `lb-ledger`, НЕ `ledger`: `ledger` — це картка
  hero-мокапа (padding 20px + border + shadow), і стрічка ловила її стилі (реальний баг 58px).
  Гейт: `preview/tops/build.py` рендерить усі 32 стрічки в справжньому оточенні й міряє висоту.
- **Перший екран = hero + форма:** `section_order` завжди ставить form-band на позицію 1, а
  `assemble.build_index` рендерить hero і band у спільному `.first-screen` (дві колонки на
  десктопі, стек на телефоні). Тому форма видно без скролу; hero-кнопку всередині цієї пари
  пригнічено CSS — дію виконує форма, а верхня CTA хедера лишається. На телефоні ховаються
  зайві hero-докази, щоб форма влізла у перший viewport.
- **Трастові логотипи під кожною формою:** усі form-фрагменти мають `.form-trust` з
  `{{TRUST_LOGOS}}`; `plan.trust_badges` (6 ключів) вибирає `gen_plan`, `assemble` підставляє
  SVG з банку `trust/` (Simple Icons, CC0) і копіює лише вибрані у `sites/<d>/img/trust/`.
  Підпис — `bands.trust_label` (локальний, 2–4 слова).
- **App-shot — обовʼязковий блок:** `appshot` (варіанти `a` картка / `b` реверс) показує реальне
  фото телефона з графіками; банк `appshots/` (20 фото Pexels License, `manifest.json`) ротується
  через `plan.appshot`, файл копіюється як `img/appshot.jpg`. Секція forced, як `guide`/`faq`.
- **Partner logo grid — обовʼязковий блок:** `partners` показує 8 карток з `trust/` (6 з форми +
  2 ротаційні, для сітки — окремий набір `plan.partner_badges`), 2 колонки на телефоні / 4 на десктопі.
  Секція forced; 5 верстк: `a` сітка, `b` стрічка, `c` split, `d` numbered rail, `e` темна панель.
  `{{PARTNER_GRID}}` збирає розмітку, `write_assets` копіює всі використані SVG.
- **FAQ — 5 верстк:** `a` split, `b` grid, `c` wide, `d` numbered rows, `e` two columns.
  `faq`/`partners`/`guide`/`appshot` ротуються явно по останніх 3 планах, включно з canonical.
- **Guide — 4 верстки:** `a` картки, `b` глосарій, `c` акордеон, `d` swipe-rail.
  **App-shot — 4 верстки:** `a` image/copy, `b` reverse, `c` photo-cover з overlay, `d` banner + 3 points.
  Для обох на телефоні окремі мобільні правила (rail/accordion/stack).
- **Довгі внутрішні сторінки:** `product`, `offer`, `faq` — окремі редакційні лендінги
  (`build_long_inner`): intro + TOC + 5 секцій (H2, 2 абзаци, 3 буліти) + FAQ + форма внизу.
  `content_gen.long_inner_pages()` збирає offline-версію з localized sections (450+/600+ слів),
  LLM пише `inner_product` / `inner_offer` / `inner_faq`; `assemble.validate_content` валить
  сторінку, якщо слів/секцій/FAQ менше норми. Сторінки додані в меню, футер, sitemap і JSON-LD
  (FAQPage для сторінок із `faq`).
- **First-screen композиції:** `layout.variants.first_screen` (`a` split, `b` centered, `c` form-left,
  `d` dark panel) ротуються разом із forced-блоками. `build_index` ставить `data-first` на
  `.first-screen`; форма/поля/consent не змінюються, змінюється лише композиція й трактування
  trust-логотипів (рядок, центр, верх картки, сітка).
- **Google/social preview:** `brand_icons.py` робить `og-image.jpg` 1200×630 з брендовою панеллю
  + реальним `img/appshot.jpg`; `page_shell` віддає `og-image.jpg`, `og:image:alt`, twitter:image
  і `robots: max-image-preview:large`; JSON-LD має `primaryImageOfPage`.
- **Мобільний partner-шар:** останній `@media(max-width:700px)` у `blocks.css` робить заголовки
  великими uppercase, form-band — кольоровою карткою з білими полями, статистику — картками,
  відгуки — swipe-стрічкою, кроки — плитками з номерами, FAQ — картками. Десктоп лишається
  редакційним; мобільний шар навмисно останній у каскаді.
- **Partner-палітри:** `gen_plan.PARTNER_PALETTES` = 4 світлі (`p-partner-blue`, `p-harbor-teal`,
  `p-arctic-slate`, `p-cloud-indigo`) + 4 темні (`p-partner-midnight`, `p-partner-graphite`,
  `p-partner-teal-night`, `p-partner-ink`). Пул перемішується `rng.shuffle`, тому тема
  світла/темна обирається випадково; скіни — `sharp-flat / classic-border / rounded-air`.
- `SECTION_POOL` ×25 типів (`device` виведений з пулу — він дублював hero-мокап; `VARIANTS` ×23 слоти). Стат-екрани
  не дублюють значення hero: `numbers` = rating/5·reviews·orders/s·API, `stats-intro` = reviews·orders·API
  (labels з `sections.stats`), `glance` = власні `sections.glance` + rows з markets; numbers і stats-intro
  взаємовиключні в одному плані. Додаєш тип → додай фрагмент `blk-<type>.html` і (для слотів з варіантами)
  по файлу на кожен варіант, інакше `assemble.py` впаде на валідації.
- **Довгий контент — обовʼязковий, не опційний якір:** кожен план несе `people`, `faq` (12 Q&A,
  відповідь 180+ символів) і `guide` (6 пояснень по 150+ символів; варіанти `a` картки / `b` глосарій).
  FAQ і `people` структурні: `rotating_anchors()` їх не рахує, тому ротація `numbers/cta/office/compare`
  лишається ≤1 спільного екрана між сусідами. Другий Q/A-екран (`compare`/`mini-faq`) не ставиться
  разом із `faq` — вони ділять `faq.items`.
- Новий варіант = інша структура (rail/таблиця/чips/рядки/акордеон), не інший колір. Контракт форми/калькулятора зберігати.
- `twin_check.py` падає на: однаковий inventory/variant-map/slug-set, ≥72% inventory, positional ≥60% проти 2+ планів,
  class-Jaccard ≥85%, widget-superset, **content-fp ≥45% проти профілю, шаблон відгуків сиблінга (місто/стаж)**.
  `tests/selftest.py` перевіряє, що клон справді ловиться.

## Жорсткі правила
- `h1 .brand-line` + бренд-first `<title>` + 1 h1/сторінка — audit ловить. Бренд у h1 рівно
  ОДИН раз: шаблон hero друкує його в `.brand-line`, тому `hero.h1_rest`/`h1_accent` його не
  повторюють (модель закривала заголовок брендом → «Starling Aegistra … Starling Aegistra» на
  starlingaegistra.site). Валідатор пакує це в repair, `assemble.sanitize_hero_copy` чистить
  легасі-паки, `seo_audit` валить сторінку з подвійним брендом у h1.
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
- Мобільні правила — ТІЛЬКИ після базових правил компонента. `@media`-блок, написаний вище за
  базу (`.ps-split`), програє каскад: на телефоні лишається десктопна сітка й блок вилазить за
  екран (реальний баг pulse-sim на terso-beniaggio.site). `mobile_lint` тепер це ловить.
- Мобільне меню: якщо варіант хедера задає власний `display` для `.blk-nav`, він мусить мати
  пару в `@media(max-width:700px)` — `.blk-nav{display:none}` + `.blk-nav.open{display:flex}`.
  Інакше специфічність десктопного правила перебиває базове «сховано», і бургер не закриває меню
  (реальний баг варіанта `i`).
- Self-check після змін інфраструктури: `python3 tests/selftest.py` (має бути PASSED).
- Збірка спершу лікує себе, а потім падає: `self_heal_page` прибирає повтор абзацу
  (не чіпаючи `aria-hidden` копій слайдерів) і повертає пробіл у злиплий бренд; локалізатор
  після repair-пасів ретраїть проблемні рядки поштучно. Але помилки лишаються помилками:
  `--build` завершується червоним, якщо гейт не пройшов. Публікація з боргами — лише явний
  `--ship-anyway` (ERR стають WARN і друкуються). Тестовий етап: `--ship-anyway` не вмикати.
- Canonical-URL гігієна: sitemap/canonical/внутрішні лінки — тільки з `.php`; кожен контент-файл
  починається з PHP-canonical-guard (`PHP_CANON_GUARD` в assemble.py): GET/HEAD на URL без `.php`
  → 301 на `.php` (панель віддає extensionless з 200 і перегенеровує sitemap без `.php`).
  Guard не ставиться на thanks.php (рядок 1 = postback) та 404.php (мʼякі 404 не мають 301-ити).
  seo_audit ловить non-.php locs у sitemap та canonical-и поза sitemap.
- Блог живе в `/blog/` (`assemble.BLOG_DIR`): головна — `blog/index.php` (`BLOG_HUB`), статті —
  `blog/<slug>.php`; `hub_slug` у планах більше не використовується (старий ключ ігнорується).
  Canonical/sitemap/JSON-LD — з текою. Shell authored для кореня (`index.php`, `blocks/…`, `img/…`), тому сторінки
  блогу проходять `assemble.rebase_relative(page, local={...})`: `../` додається всім кореневим
  лінкам/ассетам, а лінки всередині силу лишаються локальними. Не хардкодити `../` у шаблонах і
  не писати блог-файли в корінь. `seo_audit.norm_url` резолвить відносні лінки від теки сторінки.
  Пак блогу — один довгий JSON-відповідь, і провайдер його псує (реальні випадки: обрив на
  18 830 символах, неекранована лапка, сирий `\n` усередині рядка — `Invalid control character`).
  `tools/blog_content.py` це переживає: `extract_json` парсить зі `strict=False` і без висячих ком,
  `close_truncated` добирає обрізану відповідь, далі один compact-retry, `prune_incomplete`
  відсіює недописану статтю, а теми, яких пак не діставив, питаються по одній статті (`ask_article`).
  Repair не жене весь пак: помилки, прив'язані до статті (`articles[i] …`), лікуються переписуванням
  ЛИШЕ цієї статті; повний пак — лише коли проблема на рівні хаба/дедупу. Ціль 380 слів має
  допуск ±60 (`body_word_floor` → 320): 378 слів — це закінчена стаття, а не привід валити збірку
  (реальний баг dk-spornadike.site — два повних repair-паси й червона збірка через 2 слова).
  Офлайн-заглушка — лише коли не вдалося жодне з цього (і тоді збірка падає, а не шипить мовчки).
- Контент-репейр теж точковий: `llm_content.repair_targets`/`repair_objects` переписують лише
  об'єкт, на який вказала помилка (`faq.items`, `reviews.items`, `sections.guide`, `hero`,
  `livebar`, `meta`…), а повний пак лишається запасним шляхом для структурних дір. Довгі сторінки
  мають допуск ±60 слів (`450 → 390`, `600 → 540`) і лікуються навіть коли поруч є інші помилки
  (раніше одна порожня дрібниця блокувала таргетований репейр). Косметика без моделі:
  `self_heal` добиває бренд у `title_home`, ріже його до 70 символів і повертає пробіл у злиплий
  бренд. Локалізатор не перекладає адреси (`.addr/.address/.street/.venue`) — «Park Avenue»
  лишається як є, інакше гейт «not translated» валив увесь переклад.
- Повторний `--build` не палить токени на те, що вже добре: `gen_plan.content_is_reusable` /
  `blog_is_reusable` перевіряють наявний пак гейтом і перевикористовують його (resume після
  пізнього падіння); `--force` змушує перегенерувати. Паки несуть `meta.content_lang`, а
  офлайн-заглушка блогу — `_offline_fallback`; такий пак ніколи не перевикористовується
  (легасі-заглушку ловлять порівнянням з детермінованим `offline_pack`). Довгі сторінки
  `inner_product`/`inner_offer`/`inner_faq` при невірній формі лікуються таргетованим запитом
  лише цих об'єктів (`repair_inner_pages`), а не повтором усього 5-тисячного паку.

## Структура продукту
```
gen_plan.py             планувальник (seed-детермінований, валідує проти plans/*) + --build ланцюжок
tools/content_gen.py    контент-пак з resources/content-l10n.json (мова гео, seed-варіації)
tools/llm_content.py    LLM-пак: бриф → модель пише JSON → валідація + repair + запис персон/чисел
tools/brand_icons.py    favicon/og з палітри плану (rsvg-convert + PIL)
tools/mobile_lint.py    статичний мобільний гейт (viewport/tbl-scroll/inline grid)
tools/profile_write.py  реєстрація profiles/<domain>.json + взаємні siblings
tools/blog_content.py   блог-пак (3–5 статей) одним LLM-викликом → content/<domain>-blog.json
blog_assemble.py         блог-шар: teaser + /blog/index.php + статті /blog/<slug>.php (3 стилі, обкладинки), валідатор паку
blocks/blog.css          стилі хаба/обкладинок (лише для сторінок із plan.blog)
resources/blog-topics.json  банк 20 тем для --blog
resources/content-l10n.json  мовні банки текстів (it/cs/en; решта → en fallback)
resources/hero-proof.json  докази hero: claims / quote / quote_by / steps (en/it/cs)
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
appshots/ ×20           фото телефона з графіками (Pexels License, manifest.json)
trust/ ×19              SVG-логотипи під формою (Simple Icons, CC0, manifest.json)
integr.-example/        канон інтеграції (config плейсхолдери, crm.php канонічний)
plans/ plans/*.json     історія планів (вхід twin_check; не видаляти)
sites/                  вихід assembler'а
tests/selftest.py       самоперевірка інфраструктури (54 перевірки + e2e)
```

## Звіт (мовою людини)
Таблиця: домен / палітра / скін / hero / віджети / депозит / контакти / слуги.
Матриця відмінностей сиблінгів + вихід гейтів. Вручну: DNS, IP-whitelist, мобільний огляд.
Нагадування: прод не тестували.
