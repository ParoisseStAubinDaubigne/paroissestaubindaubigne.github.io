import json, base64, email, sys, os
from email import policy
src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src))
raw = d["raw"]
raw += "=" * (-len(raw) % 4)
msg = email.message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)
os.makedirs(out, exist_ok=True)
for part in msg.iter_attachments():
    name = part.get_filename() or "piece"
    data = part.get_payload(decode=True)
    open(os.path.join(out, name), "wb").write(data)
    print(name, part.get_content_type(), len(data))
