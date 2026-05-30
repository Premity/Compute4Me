# resnet18_hpo — sample Container Contract image

A minimal user model image honoring the [Container Contract](../../docs/architecture/wire-protocol.md):
env-vars-in (`C4M_CONFIG`, `C4M_INPUT_DIR`, `C4M_OUTPUT_DIR`, `C4M_TASK_ID`), files-out
(`metrics.json`, optional `progress.jsonl`). Runs with no `import compute4me`.

Used by the E2E smoke test as the trial image. Populated in T17.
