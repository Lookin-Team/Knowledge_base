"""Create only synthetic local settings. Refuses to overwrite an existing .env."""
from pathlib import Path
import base64
import os
import secrets
root = Path(__file__).resolve().parent.parent
text = (root / "local-dev/env.example").read_text()
text = text.replace("__GENERATED_KEY__", "base64:" + base64.b64encode(secrets.token_bytes(32)).decode())
fd = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(text)
print("Created synthetic .env with mode 0600")
