"""Step 0: is the account working?

Lists the models your key can see and makes one tiny Muse Spark call.
If this fails with 401/403, the key is wrong or the account is still
restricted (payment hold not finished) - check dev.meta.ai > Billing.

    python scripts/00_check_setup.py
"""

from common import MUSE_SPARK, SAM, meta_client

client = meta_client()

print("Models visible to this key:")
ids = sorted(m.id for m in client.models.list())
for model_id in ids:
    print("  -", model_id)
for needed in (MUSE_SPARK, SAM):
    print(f"{needed}: {'OK' if needed in ids else 'NOT LISTED'}")

response = client.responses.create(
    model=MUSE_SPARK,
    input="Reply with exactly: ready",
    reasoning={"effort": "minimal"},
)
print("\nMuse Spark says:", response.output_text.strip())
print("Usage:", response.usage)
