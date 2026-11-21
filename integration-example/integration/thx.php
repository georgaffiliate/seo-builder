<?php
$configPath = dirname((string) ($_SERVER['SCRIPT_FILENAME'] ?? '')) . '/config.php';
if (!is_file($configPath)) {
    $configPath = __DIR__ . '/config.php';
}
$config = is_file($configPath) ? require $configPath : [];
if (!is_array($config)) {
    $config = [];
}
if (!isset($language) || $language === '') {
    $language = $config['lang'] ?? 'auto';
}

$autologinEnabled = !array_key_exists('autologin_redirect', $config) || !empty($config['autologin_redirect']);

$delayMsSource = isset($thankYouRedirectDelayMs) ? $thankYouRedirectDelayMs : ($config['autologin_redirect_delay_ms'] ?? 3000);
$redirectDelayMs = max(0, min(600000, (int) $delayMsSource));

$pixel     = $_GET['pixel'] ?? '';
$autologin = $_GET['autologin'] ?? '';
$subid     = $_GET['subid'] ?? '';
$jobId     = $_GET['job_id'] ?? '';
$tsId      = (int) ($_GET['ts_id'] ?? 0);

if ($pixel === '{pixel}') {
    $pixel = '';
}

const BIGO_TS_ID = 13;
$isBigo = $tsId === BIGO_TS_ID;

$bigoBrowserPixel = !empty($config['bigo_browser_pixel']);
$fbPixelEnabled = !empty($config['facebook_pixel']);

$pixelEnabled = $pixel !== '' && (!$isBigo || $bigoBrowserPixel);
if (!$fbPixelEnabled && !$isBigo) {
    $pixelEnabled = false;
}

$statusUrl = (isset($jobStatusBase) && $jobStatusBase !== '') ? $jobStatusBase : '../api/integration/job_status.php';
$base = rtrim(str_replace('\\', '/', dirname((string) ($_SERVER['SCRIPT_NAME'] ?? '/'))), '/');
$src  = $base . '/thanks-init.js';
?>
<?php if ($isBigo && $pixelEnabled): ?>
<script>
  window.bgdataLayer = window.bgdataLayer || [];
  function bge() { bgdataLayer.push(arguments); }
  window.bge = window.bge || bge;
  bge('init', <?php echo json_encode($pixel, JSON_UNESCAPED_UNICODE); ?>);
  !function(e,t){try{if(!e)return;try{"undefined"!=typeof localStorage&&localStorage.setItem("pixel_storage_dm",e)}catch(e){}var n=document.createElement("script");n.src="https://"+e+"/ad/events.js?pixel_id="+t,n.async=!0,n.setAttribute("data-pixel-script-dm",e),(document.head||document.getElementsByTagName("head")[0]||document.body||document.documentElement).appendChild(n)}catch(e){}}(function(e){try{var t=new RegExp("(^|&)"+e+"=([^&]*)(&|$)"),n=window.location.search.substr(1).match(t);return null!=n?decodeURIComponent(n[2].replace(/\+/g," ")):""}catch(e){return""}}("dm")||"tk.mowell.tech",<?php echo json_encode($pixel, JSON_UNESCAPED_UNICODE); ?>);
</script>
<?php endif; ?>
<script src="<?= htmlspecialchars($src, ENT_QUOTES) ?>"
        data-pixel="<?= htmlspecialchars($pixel, ENT_QUOTES) ?>"
        data-pixel-enabled="<?= $pixelEnabled ? 'true' : 'false' ?>"
        data-fb-enabled="<?= $fbPixelEnabled ? 'true' : 'false' ?>"
        data-is-bigo="<?= $isBigo ? 'true' : 'false' ?>"
        data-subid="<?= htmlspecialchars($subid, ENT_QUOTES) ?>"
        data-autologin="<?= htmlspecialchars($autologin, ENT_QUOTES) ?>"
        data-job-id="<?= htmlspecialchars($jobId, ENT_QUOTES) ?>"
        data-poll="<?= !empty($config['job_polling']) ? 'true' : 'false' ?>"
        data-auto-redirect="<?= $autologinEnabled ? 'true' : 'false' ?>"
        data-delay-ms="<?= (int) $redirectDelayMs ?>"
        data-status-url="<?= htmlspecialchars($statusUrl, ENT_QUOTES) ?>"></script>
