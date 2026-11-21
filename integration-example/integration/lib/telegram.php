<?php

function tg_send(string $botToken, string $chatId, string $text): array
{
    if ($botToken === '' || $chatId === '') {
        return ['ok' => false, 'reason' => 'empty_config'];
    }

    $ch = curl_init('https://api.telegram.org/bot' . $botToken . '/sendMessage');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode([
            'chat_id'                  => $chatId,
            'text'                     => $text,
            'parse_mode'               => 'HTML',
            'disable_web_page_preview' => true,
        ]),
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
        CURLOPT_TIMEOUT        => 5,
        CURLOPT_CONNECTTIMEOUT => 3,
    ]);

    $result = curl_exec($ch);
    $code   = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    return [
        'ok'        => $result !== false && $code >= 200 && $code < 300,
        'http_code' => $code,
    ];
}

function tg_escape(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_HTML5, 'UTF-8');
}

function tg_has_value($value): bool
{
    $value = trim((string) $value);
    if ($value === '' || $value === '—') {
        return false;
    }

    return strpos($value, '{') === false;
}

function tg_crm_status_text(array $crmBody, bool $crmOk = false): string
{
    if (!empty($crmBody['status']) && is_string($crmBody['status'])) {
        return $crmBody['status'];
    }
    if ($crmOk) {
        return 'success';
    }
    if (!empty($crmBody['message']) && is_string($crmBody['message'])) {
        return $crmBody['message'];
    }
    if (!empty($crmBody['data']['errorMessage']) && is_string($crmBody['data']['errorMessage'])) {
        return $crmBody['data']['errorMessage'];
    }
    if (!empty($crmBody['name']) && is_string($crmBody['name'])) {
        return $crmBody['name'];
    }
    return '—';
}

function tg_crm_pick_string(array $body, array $paths): string
{
    foreach ($paths as $path) {
        $node = $body;
        foreach ($path as $key) {
            if (!is_array($node) || !array_key_exists($key, $node)) {
                $node = null;
                break;
            }
            $node = $node[$key];
        }
        if (is_string($node) && trim($node) !== '') {
            return trim($node);
        }
    }

    return '';
}

function tg_crm_summary_rows(array $crmResult, bool $crmOk): array
{
    $crmBody  = is_array($crmResult['response'] ?? null) ? $crmResult['response'] : [];
    $httpCode = (string) ($crmResult['http_code'] ?? '');

    $rows = [];
    if ($httpCode !== '' && $httpCode !== '0') {
        $rows[] = ['label' => 'HTTP', 'value' => $httpCode];
    }

    $uuid = tg_crm_pick_string($crmBody, [
        ['lead_uuid'],
        ['data', 'lead_uuid'],
    ]);

    if ($crmOk) {
        if ($uuid !== '') {
            $rows[] = ['label' => 'UUID', 'value' => $uuid];
        }

        return $rows;
    }

    $message = tg_crm_pick_string($crmBody, [['message']]);
    if ($message !== '') {
        $rows[] = ['label' => 'Error', 'value' => $message];
    }

    $errorMessage = tg_crm_pick_string($crmBody, [
        ['data', 'errorMessage'],
        ['data', 'error_message'],
    ]);
    if ($errorMessage !== '') {
        $rows[] = ['label' => 'Message', 'value' => $errorMessage];
    }

    if ($uuid !== '' && $errorMessage === '') {
        $rows[] = ['label' => 'UUID', 'value' => $uuid];
    }

    if (count($rows) === 1) {
        $fallback = tg_crm_status_text($crmBody, false);
        if ($fallback !== '—') {
            $rows[] = ['label' => 'Status', 'value' => $fallback];
        }
    }

    return $rows;
}

function tg_tree_lines(array $rows, bool $showAll = false): array
{
    $visible = [];
    foreach ($rows as $row) {
        if (!$showAll && !tg_has_value($row['value'] ?? '')) {
            continue;
        }
        $visible[] = $row;
    }

    $lines = [];
    $last  = count($visible) - 1;
    foreach ($visible as $i => $row) {
        $value = trim((string) ($row['value'] ?? ''));
        if ($showAll && $value === '') {
            $value = '—';
        }
        $prefix  = $i === $last ? '└' : '├';
        $lines[] = $prefix . ' ' . $row['label'] . ': ' . tg_escape($value);
    }

    return $lines;
}

function tg_build_message(array $lead, array $crmResult, bool $showCrmLog = true): string
{
    $clean = static function ($value): string {
        if ($value === null || $value === '') {
            return '';
        }
        $value = urldecode((string) $value);
        $value = html_entity_decode($value, ENT_QUOTES | ENT_HTML5, 'UTF-8');
        return trim($value);
    };

    $crmOk = !empty($crmResult['ok']);

    $statusLine = $crmOk ? '✅ LEAD ACCEPTED' : '❌ LEAD REJECTED';
    $fullName   = trim($clean($lead['first_name'] ?? '') . ' ' . $clean($lead['last_name'] ?? ''));

    $lines = [
        $statusLine,
        '━━━━━━━━━━━━━━━━━━',
    ];

 if (!empty($lead['buyer_original'])) {
    $original = tg_escape(trim((string) $lead['buyer_original']));
    if ($original === '') {
        $original = '—';
    }
    $lines[] = '⚠️ Buyer fallback: «' . $original . '» → ' . tg_escape((string) ($lead['buyer'] ?? '')) . ' @obmtech';
}

    $lines[] = 'Source: SEO';
    $lines[] = '';
    $lines[] = '👤 Контакт';

    $lines = array_merge($lines, tg_tree_lines([
        ['label' => 'Имя', 'value' => $fullName],
        ['label' => 'Email', 'value' => $clean($lead['email'] ?? '')],
     //   ['label' => 'Phone', 'value' => $clean($lead['phone'] ?? '')],
        ['label' => 'IP', 'value' => $clean($lead['ip'] ?? '')],
    ]));
    
    $lines[] = '';
    $lines[] = '📊 Оффер';

    $lines = array_merge($lines, tg_tree_lines([
        ['label' => 'Buyer', 'value' => $clean($lead['buyer'] ?? '')],
        ['label' => 'Funnel', 'value' => $clean($lead['funnel'] ?? '')],
        ['label' => 'Offer ID', 'value' => $clean($lead['offer_name'] ?? '')],
        ['label' => 'Keitaro Campaign ID', 'value' => $clean($lead['keitaro_campaign_id'] ?? '')],
        ['label' => 'Keitaro Campaign', 'value' => $clean($lead['keitaro_campaign_name'] ?? '')],
        ['label' => 'Страна', 'value' => $clean($lead['country'] ?? '')],
        ['label' => 'Язык', 'value' => $clean($lead['lang'] ?? '')],
        ['label' => 'Домен', 'value' => $clean($lead['domain'] ?? '')],
    ]));

    $lines[] = '';
    $lines[] = '🏷️ CRM';
    $lines   = array_merge($lines, tg_tree_lines(tg_crm_summary_rows($crmResult, $crmOk)));

    if ($showCrmLog) {
        $logPayload = [
            'http_code' => $crmResult['http_code'] ?? null,
            'response'  => $crmResult['response'] ?? null,
        ];
        $jsonLog = json_encode($logPayload, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
        if ($jsonLog === false) {
            $jsonLog = '{}';
        }

        $lines[] = '';
        $lines[] = '📋 CRM response log';
        $lines[] = '<pre>' . tg_escape($jsonLog) . '</pre>';
    }

    return implode("\n", $lines);
}
