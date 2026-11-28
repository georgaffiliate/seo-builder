<?php

/**
 * Antifraud: per-IP lead limit for selected buyers.
 *
 * A blocked lead:
 *  - is NOT sent to CRM, Keitaro or the buyer chat;
 *  - gets status=done and fire_lead_pixel=false in its job file,
 *    so the landing redirects to "thank you" without the pixel;
 *  - a 🚫 message arrives in the team chat.
 *
 * Counters: storage/frod/<BUYER>_<IP>.txt (the file stores each lead's timestamp, comma-separated).
 */

// Buyers under the limit. max_per_ip — how many leads from one IP we let through per window seconds.
const FROD_RULES = [
    'PUMA' => ['max_per_ip' => 1, 'window' => 7400, 'tg_max' => 3],
    'NEX' => ['max_per_ip' => 1, 'window' => 7400],
    'ART' => ['max_per_ip' => 1, 'window' => 7400],
    'ROX' => ['max_per_ip' => 1, 'window' => 7400],
];
const FROD_SILENT_IPS = [
    '5.46.233.99',
    '45.146.181.2',
];

function frod_dir(): string
{
    $dir = dirname(__DIR__) . '/storage/frod';
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    return $dir;
}

/**
 * Rule for a buyer (by post-resolve nickname or the original one), or null.
 */
function frod_rule(array $buyerResolved): ?array
{
    foreach ([$buyerResolved['key'] ?? '', $buyerResolved['original'] ?? ''] as $name) {
        $name = strtoupper(trim((string) $name));
        if ($name !== '' && isset(FROD_RULES[$name])) {
            return ['buyer' => $name] + FROD_RULES[$name];
        }
    }
    return null;
}

/**
 * Registers a lead from an IP and returns how many leads came from it within the window (including the current one).
 */
function frod_ip_counter(string $buyer, string $ip, int $window): int
{
    $dir  = frod_dir();
    $file = $dir . '/' . $buyer . '_' . str_replace(':', '_', $ip) . '.txt';
    $now  = time();

    // Old-file cleanup, roughly once per 100 leads
    if (mt_rand(1, 100) === 1) {
        foreach (glob($dir . '/*.txt') ?: [] as $f) {
            if (@filemtime($f) < $now - $window) {
                @unlink($f);
            }
        }
    }

    $fh = @fopen($file, 'c+');
    if (!$fh) {
        return 0;
    }
    flock($fh, LOCK_EX);

    $hits = array_filter(explode(',', (string) stream_get_contents($fh)), function ($t) use ($now, $window) {
        return (int) $t > $now - $window;
    });
    $hits[] = $now;

    ftruncate($fh, 0);
    rewind($fh);
    fwrite($fh, implode(',', $hits));
    fflush($fh);
    flock($fh, LOCK_UN);
    fclose($fh);

    return count($hits);
}

/**
 * Main function for api.php.
 * Returns true if the lead was blocked (then api.php must exit).
 */
function frod_handle(
    string $jobId,
    array $payload,
    array $lead,
    array $buyerResolved,
    ?array $buyerConfig,
    string $tgToken
): bool {
    $rule = frod_rule($buyerResolved);
    if ($rule === null) {
        return false;
    }

    $ip = trim((string) ($payload['ip'] ?? ''));
    if ($ip === '' || !filter_var($ip, FILTER_VALIDATE_IP)) {
        return false;
    }

    // IPs on this list — silent block, no notifications
    if (in_array($ip, FROD_SILENT_IPS, true)) {
        job_write($jobId, array_merge(job_read($jobId) ?? [], [
            'status'          => 'done',
            'fire_lead_pixel' => false,
            'blocked'         => strtolower($rule['buyer']) . '_silent_ip',
            'blocked_ip'      => $ip,
            'updated_at'      => date('c'),
        ]));
        return true;
    }

    $count = frod_ip_counter($rule['buyer'], $ip, (int) $rule['window']);
    if ($count <= (int) $rule['max_per_ip']) {
        return false;
    }

    job_write($jobId, array_merge(job_read($jobId) ?? [], [
        'status'          => 'done',
        'fire_lead_pixel' => false,
        'blocked'         => strtolower($rule['buyer']) . '_ip_limit',
        'blocked_ip'      => $ip,
        'blocked_count'   => $count,
        'updated_at'      => date('c'),
    ]));

    // Team chat only, nothing is sent to the buyer.
    // After tg_max blocks from one IP within the window — go quiet.
    $tgMax = (int) ($rule['tg_max'] ?? 0);
    $mute  = $tgMax > 0 && $count > $tgMax;

    if (!$mute && $buyerConfig && !empty($buyerConfig['chat_team_id'])) {
        tg_send(
            $tgToken,
            $buyerConfig['chat_team_id'],
            "🚫 {$rule['buyer']}: повторний лід з IP {$ip} — НЕ відправлено в CRM\n"
            . "Лідів з цього IP за період: {$count}\n"
            . 'Телефон: ' . ($lead['phone'] ?? '')
        );
    }

    return true;
}