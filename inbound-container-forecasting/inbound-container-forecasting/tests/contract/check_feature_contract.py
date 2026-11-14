"""Verify the compiled Dataform feature mart exposes every column the model expects.

    cd dataform && npx @dataform/cli compile --json | python ../tests/contract/check_feature_contract.py
"""

import json
import re
import sys

sys.path.insert(0, "mlops/src")
sys.path.insert(0, "../mlops/src")
from inbound_forecast.features import FEATURES, KEY_COLS, TARGET  # noqa: E402

compiled = json.load(sys.stdin)
mart = next(
    t for t in compiled["tables"] if t["target"]["name"] == "mart_container_volume_features"
)
query = mart["query"]
expected = [c for c in FEATURES if c != "dc_code"] + KEY_COLS + [TARGET, "is_future"]
missing = [c for c in expected if not re.search(rf"\b{c}\b", query)]
if missing:
    sys.exit(f"Feature contract broken, columns missing in Dataform mart: {missing}")
print(f"OK: all {len(expected)} model columns present in compiled mart")
