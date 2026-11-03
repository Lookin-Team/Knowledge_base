<?php
// Run explicitly: php scripts/install-proposals.php. Never executed on a web request.
require __DIR__ . '/../vendor/autoload.php';
$app = require __DIR__ . '/../bootstrap/app.php';
$app->make(\Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$schema = \Illuminate\Support\Facades\Schema::getFacadeRoot();
if (!$schema->hasTable('lookin_publication_proposals')) {
    $schema->create('lookin_publication_proposals', function ($t) {
        $t->bigIncrements('id');
        $t->unsignedInteger('author_id')->index();
        $t->string('kind', 20);
        $t->string('title');
        $t->longText('body');
        $t->unsignedInteger('shelf_id')->nullable();
        $t->string('direction')->default('');
        $t->text('hashtags');
        $t->longText('original');
        $t->string('status', 20)->index();
        $t->unsignedInteger('moderator_id')->nullable();
        $t->unsignedInteger('page_id')->nullable();
        $t->text('reason')->nullable();
        $t->timestamp('decided_at')->nullable();
        $t->timestamps();
    });
    echo "Proposal table created.\n";
} else {
    echo "Proposal table already exists; preserved.\n";
}

if (!$schema->hasTable('lookin_proposal_files')) {
    $schema->create('lookin_proposal_files', function ($t) {
        $t->bigIncrements('id');
        $t->unsignedBigInteger('proposal_id')->index();
        $t->string('name');
        $t->string('mime', 100);
        $t->unsignedInteger('size');
        $t->longText('content');
        $t->unsignedInteger('attachment_id')->nullable();
        $t->timestamp('created_at');
    });
    echo "Private proposal files table created.\n";
}
