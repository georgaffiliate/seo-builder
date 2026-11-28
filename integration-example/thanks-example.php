<?php
/**
 * thanks-example.php — мінімальна сторінка «дякуємо».
 *
 * Використання:
 *   1) покладіть цей файл у корінь сайту як thanks.php;
 *   2) якщо у вас наша панель — перший рядок має бути require _postback.php + send_postback();
 *      (файл _postback.php генерує панель, у сторонньому хостингу його немає — код нижче
 *      це перевіряє й просто пропускає крок);
 *   3) у формі/скрипті вкажіть data-thanks="./thanks.php".
 *
 * Autologin: якщо CRM повернув auto_login_url, lead-form.js прокидає його в ?autologin=…
 * і сторінка може перенаправити користувача (див. блок нижче).
 */

// 1. Постбек у панель (no-op, якщо файлу немає)
if (is_file(__DIR__ . '/_postback.php')) {
    require __DIR__ . '/_postback.php';
    if (function_exists('send_postback')) {
        send_postback();
    }
}

// 2. Autologin-редірект (необовʼязково)
$autologin = isset($_GET['autologin']) ? trim((string) $_GET['autologin']) : '';
$isUrl = $autologin !== '' && preg_match('~^https?://~i', $autologin) === 1;

$lang = 'sk'; // замініть на мову сайту, якщо потрібно
$copy = [
    'sk' => ['h1' => 'Ďakujeme za vašu žiadosť', 'p' => 'Náš tím vás bude kontaktovať v pracovných hodinách, zvyčajne do 30 minút.', 'back' => 'Späť na úvod'],
    'cs' => ['h1' => 'Děkujeme za vaši žádost', 'p' => 'Náš tým vás bude kontaktovat v pracovních hodinách, obvykle do 30 minut.', 'back' => 'Zpět na úvod'],
    'it' => ['h1' => 'Grazie per la richiesta', 'p' => 'Il nostro team ti contatterà in orario di ufficio, di solito entro 30 minuti.', 'back' => 'Torna alla home'],
    'en' => ['h1' => 'Thank you for your request', 'p' => 'Our team will contact you during office hours, usually within 30 minutes.', 'back' => 'Back to home'],
];
$t = $copy[$lang] ?? $copy['en'];
?>
<!doctype html>
<html lang="<?= htmlspecialchars($lang, ENT_QUOTES) ?>">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title><?= htmlspecialchars($t['h1'], ENT_QUOTES) ?></title>
<?php if ($isUrl): ?>
  <meta http-equiv="refresh" content="3;url=<?= htmlspecialchars($autologin, ENT_QUOTES) ?>">
<?php endif; ?>
</head>
<body style="font-family:system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:0 20px;line-height:1.6">
  <h1 style="font-size:28px"><?= htmlspecialchars($t['h1'], ENT_QUOTES) ?></h1>
  <p><?= htmlspecialchars($t['p'], ENT_QUOTES) ?></p>
<?php if ($isUrl): ?>
  <p><a href="<?= htmlspecialchars($autologin, ENT_QUOTES) ?>"><?= htmlspecialchars($t['back'], ENT_QUOTES) ?></a></p>
<?php else: ?>
  <p><a href="./"><?= htmlspecialchars($t['back'], ENT_QUOTES) ?></a></p>
<?php endif; ?>
</body>
</html>
