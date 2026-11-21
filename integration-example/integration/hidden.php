<?php
$__cfgFile = __DIR__ . '/config.php';
$__cfg = is_file($__cfgFile) ? require $__cfgFile : [];
if (!is_array($__cfg)) {
    $__cfg = [];
}

$__allowed = ['base', 'ads', 'fb', 'device', 'keitaro'];
$__groups = $__cfg['lead_fields'] ?? ['base'];
if (!is_array($__groups)) {
    $__groups = ['base'];
}
$__groups = array_values(array_intersect($__groups, $__allowed));

$__host = (string) ($_SERVER['HTTP_HOST'] ?? '');
$__ua   = (string) ($_SERVER['HTTP_USER_AGENT'] ?? '');

$__maps = [
    'base' => [
        'country' => (string) ($__cfg['country'] ?? ''),
        'lang'    => (string) ($__cfg['lang'] ?? ''),
        'funnel'  => (string) ($__cfg['funnel'] ?? ''),
        // Real domain in the lead: Telegram shows it in its log; the CRM gets google.com (overridden in lib/crm.php).
        'domain'  => ($__cfg['domain'] ?? '') !== '' ? (string) $__cfg['domain'] : $__host,
        'buyer'   => ($__cfg['buyer'] ?? '') !== '' ? (string) $__cfg['buyer'] : (string) ($__cfg['default_buyer'] ?? ''),
    ],
    'ads' => [
        'utm_source'    => '{utm_source}',   'utm_medium'    => '{utm_medium}',   'utm_campaign'  => '{utm_campaign}',
        'utm_content'   => '{utm_content}',  'utm_term'      => '{utm_term}',     'utm_placement' => '{utm_placement}',
        'campaign_id'   => '{campaign_id}',  'adset_id'      => '{adset_id}',     'ad_id'         => '{ad_id}',
        'adset_name'    => '{adset_name}',   'ad_name'       => '{ad_name}',
    ],
    'fb' => [
        'fbclid' => '{fbclid}',
    ],
    'device' => [
        'user_agent' => $__ua,
        'ttclid'     => '{ttclid}',
        'time_on_page' => '0',
    ],
    'keitaro' => [
        'subid'                => '{subid}',        'pixel'                => '{pixel}',
        'offer_name'           => '{offer_id}',     'keitaro_campaign_id'  => '{campaign_id}',
        'keitaro_campaign_name' => '{campaign_name}', 'catalog_id'         => '{catalog_id}',
        'catalog_name'         => '{catalog_name}', 'bbg'                  => '',
        'os'                   => '',               'idfa'                 => '',
        'gaid'                 => '',
    ],
];

foreach ($__groups as $__g) {
    foreach (($__maps[$__g] ?? []) as $__name => $__raw) {
        $__val = trim((string) ($_GET[$__name] ?? ''));
        if ($__val === '') {
            if (preg_match('/^\{+([^}]+)\}+$/', (string) $__raw, $__m)) {
                $__val = '{' . $__m[1] . '}';
            } else {
                $__val = (string) $__raw;
            }
        }
        if ($__val === '') {
            continue;
        }
        $__cls = $__name === 'country' ? ' class="js-lead-country"' : '';
        echo '<input type="hidden" name="' . htmlspecialchars($__name, ENT_QUOTES)
            . '" value="' . htmlspecialchars($__val, ENT_QUOTES) . '"' . $__cls . '>';
    }
}
