# seo-builder

Контейнер-сервіс, який за одним HTTP-запитом збирає готовий статичний сайт
(план → контент → верстка → гейти → іконки → SEO-перевірки) і, за бажанням,
одразу заливає його на хостинг через API панелі.

**Це сервіс-сусід:** контейнер `seo-builder` запускається поруч (на тій самій
машині, в тій самій Docker-мережі), що й ваш робочий контейнер. Ваш контейнер
відправляє йому HTTPS-запит — сервіс будує сайт, заливає його по API панелі
і віддає назад JSON-відповідь «все залито успішно» (або детальну помилку).

```
┌────────────────┐   HTTPS :8443    ┌───────────────────┐        ┌────────────────┐
│ ваш контейнер  │ ───────────────▶ │  seo-builder      │ ──────▶ │ панель хостингу│
│ (клієнт)       │ ◀─────────────── │  (+ caddy TLS)    │  zip    │ (stores API)   │
└────────────────┘  JSON-результат  └───────────────────┘        └────────────────┘
```

- Пайплайн всередині — той самий, що в CLI: `gen_plan.py --build` /
  `--with-llm` (план, контент, assemble, гейти, іконки, профіль).
- LLM пише **тільки контент-JSON**, верстку збирає детермінований конструктор.
- Кожен сайт унікальний: `twin_check` звіряє план з історією `plans/`.

---

## Швидкий старт

```bash
git clone https://github.com/georgaffiliate/seo-builder.git
cd seo-builder
cp .env.example .env            # заповнити API_TOKEN (+ ключі, див. таблицю нижче)
docker compose up -d --build

# перевірка
curl -sk https://localhost:8443/healthz
# {"ok": true, "service": "seo-builder", ...}
```

## Доступ з іншого контейнера (та сама машина)

**Варіант 1 — приєднати вже запущений контейнер до нашої мережі (найпростіше):**

```bash
docker network connect seo-builder_buildnet <ім'я_вашого_контейнера>
```

Після цього всередині вашого контейнера сервіс доступний як:

```
https://seo-builder-tls:8443
```

**Варіант 2 — у compose-файлі клієнта:**

```yaml
services:
  my-app:
    # ...
    networks: [default, builder]

networks:
  builder:
    external: true
    name: seo-builder_buildnet
```

**З хост-машини** сервіс доступний на `https://localhost:8443`.

TLS — self-signed сертифікат, який `scripts/deploy.sh` генерує разово на
сервері (SAN: `localhost`, `seo-builder-tls`, IP сервера), тому клієнтські
запити йдуть з `curl -k` / `verify=False`, або підключіть власний CA.

---

## Блог-сторінки (`--blog`)

Класична збірка не змінюється: без `--blog` план не містить блоку `blog`, і
`assemble.py` взагалі не завантажує блог-модуль.

```bash
python3 gen_plan.py --brand "Infinity Shop" --lang it --domain infinity-shop.site \
  --blog --build
```

Що додається:

- **3–5 статей** (рандомно) з банку `resources/blog-topics.json` (20 тем). Теми,
  використані останніми планами, пропускаються першими; дати фіксуються планом і
  ніколи не бувають у майбутньому.
- **Один LLM-виклик** на весь пак: `tools/blog_content.py` відправляє бриф тем і
  отримує `content/<domain>-blog.json` (статті, FAQ, related, CTA). Один repair-пас;
  якщо модель не дала валідний JSON — детермінований offline-пак, щоб збірка не падала.
- **3 структурні стилі** (`a` editorial / `b` magazine + TOC / `c` compact brief),
  які обирає план. Хедер, футер, livebar, палітра, скін і шрифти — від основного сайту.
- **Головна сторінка блогу** — `blog/index.php` (`/blog/` відкриває її, `/blog` → 301 `/blog/`):
  перелік усіх статей + teaser на головній; хлібні крихти статей ведуть на неї, а не на `#guides`.
  **Усі блог-сторінки живуть у `/blog/`** (`assemble.BLOG_DIR`), тобто `/blog/<slug>.php`,
  поки офферні сторінки лишаються в корені. Shell-лінки (`index.php`, `blocks/…`, `img/…`)
  ребейзяться на `../` через `assemble.rebase_relative()`, лінки всередині силу лишаються
  локальними; canonical і sitemap містять `/blog/`.
- **Кожна стаття має власну обкладинку 1200×630** (детермінований SVG/PNG з палітри,
  `img/blog-<slug>.png` у корені), яка йде в `og:image` і `BlogPosting.image`.
- `BlogPosting` містить повний `publisher` (name + logo), `mainEntityOfPage`, `wordCount`;
  `BreadcrumbList` веде `Home → хаб → стаття`; `FAQPage` — лише видимі питання.
- Дати в teaser/byline — мовою сайту (`6 ottobre 2026`), ISO лишається в `<time datetime>`
  і sitemap. `title` разом із бренд-префіксом обмежений 70 символами.
- Гейт блогу ловить: дублі слагов/абзаців, майбутні дати, залишкові `{brand}`, `TODO`
  (лише великими літерами — слово `metodo` не рахується), емодзі, чужу писемність
  (кирилиця/китайська на латинському сайті) і задовгі title.
- Усі сторінки потрапляють у `sitemap.xml` і проходять `seo_audit` (schema/image/publisher,
  hub ItemList, CTA, дата, обсяг), `mobile_lint`, `twin_check`.

Тільки для тестів / без ключа: `--blog --build --offline` (пише generic offline-пак,
не для продакшну — замініть контент перед деплоєм).


## API

Авторизація: заголовок `Authorization: Bearer <API_TOKEN>` на всіх ендпоінтах
крім `/healthz`.

### `POST /blog/article`

Одна стаття блогу як **контент-JSON** (не HTML). Панель рендерить її у шелл живої
сторінки сайту, тому верстка й CSS не залежать від моделі. `/build` не змінюється.

```bash
curl -sk -X POST https://seo-builder-tls:8443/blog/article \
  -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  -d '{"lang":"lt","brand":"Brento","domain":"site.lt",
       "existing":[{"slug":"first","title":"Pirmas"}],
       "topic":{"intent":"withdrawal fees"}}'
```

Відповідь `200 {"ok":true,"article":{...}}`, де `article` містить `slug`, `title`, `h1`,
`excerpt`, `read_min`, `takeaways`, `sections[{h2,p,points}]`, `faq[{q,a}]`, `related`,
`cta`. Модель відповідає лише за текст: числа/ліцензії не вигадуються, HTML/емодзі/депозит
заборонені, а відповідь проходить валідатор (slug, довжини, ≥380 слів, 2–5 FAQ).
Помилки: `400` некоректний запит, `502` модель не дала валідний JSON або немає ключа.

Необов'язкове поле `title_max` (30..72) — скільки знаків лишає панель на `title` без
бренду: вона дописує `Brand — ` у `<title>` і тримає 70 разом із префіксом. Без поля
модель просять 50–65, як раніше; перебір на кілька знаків підрізається по межі слова,
а не валить запит.

Необов'язкове поле `links` — масив об'єктів `{"url": "https://…"}` (до 3). Модель вставляє
кожен URL у тіло статті як `[анкор](URL)`; панель рендерить лише ці URL, решта markdown-лінків
стає текстом. Анкор — 2–6 слів мовою статті. Для блоку «корисні посилання» модель віддає
`link_label` тією ж мовою. Без `links` промпт і поведінка не змінюються.

### `POST /build`

Поставити сайт у чергу на збірку.

**Приклад запиту:**

```bash
curl -sk -X POST https://seo-builder-tls:8443/build \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "brand": "Infinity Shop",
    "lang": "en",
    "cc": "CZ",
    "geo": "Praha",
    "currency": "CZK",
    "domain": "infinity-shop.site",
    "with_llm": true,
    "deploy": true
  }'
```

**Відповідь (202 Accepted, збірка йде у фоні):**

```json
{
  "ok": true,
  "job_id": "7f3c2a1e8b9d4f02a1c35e6d7b8a9f01",
  "status": "queued",
  "domain": "infinity-shop.site",
  "poll": "/jobs/7f3c2a1e8b9d4f02a1c35e6d7b8a9f01"
}
```

**Параметри:**

| Поле         | Тип      | Обов'язково | Опис |
|--------------|----------|-------------|------|
| `brand`      | string   | так         | Бренд як є, напр. `Infinity Shop` |
| `lang`       | string   | так         | Мова/гео сайту: `en`, `it`, `cs`, … |
| `domain`     | string   | так         | Домен, напр. `infinity-shop.site`. Якщо план уже існує — помилка 409 |
| `cc`         | string   | ні          | ISO-код країни (`CZ`, `NO`, `IT`…); за замовчуванням виводиться з `lang` |
| `geo`        | string   | ні          | Місто, напр. `Praha` (інакше — столиця) |
| `currency`   | string   | ні          | Валюта депозиту, за замовчуванням `EUR` |
| `seed`       | int      | ні          | Фіксація варіації плану (інакше детерміновано з brand+domain) |
| `calculator` | string   | ні          | `auto` (за замовчуванням) / `on` / `off` |
| `with_llm`   | bool     | ні          | `true` — унікальні тексти пише LLM (потрібен `VENICE_API_KEY`); `false` — мовний банк |
| `blog`       | bool     | ні          | `true` — додати блог-шар: 3–5 статей з банку тем + teaser на головній |
| `llm_model`  | string   | ні          | Перевизначити модель LLM |
| `deploy`     | bool     | ні          | `true` — після успішної збірки залити сайт на панель |
| `force`      | bool     | ні          | `true` — перезібрати домен, план якого вже існує |
| `wait`       | bool     | ні          | `true` — тримати з'єднання до завершення (відповідь — готовий результат) |

### `GET /jobs/{job_id}`

Статус і результат. Поки працює — `202` зі статусом; коли завершено — `200`.

Статуси: `queued → running → deploying → done | failed`.

```json
{
  "job_id": "7f3c…",
  "status": "done",
  "domain": "infinity-shop.site",
  "seed": 4213775,
  "pages": 9,
  "deploy": {
    "ok": true,
    "domain": "infinity-shop.site",
    "store_id": 123,
    "can_upload": true,
    "upload_http": 200,
    "note_htaccess": ".htaccess rejected by the panel - expected (custom 404 via 404.php)",
    "public_check": { "url": "https://infinity-shop.site/", "status": 200 }
  },
  "build_log": "PLAN OK -> plans/infinity-shop.site.json  (seed 4213775) …",
  "log_tail": "== building: gen_plan.py --build … == upload OK"
}
```

При помилці збірки/деплою: `status: "failed"`, поле `error` з причиною,
`build_log` / `deploy_log` з хвостом логів. **Гейти впали → нічого не деплоїться.**

### `GET /healthz`

Без авторизації. `{"ok": true, "queued": 0, "jobs": 3}` — для моніторингу.

### Коди відповідей

| Код | Значення |
|-----|----------|
| 202 | Прийнято в чергу / ще працює |
| 200 | Готово (`done` або `failed` — див. `status`) |
| 400 | Невалідний запит (немає `brand`/`lang`/`domain`, поганий JSON…) |
| 401 | Немає/невірний `Authorization: Bearer` |
| 404 | Невідомий шлях або `job_id` |
| 409 | План для домену вже існує (використайте `force: true`) |

### Готовий скрипт-клієнт

```bash
export API_TOKEN=...
docker network connect seo-builder_buildnet "$HOSTNAME"   # якщо ви в контейнері
./client/example.sh                                       # Infinity Shop → infinity-shop.site
DEPLOY=1 WAIT=1 ./client/example.sh                       # збірка + деплой, синхронно
# свої значення: BRAND=... DOMAIN=... CC=NO GEO=Oslo ./client/example.sh
```

---

## Сервер і автодеплой (SSH-ключ у GitHub Secrets)

Напрямок доступу один: **GitHub Actions → сервер** (rsync + rebuild).
Сервер нічого не тягне з GitHub, ключ не треба класти в `authorized_keys` вручну.

Разово на сервері:

```bash
# 1. конфіг (до першого деплою!)
mkdir -p /opt/seo-builder/app
nano /opt/seo-builder/app/.env        # вміст — з .env.example, вписати свої ключі

# 2. файрвол
ufw allow OpenSSH && ufw allow 8443/tcp && ufw enable

# 3. ключ для GitHub Actions
ssh-keygen -t ed25519 -N "" -f ~/.ssh/gha_deploy
cat ~/.ssh/gha_deploy.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/gha_deploy                 # вміст → секрет SSH_PRIVATE_KEY
```

У **GitHub → repo → Settings → Secrets and variables → Actions** додати:

| Secret | Значення |
|--------|----------|
| `SSH_HOST` | IP сервера, напр. `84.200.80.37` |
| `SSH_USER` | користувач сервера (з права на docker, напр. `root`) |
| `SSH_PRIVATE_KEY` | повний вміст `~/.ssh/gha_deploy` (разом з BEGIN/END рядками) |
| `SSH_PORT` | опційно, якщо SSH не на 22 |

Автодеплой: push у `main` → Actions робить `rsync` коду в `/opt/seo-builder/app`
(`.env` не чіпає) → `docker compose up -d --build` → health check.
Ручний запуск: **Actions → deploy → Run workflow**.

---

## Змінні середовища (`.env`)

| Змінна | Навіщо |
|--------|--------|
| `API_TOKEN` | Bearer-токен для клієнтів (обов'язково) |
| `VENICE_API_KEY` | Ключ LLM для `with_llm: true`. Без нього сайт збирється на мовному банку |
| `PANEL_API_KEY` | Ключ панелі хостингу (lookup stores + upload zip). Або змонтуйте файл у `/run/secrets/panel_api_key` |
| `PANEL_API_URL` | Адреса панелі, за замовчуванням `https://florentina-tr.shop` |
| `BUILD_TIMEOUT` | Ліміт на збірку, сек (3600) |
| `DEPLOY_TIMEOUT` | Ліміт на деплой, сек (600) |

Збірки виконуються **послідовно** (по одній у черзі) — це свідомо: гейти
унікальності порівнюють кожен план з історією.

## Що зберігається де

Docker-volumes: `plans/` (історія планів — вхід для анти-твін гейта),
`profiles/`, `content/` (контент-паки), `sites/` (зібрані сайти). Дані
переживають рестарт контейнера і не потрапляють у git.

## Обмеження та нагадування

- Панель відкидає `.htaccess` — це нормально, власний 404 працює через `404.php`.
- **Прод-форму не тестувати** (submit = лід у CRM). Перевірка — GET-статуси
  сторінок, їх повертає `public_check`.
- DNS та IP-whitelist панелі налаштовуються вручну — якщо `public_check.status`
  дорівнює `null`, домен, швидше за все, ще не резолвиться.
- Мобільний огляд (360/390/768 px) залишається ручним кроком — це єдине,
  що машина не ловить.

---

## API quick reference (EN)

```bash
curl -sk -X POST https://seo-builder-tls:8443/build \
  -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  -d '{"brand":"Infinity Shop","lang":"en","cc":"CZ","geo":"Praha",
       "currency":"CZK","domain":"infinity-shop.site","with_llm":true,"deploy":true}'
# -> 202 {"job_id":"...","poll":"/jobs/..."}
curl -sk https://seo-builder-tls:8443/jobs/<job_id> -H "Authorization: Bearer $API_TOKEN"
# -> 200 {"status":"done","deploy":{"ok":true,...}}  |  {"status":"failed","error":"..."}
```

Add `"wait": true` to hold the connection until the job finishes.
The service runs as a sibling container on the same Docker host; TLS is
self-signed (use `-k` or mount your own CA).
