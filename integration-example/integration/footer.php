<?php
$__cfgFile = __DIR__ . '/config.php';
$__cfg = is_file($__cfgFile) ? require $__cfgFile : [];
if (!is_array($__cfg)) {
    $__cfg = [];
}

$__country = (string) ($__cfg['country'] ?? 'auto');
$__poll    = !empty($__cfg['job_polling']) ? 'true' : 'false';
// Offer pages live at the domain root, but they can be included from /blog/*.php.
// A relative './thanks.php' or '/blog/lead-form.js' breaks there, so both the
// script and the redirect target are root-absolute.
$__base    = '';
$__thanks  = (isset($thanksUrl) && $thanksUrl !== '') ? $thanksUrl : $__base . '/thanks.php';
$__lf      = __DIR__ . '/../../lead-form.js';
$__ver     = is_file($__lf) ? (string) filemtime($__lf) : '1';
$__src     = $__base . '/lead-form.js?v=' . $__ver;
?>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.15/css/intlTelInput.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.15/js/intlTelInput.min.js"></script>
<script src="<?= htmlspecialchars($__src, ENT_QUOTES) ?>"
        data-country="<?= htmlspecialchars($__country, ENT_QUOTES) ?>"
        data-tsid="{ts_id}"
        data-poll="<?= $__poll ?>"
        data-thanks="<?= htmlspecialchars($__thanks, ENT_QUOTES) ?>"></script>
