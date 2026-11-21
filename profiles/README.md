# profiles/ — реєстр збудованих офферів

Один файл на домен: `profiles/<domain>.json`. Пишеться автоматично командою
`python3 gen_plan.py … --build` (крок PROFILE, `tools/profile_write.py`) —
руками правити можна, але контакти/дизайн мають збігатися з сайтом.

Мінімум полів: `domain brand brand_variants geo lang locale currency deposit_rule
regulator buyer funnel city contacts{addr phone email hours} design{palette theme skin
fonts hero} widgets slugs people[{name photo}] plan content built siblings gates manual`.

Правила:
- `buyer` = `PUMA`, `funnel` = найдовший CAPS-токен бренду (напр. `VOLTREKSC`).
- Контакти сиблінгів не повторюються (інша вулиця + номер телефону) — це перевіряється очима.
- `siblings` заповнюється взаємно: додаєш новий домен — у сусідів з'являється його домен.
- `gates` фіксує результат автогейтів; `manual` — що лишилось людині (DNS, IP-whitelist,
  мобільний огляд, прод не тестували бо submit = лід у CRM).
