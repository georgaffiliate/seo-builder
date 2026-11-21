<?php

function crm_push(string $apiUrl, string $apiKey, array $payload): array
{
    $raw = null;
    $httpCode = 0;

    for ($attempt = 1; $attempt <= 2; $attempt++) {
        $ch = curl_init($apiUrl);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST           => true,
            CURLOPT_HTTPHEADER     => [
                'Authorization: ' . $apiKey,
                'Content-Type: application/json',
            ],
            CURLOPT_POSTFIELDS     => json_encode($payload),
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

    $ok = ($httpCode >= 200 && $httpCode < 300) || !empty($response['lead_uuid']);
    if (crm_is_duplication_error($response)) {
        $ok = false;
    }

    $autologin = '';
    if (!empty($response['auto_login_url']) && is_string($response['auto_login_url'])) {
        $autologin = $response['auto_login_url'];
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
    $data = $response['data'] ?? null;
    if (!is_array($data)) {
        return '';
    }

    $errorType = $data['errorType'] ?? $data['error_type'] ?? '';
    return is_string($errorType) ? strtoupper(trim($errorType)) : '';
}

function crm_is_duplication_error(?array $response): bool
{
    if (!is_array($response)) {
        return false;
    }

    $errorType = crm_get_error_type($response);
    if (in_array($errorType, ['CRM_DUPLICATION_ERROR', 'DUPLICATION_ERROR'], true)) {
        return true;
    }

    $data = $response['data'] ?? null;
    if (!is_array($data)) {
        return false;
    }

    $message = strtolower((string) ($data['errorMessage'] ?? $data['error_message'] ?? ''));
    if ($message === '') {
        return false;
    }

    return strpos($message, 'already exist') !== false
        || strpos($message, 'duplication') !== false;
}

function crm_should_fire_lead_pixel(?array $response): bool
{
    return !crm_is_duplication_error($response);
}

function crm_build_payload(array $lead, array $session, string $buyerKey, string $offerId): array
{
    $firstName = (string) ($lead['first_name'] ?? $lead['first'] ?? '');
    $lastName  = (string) ($lead['last_name'] ?? $lead['last'] ?? '');
    $email     = (string) ($lead['email'] ?? '');

    $phone = trim((string) ($lead['phone'] ?? ''));
    if ($phone !== '' && $phone[0] === '+') {
        $phone = '+' . preg_replace('/\D/', '', substr($phone, 1));
    } else {
        $phone = preg_replace('/\D/', '', $phone);
    }

    $countryCode  = strtoupper(trim((string) ($lead['country'] ?? '')));
    $leadLanguage = strtolower(trim((string) ($lead['lang'] ?? '')));
    $ipValue      = $_SERVER['HTTP_CF_CONNECTING_IP'] ?? $_SERVER['REMOTE_ADDR'] ?? '';
    $domainValue  = trim((string) ($lead['domain'] ?? ''));
    $clickId      = trim((string) ($lead['fbclid'] ?? $lead['external_id'] ?? ''));

    $password = crm_generate_password();

    // --- SPAM mark for buyer POL on short time_on_page ---
    $timeOnPageSeconds = max(0, (int) ($lead['time_on_page'] ?? 0));
    $isPolBuyer         = strtoupper(trim((string) ($lead['buyer'] ?? ''))) === '000'; // removed the label comparison
    $spamLabel           = ($isPolBuyer && $timeOnPageSeconds < 60) ? 'SPAM' : '';
    // -------------------------------------------------------------

    $payload = [
        'ip'           => $ipValue,
        'email'        => $email,
        'first_name'   => $firstName,
        'last_name'    => $lastName,
        'password'     => $password,
        'phone'        => $phone,
        'affiliate_id' => $buyerKey,
        'offer_id'     => $offerId,
        'aff_sub'      => $clickId,
        'aff_sub2'     => (string) ($lead['funnel'] ?? ''),
        'aff_sub3'     => (string) ($lead['subid'] ?? $session['_subid'] ?? ''),
        'aff_sub4'     => (string) ($lead['pixel'] ?? ''),
        'aff_sub5'     => (string) ($lead['ad_name'] ?? ''),
        'aff_sub6'     => (string) ($lead['utm_campaign'] ?? ''),
        'aff_sub7'     => (string) ($lead['utm_source'] ?? ''),
        'aff_sub8'     => (string) ($lead['utm_placement'] ?? ''),
        'aff_sub9'     => (string) ($lead['adset_name'] ?? ''),
        'aff_sub10'    => (string) ($lead['ad_id'] ?? ''),
        'aff_sub11'    => $domainValue,
        'aff_sub12'    => $spamLabel,
        'aff_sub13'    => '',
    ];

    if ($countryCode !== '') {
        $payload['country_code'] = $countryCode;
    }
    if ($leadLanguage !== '') {
        $payload['lead_language'] = $leadLanguage;
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