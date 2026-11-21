<?php
$__cfgFile = __DIR__ . '/config.php';
$__cfg = is_file($__cfgFile) ? require $__cfgFile : [];
if (!is_array($__cfg)) {
    $__cfg = [];
}

$__allowed = ['ads', 'fb', 'device', 'keitaro'];
$__groups = $__cfg['lead_fields'] ?? [];
if (!is_array($__groups)) {
    $__groups = [];
}
$__groups = array_values(array_intersect($__groups, $__allowed));

// NOTE: the 'base' group (country/lang/funnel/domain/buyer) is NOT rendered here.
// Those are static per-offer values from config.php and are attached server-side in
// api.php. Rendering them into the HTML would put an identical hidden-input block
// into every farm site's view-source — an obvious same-network fingerprint — and
// would let the client spoof them. Per-visitor groups below stay client-side.

$__ua = (string) ($_SERVER['HTTP_USER_AGENT'] ?? '');

$__maps = [
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
        echo '<input type="hidden" name="' . htmlspecialchars($__name, ENT_QUOTES)
            . '" value="' . htmlspecialchars($__val, ENT_QUOTES) . '">';
    }
}
