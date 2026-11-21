<?php

/**
 * Job files for autologin polling + lead processing audit.
 * Same format as integration/: job_id, lead, crm_http_code, crm_response, keitaro_update, telegram_*.
 */

function jobs_dir(): string
{
    $dir = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'jobs';
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    return $dir;
}

function job_path(string $jobId): string
{
    return jobs_dir() . DIRECTORY_SEPARATOR . $jobId . '.json';
}

function job_create_id(string $buyer = '', string $subId = ''): string
{
    $buyer = preg_replace('/[^a-zA-Z0-9]/', '', $buyer) ?: 'NOBUYER';
    $subId = preg_replace('/[^a-zA-Z0-9._-]/', '', $subId) ?: 'nosub';

    try {
        $rand = substr(bin2hex(random_bytes(4)), 0, 8);
    } catch (Exception $e) {
        $rand = (string) mt_rand(10000000, 99999999);
    }

    return date('Y-m-d_H-i-s') . '_' . $buyer . '_' . $subId . '_' . $rand;
}

/**
 * Strips PII before the lead is written to the job file (files are publicly reachable):
 *  - phone is removed completely;
 *  - email, first_name, last_name are hashed with SHA-256 (email is normalized).
 * The in-memory $lead is NOT modified — hashing is only for the file.
 */
function job_sanitize_lead(array $lead): array
{
    unset($lead['phone']);

    foreach (['email', 'first_name', 'last_name'] as $k) {
        if (isset($lead[$k]) && $lead[$k] !== '') {
            $value = $k === 'email'
                ? strtolower(trim((string) $lead[$k]))
                : trim((string) $lead[$k]);
            $lead[$k] = hash('sha256', $value);
        }
    }

    return $lead;
}

function job_write(string $jobId, array $data): bool
{
    $path = job_path($jobId);
    $tmp  = $path . '.tmp';
    $json = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    if ($json === false) {
        return false;
    }

    if (@file_put_contents($tmp, $json, LOCK_EX) === false) {
        return false;
    }

    return @rename($tmp, $path);
}

function job_read(string $jobId): ?array
{
    if ($jobId === '' || !preg_match('/^[a-zA-Z0-9._\-]+$/', $jobId)) {
        return null;
    }

    $path = job_path($jobId);
    if (!is_file($path)) {
        return null;
    }

    $raw = @file_get_contents($path);
    if (!is_string($raw) || $raw === '') {
        return null;
    }

    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}

function jobs_gc(int $maxAgeSeconds = 172800): void
{
    if (mt_rand(1, 100) !== 1) {
        return;
    }

    $dir   = jobs_dir();
    $files = @glob($dir . DIRECTORY_SEPARATOR . '*.json');
    if (!is_array($files)) {
        return;
    }

    $now = time();
    foreach (array_slice($files, 0, 100) as $file) {
        $mtime = @filemtime($file);
        if (is_int($mtime) && ($now - $mtime) > $maxAgeSeconds) {
            @unlink($file);
        }
    }
}
