from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canon_test
import decision_test
import smoke_test
import interaction_test
import information_test
import action_test
import model_gateway_test
import v07_test
import v08_test
import v09_test
import v10_test
import v11_test
import v12_test
import v13_test
import v14_test
import v15_test
import audit_v01_v15_test
import v16_test
import v17_test
import v18_test
import v19_test
import v19_edge_test
import v20_test
import v20_edge_test
import v21_test
import v21_edge_test
import v22_test
import v22_edge_test
import v23_test
import v23_edge_test
import v24_test
import v24_edge_test
import v25_test
import v25_edge_test
import v26_test
import v26_edge_test
import v27_test
import v28_test
import v29_test
import v30_test
import v31_test
import v32_test
import v33_test
import v34_test
import v35_test
import v36_test
import v37_test
import v38_test
import v39_test
import v40_test
import v41_test
import v42_test
import v43_test
import v44_test
import v45_test
import v46_test
import v47_test


def run():
    canon_test.run()
    decision_test.run()
    smoke_test.run()
    interaction_test.run()
    information_test.run()
    action_test.run()
    model_gateway_test.run()
    v07_test.run()
    v08_test.run()
    v09_test.run()
    v10_test.run()
    v11_test.run()
    v12_test.run()
    v13_test.run()
    v14_test.run()
    v15_test.run()
    audit_v01_v15_test.run()
    v16_test.run()
    v17_test.run()
    v18_test.run()
    v19_test.run()
    v19_edge_test.run()
    v20_test.run()
    v20_edge_test.run()
    v21_test.run()
    v21_edge_test.run()
    v22_test.run()
    v22_edge_test.run()
    v23_test.run()
    v23_edge_test.run()
    v24_test.run()
    v24_edge_test.run()
    v25_test.run()
    v25_edge_test.run()
    v26_test.run()
    v26_edge_test.run()
    v27_test.run()
    v28_test.run()
    v29_test.run()
    v30_test.run()
    v31_test.run()
    v32_test.run()
    v33_test.run()
    v34_test.run()
    v35_test.run()
    v36_test.run()
    v37_test.run()
    v38_test.run()
    v39_test.run()
    v40_test.run()
    v41_test.run()
    v42_test.run()
    v43_test.run()
    v44_test.run()
    v45_test.run()
    v46_test.run()
    v47_test.run()
    print("All Narrative Engine v0.47.0 tests passed.")


if __name__ == "__main__":
    run()
