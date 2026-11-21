<?php

function buyer_is_valid_key(string $buyer): bool
{
    $buyer = trim($buyer);

    return $buyer !== '' && strpos($buyer, '{') === false;
}

/**
 * @return array{
 *     key: string,
 *     config: ?array,
 *     fallback_used: bool,
 *     original: string
 * }
 */
function buyer_resolve(string $rawBuyer, array $buyerMap, string $defaultBuyer = ''): array
{
    $original = trim($rawBuyer);
    $key      = strtoupper($original);

    if (buyer_is_valid_key($original) && isset($buyerMap[$key])) {
        return [
            'key'           => $key,
            'config'        => $buyerMap[$key],
            'fallback_used' => false,
            'original'      => $original,
        ];
    }

    $fallbackKey = strtoupper(trim($defaultBuyer));
    if ($fallbackKey !== '' && isset($buyerMap[$fallbackKey])) {
        return [
            'key'           => $fallbackKey,
            'config'        => $buyerMap[$fallbackKey],
            'fallback_used' => true,
            'original'      => $original,
        ];
    }

    return [
        'key'           => buyer_is_valid_key($original) ? $key : '',
        'config'        => null,
        'fallback_used' => false,
        'original'      => $original,
    ];
}
