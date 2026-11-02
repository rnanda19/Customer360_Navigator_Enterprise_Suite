# Customer360 Navigator — Enterprise Governance Status (BP1-BP8)

Generated: 2026-11-02T09:57:14.173858+00:00

Real status, read live from this project's own config files and local MLflow registry state - never fabricated. See src/mlops/enterprise_status.py's module docstring for exactly how each field is derived.

| BP | Problem type | Lifecycle state | Governance applicable | MLflow champion | Artifact on disk | Config status |
|---|---|---|---|---|---|---|
| bp1 | trained_classifier | production | yes | 1 | yes | `gate1_confirmed_gate2_confirmed_gate3_confirmed_gate4_confirmed_gate5_confirmed_gate6_confirmed` |
| bp2 | trained_classifier | validation | yes | (none) | no | `gate1_confirmed_gate3_confirmed_gate4_confirmed_gate5_confirmed_gate6_confirmed` |
| bp3 | trained_classifier | validation | yes | (none) | no | `gate1_confirmed_gate3_confirmed_gate4_confirmed_gate5_confirmed_gate6_confirmed` |
| bp4 | benchmark_pipeline | development | no | (none) | no | `gate6_complete` |
| bp5 | association_reporting | development | no | (none) | no | `gate1_confirmed` |
| bp6 | retrieval_strategy | validation | no | (none) | no | `gate1_confirmed_gate2_confirmed_gate3_confirmed_gate4_confirmed_gate5_confirmed` |
| bp7 | rule_engine | validation | no | (none) | no | `gate1_confirmed_gate2_confirmed_gate3_confirmed_gate4_confirmed_gate5_confirmed` |
| bp8 | gold_layer_aggregation | validation | no | (none) | no | `gate1_confirmed_gate2_confirmed_gate3_confirmed` |
