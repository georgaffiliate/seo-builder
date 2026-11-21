<?php
/**
 * api.php — synchronous lead intake (NO job files).
 *
 * Flow: browser POST → antifraud → CRM → a response carrying crm_response (which
 * contains auto_login_url) goes straight back to the browser. Telegram is fired
 * after the response is flushed (fastcgi_finish_request), but nothing is written
 * to disk — hence job_status.php/polling are not needed.
 */
header('Content-Type: application/json; charset=UTF-8');
date_default_timezone_set('Europe/Kyiv');
// Keep warnings (e.g. curl_close() on PHP 8.5) out of the response body
// so they don't break JSON.parse on the frontend
error_reporting(E_ALL & ~E_DEPRECATED);

require_once __DIR__ . '/lib/crm.php';
require_once __DIR__ . '/lib/telegram.php';
require_once __DIR__ . '/lib/keitaro.php';
require_once __DIR__ . '/lib/buyers.php';
require_once __DIR__ . '/lib/frod.php';

$config   = require __DIR__ . '/config.php';
$buyerMap = $config['buyers'];
$apiKey   = $config['fixed_api_key'];
$crmUrl   = $config['crm_api_url'];
$tgToken  = $config['tg_bot_token'];

// --- Input ---
$rawBody  = file_get_contents('php://input');
$raw      = json_decode($rawBody, true);
$lead     = is_array($raw['post'] ?? null) ? $raw['post'] : (is_array($raw) ? $raw : []);
$session  = is_array($raw['session'] ?? null) ? $raw['session'] : [];
$server   = is_array($raw['server'] ?? null) ? $raw['server'] : [];
$rawClick = is_array($raw['rawclick'] ?? null) ? $raw['rawclick'] : [];

if (!$lead) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'empty_body'], JSON_UNESCAPED_UNICODE);
    exit;
}

ignore_user_abort(true);
@set_time_limit(60);

// --- Buyer ---
$buyerResolved = buyer_resolve(
    (string) ($lead['buyer'] ?? ''),
    $buyerMap,
    (string) ($config['default_buyer'] ?? '')
);
$buyerKey    = $buyerResolved['key'];
$buyerConfig = $buyerResolved['config'];

if ($buyerResolved['fallback_used']) {
    $lead['buyer_original'] = $buyerResolved['original'];
    $lead['buyer']          = $buyerKey;
}

if ($buyerConfig && !empty($buyerConfig['crm_token'])) {
    $apiKey = $buyerConfig['crm_token'];
}

$offerId = (string) ($lead['funnel'] ?? '');
$payload = crm_build_payload($lead, $session, $buyerKey, $offerId);

// --- Antifraud. Blocked lead: not sent to CRM, browser gets ok without autologin ---
if (frod_handle($payload, $lead, $buyerResolved, $buyerConfig, $tgToken)) {
    echo json_encode([
        'ok'              => true,
        'blocked'         => true,
        'fire_lead_pixel' => false,
        'crm_response'    => null,
    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (function_exists('fastcgi_finish_request')) {
        fastcgi_finish_request();
    }
    exit;
}

// --- CRM (synchronous) ---
$crm         = crm_push($crmUrl, $apiKey, $payload);
$crmSuccess  = !empty($crm['ok']);
$crmResponse = $crm['response'] ?? null;
$httpCode    = $crm['http_code'] ?? null;

// We answer the browser right after the CRM — auto_login_url travels in crm_response,
// from where footer.php picks it up into the thank-you page URL.
echo json_encode([
    'ok'              => true,
    'crm_ok'          => $crmSuccess,
    'crm_http_code'   => $httpCode,
    'crm_response'    => $crmResponse,
    'fire_lead_pixel' => crm_should_fire_lead_pixel(is_array($crmResponse) ? $crmResponse : null),
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

if (function_exists('fastcgi_finish_request')) {
    fastcgi_finish_request();
} else {
    @ob_flush();
    @flush();
}

// --- Lead in Web Console (panel). Only here: blocked leads exited above; simply opening the thank-you page does not count ---
if (is_file($_SERVER['DOCUMENT_ROOT'] . '/_postback.php')) {
    require_once $_SERVER['DOCUMENT_ROOT'] . '/_postback.php';
    send_postback(['buyer' => $buyerKey, 'funnel' => $offerId, 'crm_ok' => $crmSuccess ? 1 : 0]);
}

// --- After the response is sent: Keitaro sub_id → Telegram ---
if ($crmSuccess && !empty($config['keitaro'])) {
    keitaro_update_after_crm($lead, $session, $server, $rawClick);
}

$tgLead = array_merge($lead, [
    'ip'    => $payload['ip'],
    'subid' => (string) ($lead['subid'] ?? $session['_subid'] ?? ''),
]);
$showCrmLog = $buyerConfig === null || !array_key_exists('show_crm_log', $buyerConfig) || !empty($buyerConfig['show_crm_log']);
$tgText     = tg_build_message($tgLead, $crm, $showCrmLog);

// Lead caught by the browser filter (aff_sub12='SPAM'): the warning goes to both team and buyer.
if (($payload['aff_sub12'] ?? '') === 'SPAM') {
    $tgText = "⚠️ Можливо новий тип фроду: джерело FB, але браузер не Facebook.\n"
        . "Позначено SPAM у CRM.\n"
        . 'Пошта: ' . ($lead['email'] ?? '') . "\n\n"
        . $tgText;
}

if ($buyerConfig) {
    if (!empty($buyerConfig['chat_team_id'])) {
        tg_send($tgToken, $buyerConfig['chat_team_id'], $tgText);
    }
    if (!empty($buyerConfig['chat_id'])) {
        tg_send($tgToken, $buyerConfig['chat_id'], $tgText);
    }
}
