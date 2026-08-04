<?php

declare(strict_types=1);

$host = getenv('NEXTCLOUD_HOST') ?: 'localhost';
$context = stream_context_create([
    'http' => [
        'header' => "Host: {$host}\r\n",
        'ignore_errors' => true,
        'timeout' => 5,
    ],
]);
$body = @file_get_contents('http://127.0.0.1/status.php', false, $context);
$statusLine = $http_response_header[0] ?? '';
$status = is_string($body) ? json_decode($body, true) : null;
$isSuccessfulResponse = preg_match('/^HTTP\/\S+\s+2\d\d(?:\s|$)/', $statusLine) === 1;
$isInstalled = is_array($status) && ($status['installed'] ?? false) === true;

exit($isSuccessfulResponse && $isInstalled ? 0 : 1);
