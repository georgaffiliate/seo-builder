<?php

function keitaro_hash(?string $value, string $type = 'default'): string
{
    $value = trim((string) $value);
    if ($value === '') {
        return '';
    }

    switch ($type) {
        case 'email':
            $value = mb_strtolower($value);
            break;
        case 'phone':
            $value = preg_replace('/\D+/', '', $value);
            break;
        case 'name':
        case 'state':
        default:
            $value = mb_strtolower($value);
            break;
    }

    if ($value === '') {
        return '';
    }

    return hash('sha256', $value);
}

function keitaro_sanitize_user_agent($value): string
{
    if ($value === null) {
        return '';
    }

    $value = trim((string) $value);
    if ($value === '') {
        return '';
    }

    if (!mb_check_encoding($value, 'UTF-8')) {
        $value = mb_convert_encoding($value, 'UTF-8', 'UTF-8');
    }

    $converted = @iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $value);
    if ($converted === false || $converted === '') {
        $converted = preg_replace('/[^\x20-\x7E]+/', ' ', $value);
        $converted = trim(preg_replace('/\s+/', ' ', (string) $converted));
    }

    if (strlen($converted) > 1024) {
        $converted = substr($converted, 0, 1024);
    }

    return $converted;
}

function keitaro_tracker_context(array $lead, array $session, array $server, array $rawClick): array
{
    $subId = trim((string) ($lead['subid'] ?? $session['_subid'] ?? ''));
    $host  = trim((string) ($server['HTTP_HOST'] ?? $rawClick['domain'] ?? $lead['domain'] ?? ''));
    $scheme = 'https';

    $referer = trim((string) ($server['HTTP_REFERER'] ?? ''));
    if ($referer !== '') {
        $parsed = parse_url($referer, PHP_URL_SCHEME);
        if (is_string($parsed) && $parsed !== '') {
            $scheme = $parsed;
        }
    } elseif (empty($_SERVER['HTTPS']) || $_SERVER['HTTPS'] === 'off') {
        $scheme = 'http';
    }

    return [
        'sub_id'  => $subId,
        'host'    => $host,
        'scheme'  => $scheme,
    ];
}

function keitaro_build_params(array $lead): array
{
    $email     = (string) ($lead['email'] ?? '');
    $firstName = (string) ($lead['first_name'] ?? $lead['first'] ?? '');
    $lastName  = (string) ($lead['last_name'] ?? $lead['last'] ?? '');
    $rawPhone  = (string) ($lead['phone'] ?? '');
    $state     = (string) ($lead['state'] ?? $lead['st'] ?? '');

    $fbclid    = trim((string) ($lead['fbclid'] ?? ''));
    $fbc       = trim((string) ($lead['fbc'] ?? ''));
    $fbp       = trim((string) ($lead['fbp'] ?? ''));
    $domain    = trim((string) ($lead['domain'] ?? ''));
    $userAgent = trim((string) ($lead['user_agent'] ?? ''));

    // --- new additions ---
    $subid = (string) ($lead['subid'] ?? '');

    $clientIp = $_SERVER['HTTP_CF_CONNECTING_IP'] ?? $_SERVER['REMOTE_ADDR'] ?? '';
    $clientIp = filter_var($clientIp, FILTER_VALIDATE_IP) ? $clientIp : '';

    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $referer = trim((string) ($_SERVER['HTTP_REFERER'] ?? ''));
    $eventSourceUrl = $referer !== '' ? $referer : ($domain !== '' ? $scheme . '://' . $domain : '');
    // --- end of new additions ---

    return [
        'extra_param_4' => $fbclid,
        'extra_param_5' => $_COOKIE['_fbc'] ?? $fbc,
        'extra_param_6' => $_COOKIE['_fbp'] ?? $fbp,
        'sub_id_12' => $domain,
        'sub_id_13' => keitaro_sanitize_user_agent($userAgent),
        'sub_id_14' => keitaro_hash($email, 'email'),
        'sub_id_15' => keitaro_hash($rawPhone, 'phone'),
        'extra_param_1' => keitaro_hash($lastName, 'name'),
        'extra_param_2' => keitaro_hash($firstName, 'name'),
        'extra_param_3' => keitaro_hash($state, 'state'),
        'extra_param_7' => keitaro_hash($subid, 'external_id'),
        'extra_param_8' => $clientIp,
        'extra_param_9' => $eventSourceUrl,
    ];
}
function keitaro_update_tokens(array $params, string $subId, string $trackerHost, string $scheme = 'https'): array
{
    if ($subId === '') {
        return ['ok' => false, 'reason' => 'empty_subid'];
    }

    if ($trackerHost === '') {
        return ['ok' => false, 'reason' => 'empty_tracker_host'];
    }

    $params = array_filter($params, static function ($value) {
        return $value !== null && $value !== '';
    });

    if (!$params) {
        return ['ok' => false, 'reason' => 'empty_params'];
    }

    $url = $scheme . '://' . $trackerHost
        . '/?_update_tokens=1&sub_id=' . urlencode($subId)
        . '&' . http_build_query($params);

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 5,
        CURLOPT_CONNECTTIMEOUT => 3,
        CURLOPT_FOLLOWLOCATION => true,
    ]);

    $result    = curl_exec($ch);
    $httpCode  = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlError = curl_error($ch);
    curl_close($ch);

    return [
        'ok'         => $result !== false && $httpCode >= 200 && $httpCode < 300,
        'http_code'  => $httpCode ?: null,
        'curl_error' => $curlError ?: null,
        'response'   => $result !== false ? $result : null,
    ];
}

function keitaro_update_after_crm(array $lead, array $session, array $server, array $rawClick): array
{
    $ctx = keitaro_tracker_context($lead, $session, $server, $rawClick);
    if ($ctx['sub_id'] === '' || $ctx['host'] === '') {
        return ['ok' => false, 'reason' => 'empty_tracker_context'];
    }

    return keitaro_update_tokens(
        keitaro_build_params($lead),
        $ctx['sub_id'],
        $ctx['host'],
        $ctx['scheme']
    );
}