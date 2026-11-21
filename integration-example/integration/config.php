<?php
/**
 * Integration config: CRM, Telegram, buyer map.
 * CANONICAL EXAMPLE — copy to <offer>/api_local/integration/config.php and fill placeholders.
 * NEVER change lib/crm.php aff_sub11: CRM always gets 'google.com'; real host goes to Telegram only.
 */
return [
    'crm_api_url'   => 'https://yourleads.org/api/affiliates/v2/leads',
    'fixed_api_key' => 'a91aa258-be50-453c-b81b-afdbd059c299',
    'tg_bot_token'  => '8374261466:AAEcvD648TQNYRpSxVjULW02y-0tCk67P-M',

    // default_buyer — fallback used when buyer is empty or absent from buyers
    'default_buyer' => 'PUMA',

    // Values sent with the lead straight from this config (no Keitaro needed)
    'country'        => '{{CC}}',           // e.g. IT / PL / CZ / HU / NL
    'lang'           => '{{LANG}}',         // e.g. it / pl / cs
    'funnel'         => '{{FUNNEL}}',       // clean brand token CAPS, no geo prefix, no TLD (QUANTRIVIERAZ)
    'domain'         => '',                 // '' = real host from location.hostname → Telegram; CRM gets google.com
    'buyer'          => 'PUMA',             // static per playbook

    // Pixels in <head> (header.php). Work on Keitaro macros {ts_id}/{pixel}; without Keitaro keep false.
    'header_pixels'  => false,
    'facebook_pixel' => false,    // only effective when header_pixels = true

    // Update tokens/sub_id in Keitaro after successful lead (lib/keitaro.php).
    'keitaro'        => false,

    // Job polling on the thank-you page (job_status.php). api.php is synchronous now.
    'job_polling'    => false,

    // Autologin redirect on the thank-you page (redirect to auto_login_url from CRM).
    'autologin_redirect'          => true,
    'autologin_redirect_delay_ms' => 10000,

    // Which hidden-field groups to send. Default: base only — 5 fields.
    //   base    — country, lang, funnel, domain, buyer
    //   ads     — utm_*, campaign_id/adset_id/ad_id/*_name
    //   fb      — fbclid
    //   device  — user_agent, time_on_page, ttclid
    //   keitaro — subid, pixel, keitaro_*, catalog_*, bbg, os, idfa, gaid
    'lead_fields'    => ['base'],

    'buyers' => [
        "PUMA" => [
            "crm_token"     => "wuf2w5jf6ajv4xxlyk42cgfqv32kq6c94",
            "chat_id"       => "9275946896",
            "chat_team_id"  => "-5282358980",
            "show_crm_log"  => true,
        ]
    ],
];
