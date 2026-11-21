<?php
/**
 * Trackbox CRM adapter — drop-in replacement for lib/crm.php used by api-tb.php.
 * Exposes the same function names as crm.php so the rest of the pipeline
 * (job_write / keitaro_update / tg_send) doesn't need to change.
 *
 * Docs: https://intercom.help/tigloo/en/articles/9349579-trackbox-api-documentation
 *
 * Endpoint: POST /api/signup/procform
 * Auth:     headers x-trackbox-username / x-trackbox-password (+ optional x-api-key)
 * Body:     ai / ci / gi + userip / firstname / lastname / email / password / phone + optional
 */

function crm_push(string $apiUrl, string $auth, array $payload): array
{
    // $auth is a JSON string with username / password / api_key so we can keep
    // the crm_push(url, apiKey, payload) signature that api-tb.php uses.
    $creds = json_decode($auth, true) ?: [];
    $username = (string) ($creds['username'] ?? '');
    $password = (string) ($creds['password'] ?? '');
    $apiKey   = (string) ($creds['api_key']  ?? '');

    $headers = [
        'x-trackbox-username: ' . $username,
        'x-trackbox-password: ' . $password,
        'Content-Type: application/json',
    ];
    if ($apiKey !== '') {
        $headers[] = 'x-api-key: ' . $apiKey;
    }

    $raw = null;
    $httpCode = 0;

    for ($attempt = 1; $attempt <= 2; $attempt++) {
        $ch = curl_init($apiUrl);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST           => true,
            CURLOPT_HTTPHEADER     => $headers,
            CURLOPT_POSTFIELDS     => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            CURLOPT_TIMEOUT        => 40,
            CURLOPT_CONNECTTIMEOUT => 5,
        ]);

        $raw = curl_exec($ch);
        $httpCode = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($raw !== false && $httpCode >= 200 && $httpCode < 300) {
            break;
        }

        if ($attempt < 2 && ($raw === false || $httpCode >= 500 || $httpCode === 0)) {
            usleep(350000);
            continue;
        }
        break;
    }

    $response = is_string($raw) ? json_decode($raw, true) : null;
    if (!is_array($response)) {
        $response = ['raw' => $raw];
    }

    $ok = ($httpCode >= 200 && $httpCode < 300);
    if ($ok && is_array($response)) {
        // Trackbox may return { success: false, message: "..." } inside 200
        if (isset($response['success']) && $response['success'] === false) {
            $ok = false;
        }
        if (isset($response['status']) && strtolower((string) $response['status']) === 'error') {
            $ok = false;
        }
    }
    if (crm_is_duplication_error($response)) {
        $ok = false;
    }

    // Auto-login URL — Trackbox tigloo returns it in `data` (top-level string)
    // AND under addonData.data.loginURL. Try every plausible shape.
    $autologin = '';
    // (a) top-level keys with URL string
    foreach (['auto_login_url', 'autologinurl', 'autoLoginUrl', 'redirect_to', 'redirect', 'redirectUrl', 'redirect_url', 'member_url', 'login_url', 'loginUrl'] as $key) {
        if (!empty($response[$key]) && is_string($response[$key])
            && preg_match('#^https?://#', $response[$key])) {
            $autologin = $response[$key];
            break;
        }
    }
    // (b) Trackbox tigloo: `data` at top-level is the login URL as a string
    if ($autologin === '' && !empty($response['data']) && is_string($response['data'])
        && preg_match('#^https?://#', $response['data'])) {
        $autologin = $response['data'];
    }
    // (c) Trackbox nested addonData.data.loginURL / brokerUrl
    if ($autologin === '' && !empty($response['addonData']['data']) && is_array($response['addonData']['data'])) {
        foreach (['loginURL', 'auto_login_url', 'autoLoginUrl', 'brokerUrl', 'redirect', 'redirect_to', 'login_url'] as $key) {
            $v = $response['addonData']['data'][$key] ?? null;
            if (!empty($v) && is_string($v) && preg_match('#^https?://#', $v)) {
                $autologin = $v;
                break;
            }
        }
    }
    // (d) Legacy: some CRMs nest under top-level `data` array
    if ($autologin === '' && !empty($response['data']) && is_array($response['data'])) {
        foreach (['auto_login_url', 'autoLoginUrl', 'redirect', 'redirect_to', 'login_url', 'loginURL'] as $key) {
            $v = $response['data'][$key] ?? null;
            if (!empty($v) && is_string($v) && preg_match('#^https?://#', $v)) {
                $autologin = $v;
                break;
            }
        }
    }

    // Normalise into the shape api.php's downstream code expects
    // (crm_response.auto_login_url is what thx.php reads for polling)
    if ($autologin !== '' && empty($response['auto_login_url'])) {
        $response['auto_login_url'] = $autologin;
    }

    return [
        'ok'             => $ok,
        'http_code'      => $httpCode,
        'response'       => $response,
        'autologin'      => $autologin,
        'is_duplication' => crm_is_duplication_error($response),
    ];
}

function crm_get_error_type(array $response): string
{
    // Trackbox: error usually inside data.error or top-level error/message
    $candidates = [];
    if (isset($response['error']))   $candidates[] = $response['error'];
    if (isset($response['message'])) $candidates[] = $response['message'];
    $data = $response['data'] ?? null;
    if (is_array($data)) {
        foreach (['errorType', 'error_type', 'error', 'message'] as $key) {
            if (isset($data[$key])) $candidates[] = $data[$key];
        }
    }
    foreach ($candidates as $c) {
        if (is_string($c) && $c !== '') {
            return strtoupper(trim($c));
        }
    }
    return '';
}

function crm_is_duplication_error(?array $response): bool
{
    if (!is_array($response)) {
        return false;
    }

    // Look at every plausible message field, lowercase, and match substrings.
    $texts = [];
    foreach (['error', 'message', 'error_message', 'errorMessage', 'reason'] as $key) {
        if (isset($response[$key]) && is_string($response[$key])) {
            $texts[] = strtolower($response[$key]);
        }
    }
    if (!empty($response['data']) && is_array($response['data'])) {
        foreach (['error', 'message', 'error_message', 'errorMessage', 'reason', 'errorType', 'error_type'] as $key) {
            if (isset($response['data'][$key]) && is_string($response['data'][$key])) {
                $texts[] = strtolower($response['data'][$key]);
            }
        }
    }

    foreach ($texts as $t) {
        if (strpos($t, 'already exist') !== false)   return true;
        if (strpos($t, 'already registered') !== false) return true;
        if (strpos($t, 'duplicat') !== false)         return true;
        if (strpos($t, 'email exists') !== false)     return true;
        if (strpos($t, 'phone exists') !== false)     return true;
    }
    return false;
}

function crm_should_fire_lead_pixel(?array $response): bool
{
    return !crm_is_duplication_error($response);
}

/**
 * Map our internal lead → Trackbox /api/signup/procform body.
 *
 * The $buyerKey (e.g. TEST/TLH/DMA) is stuffed into MPC_5 so buyer resolution
 * still works downstream (Telegram uses it too). Funnel goes into `so`.
 */
function crm_build_payload(array $lead, array $session, string $buyerKey, string $offerId): array
{
    $firstName = (string) ($lead['first_name'] ?? $lead['first'] ?? '');
    $lastName  = (string) ($lead['last_name']  ?? $lead['last']  ?? '');
    $email     = (string) ($lead['email'] ?? '');

    $phone = trim((string) ($lead['phone'] ?? ''));
    // Trackbox docs example shows phone WITHOUT the leading + (44...), so we strip it.
    $phone = preg_replace('/\D/', '', $phone);

    $countryCode  = strtoupper(trim((string) ($lead['country'] ?? '')));
    $leadLanguage = strtoupper(trim((string) ($lead['lang'] ?? '')));
    $ipValue      = (string) ($lead['ip'] ?? ($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0'));
    $domainValue  = trim((string) ($lead['domain'] ?? ''));
    $clickId      = trim((string) ($lead['fbclid'] ?? $lead['external_id'] ?? ''));
    $subId        = (string) ($lead['subid'] ?? $session['_subid'] ?? '');

    $password = crm_generate_password();

    // Trackbox required core
    $payload = [
        'ai'        => (string) ($lead['_tb_ai'] ?? ''),   // filled from api-tb.php config
        'ci'        => (string) ($lead['_tb_ci'] ?? ''),
        'gi'        => (string) ($lead['_tb_gi'] ?? ''),
        'userip'    => $ipValue,
        'firstname' => $firstName,
        'lastname'  => $lastName,
        'email'     => $email,
        'password'  => $password,
        'phone'     => $phone,
    ];

    // Optional statistical fields (visible in Trackbox reports)
    if ($offerId !== '')      $payload['so']       = $offerId;
    if ($subId !== '')        $payload['sub']      = $subId;
    if ($clickId !== '')      $payload['term']     = $clickId;
    if (!empty($lead['ad_name']))       $payload['ad']       = (string) $lead['ad_name'];
    if (!empty($lead['utm_campaign']))  $payload['campaign'] = (string) $lead['utm_campaign'];
    if (!empty($lead['utm_source']))    $payload['medium']   = (string) $lead['utm_source'];
    if ($leadLanguage !== '') $payload['lg'] = $leadLanguage;

    // Free MPC slots — keep parity with what crm.php packed into aff_sub2..13
    $payload['MPC_1']  = (string) ($lead['pixel'] ?? '');
    $payload['MPC_2']  = (string) ($lead['adset_name'] ?? '');
    $payload['MPC_3']  = (string) ($lead['ad_id'] ?? '');
    $payload['MPC_4']  = (string) ($lead['utm_placement'] ?? '');
    $payload['MPC_5']  = $buyerKey;
    $payload['MPC_6']  = $domainValue;
    $payload['MPC_7']  = (string) ($lead['funnel'] ?? '');
    $payload['MPC_8']  = $countryCode;

    // Strip empty optionals (keeps request tight)
    foreach ($payload as $k => $v) {
        if ($v === '' && !in_array($k, ['ai', 'ci', 'gi', 'userip', 'firstname', 'lastname', 'email', 'password', 'phone'], true)) {
            unset($payload[$k]);
        }
    }

    return $payload;
}

function crm_generate_password(int $length = 10): string
{
    $lower   = 'abcdefghijklmnopqrstuvwxyz';
    $upper   = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    $digits  = '0123456789';
    $special = '!@#$%^&*()_-=+';
    $chars   = [
        $lower[mt_rand(0, 25)],
        $upper[mt_rand(0, 25)],
        $digits[mt_rand(0, 9)],
        $special[mt_rand(0, strlen($special) - 1)],
    ];
    $all = $lower . $upper . $digits . $special;
    for ($i = 4; $i < $length; $i++) {
        $chars[] = $all[mt_rand(0, strlen($all) - 1)];
    }
    shuffle($chars);
    return implode('', $chars);
}
