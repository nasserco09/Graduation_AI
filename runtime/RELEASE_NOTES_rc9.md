# LibaasLens runtime rc.9

Verified Windows x86_64 runtime resources for application **v1.2.0-rc.9**. The application source inside the archive remains at commit `4337d6e5f18ea58d42d31e9064affa2b54ef1f67`. Branding and submission-document updates do not change these archived bytes.

## Download and assemble

Download **all 28 `.zip.partNNN` files** and the five support files: `parts_manifest.json`, `assemble_runtime.py`, `Assemble_Runtime.cmd`, `runtime_manifest.json`, and `DOWNLOAD_README_AR.md`. Keep the parts and assembly files together, then run `Assemble_Runtime.cmd` with Python available.

The assembled archive is named `Graduation_AI_Runtime_rc9_v1.zip` (the original published filename), with **1,815,578,390 bytes** and SHA-256:

```text
dd713d933cb3395e754ce607ef33bfd0fabdc7105c92cc4d846b4c4075975f0c
```

Extract into a **new folder**. Install Python 3.12 x64, run `Setup_Runtime.cmd`, then `Start_Demo.cmd`. Initial dependencies need internet or compatible local wheels. The package includes SigLIP2 Base, SAM2.1 Hiera Base Plus, 3,068 gallery images, the original index, code and local frontend assets. It does not include Python, wheels, unused experimental models, personal accounts, added products or telemetry.

The original application tag and all 33 asset payloads are retained. The default repository branch is now **main**, and `feature/frontend-v2` is retained for development. The old `Graduation_AI` repository URLs redirect to **nasserco09/LibaasLens**; do not recreate a different repository under the old name if the redirects must remain valid.

Recorded package checks used an isolated Python environment with real models on CPU: 32 HTTP checks, 15 administration checks and eight package-boundary tests. These are functional checks, not new retrieval-accuracy measurements. See [runtime verification](https://github.com/nasserco09/LibaasLens/blob/main/runtime/VERIFICATION_RUNTIME.json) and [publication verification](https://github.com/nasserco09/LibaasLens/blob/main/runtime/VERIFICATION_PUBLICATION_20261114.json).

Original team-owned material is governed by the [project rights notice](https://github.com/nasserco09/LibaasLens/blob/main/LICENSE); upstream model, dataset and dependency licences remain separate. [Runtime instructions in Arabic](https://github.com/nasserco09/LibaasLens/blob/main/RUNTIME_README_AR.md).
