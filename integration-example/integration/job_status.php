<?php
header('Content-Type: application/json; charset=UTF-8');
error_reporting(E_ALL & ~E_DEPRECATED);

require_once __DIR__ . '/lib/jobs.php';
require_once __DIR__ . '/lib/crm.php';

$jobId = trim((string) ($_GET['job_id'] ?? ''));
if ($jobId === '' || !preg_match('/^[a-zA-Z0-9._\-]+$/', $jobId)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'invalid_job_id'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

$job = job_read($jobId);
if (!$job) {
    http_response_code(404);
    echo json_encode(['ok' => false, 'error' => 'job_not_found'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

$status = (string) ($job['status'] ?? 'unknown');
$crm = is_array($job['crm_response'] ?? null) ? $job['crm_response'] : null;
$crmReady = in_array($status, ['crm_success', 'crm_failed', 'done'], true);

$autologin = '';
if ($crm && !empty($crm['auto_login_url']) && is_string($crm['auto_login_url'])) {
    $autologin = $crm['auto_login_url'];
}

$fireLeadPixel = null;
if ($crmReady) {
    if (array_key_exists('fire_lead_pixel', $job)) {
        $fireLeadPixel = !empty($job['fire_lead_pixel']);
    } else {
        $fireLeadPixel = crm_should_fire_lead_pixel($crm);
    }
}

echo json_encode([
    'ok'              => true,
    'job_id'          => $jobId,
    'status'          => $status,
    'crm_ready'       => $crmReady,
    'fire_lead_pixel' => $fireLeadPixel,
    'autologin'       => $autologin,
    'crm_http_code'   => $job['crm_http_code'] ?? null,
    'updated_at'      => $job['updated_at'] ?? null,
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
