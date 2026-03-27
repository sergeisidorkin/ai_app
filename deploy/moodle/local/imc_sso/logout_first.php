<?php

// phpcs:ignore moodle.Files.RequireLogin.Missing
require_once(__DIR__ . '/../../config.php');

$PAGE->set_url('/local/imc_sso/logout_first.php');
$PAGE->set_context(context_system::instance());

$next = optional_param('next', '/auth/oidc/?source=django', PARAM_LOCALURL);

require_logout();

redirect(new moodle_url($next));
