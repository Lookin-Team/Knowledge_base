<?php
// Local first-run setup only. Reads a protected, Git-ignored synthetic credential file.
require __DIR__ . '/../vendor/autoload.php';
$app = require __DIR__ . '/../bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
if (config('app.env') !== 'local' || config('app.url') !== 'http://127.0.0.1:8080') {
    throw new RuntimeException('This helper is restricted to the reviewed local environment.');
}
$credentials = json_decode(file_get_contents(__DIR__ . '/private/admin.json'), true, flags: JSON_THROW_ON_ERROR);
$user = BookStack\Users\Models\User::query()->where('email', 'admin@admin.com')->first();
if (!$user) {
    throw new RuntimeException('Default admin not found; refusing to change any other account.');
}
if (!Illuminate\Support\Facades\Hash::check('password', $user->password)) {
    throw new RuntimeException('Admin password has already changed; refusing to overwrite it.');
}
$user->name = 'Local administrator';
$user->email = $credentials['email'];
$user->password = Illuminate\Support\Facades\Hash::make($credentials['password']);
$user->save();
echo "Default local administrator credentials replaced.\n";
