# Existing, verified VPS image; release tool verifies its immutable image ID before build.
FROM lookin-base-app:v26.09.2-ui20261102-2
USER root
COPY local-dev/theme/functions.php /app/themes/lookin-base/functions.php
COPY local-dev/theme/proposals /app/themes/lookin-base/proposals
COPY local-dev/theme/home/default.blade.php /app/themes/lookin-base/home/default.blade.php
COPY local-dev/theme/lookin/sidebar.blade.php /app/themes/lookin-base/lookin/sidebar.blade.php
COPY scripts/install-proposals.php /app/scripts/install-proposals.php
USER 1000:1000
