# Install leg — SKIPPED-INSTALL-CHIMERA-V2-21

Base 129246e2ddd138550b743a6409c1025d33346a49; agent iskip-chimera-v2-21, server bunker-mvp. Cell timestamps are evidence-recording times, not individual command start times. stdout and stderr are captured separately under raw/. Provider-returned masked key fragments are redacted.

| Cell | Status | Evidence | rc |
|---|---|---|---|
| install | OK | Python 3.12.3; sdist installed in fresh venv | 0 |
| version | OK | chimera 0.3.0 | 0 |
| config | OK | config init rc 0 and chimera.yaml existence checked | 0 |
| formations | OK | all six presets rendered | 0 |
| deliberation | FAIL | DeepSeek: Insufficient Balance; XKIRO: model temporarily unavailable for scheduled maintenance; no usable answer | 2 |
| teardown | OK | destroy rc 0, subsequent list rc 0; agent absent | 0 |

## Distribution

- chimera_deliberation-0.3.0.tar.gz SHA256 e0ac6ce3b57f12d86ef57c3cea4bd3e2024e8e0478a28e076bb4142e74e133cc
- chimera_deliberation-0.3.0-py3-none-any.whl SHA256 a20c69aa0112252901b2db476ca0dfc99ec2f387267ac63e1c1a25cb94b14069

## Commands

    uv build --out-dir /home/kara/.hermes/cache/scratch/iskip-21/dist /home/kara/chimera-v2
    sha256sum /home/kara/.hermes/cache/scratch/iskip-21/dist/*
    bunker spawn iskip-chimera-v2-21 --server bunker-mvp --ttl 1h
    bunker cp <each distribution> iskip-chimera-v2-21:/home/bunker-iskip-chimera-v2-21/ --server bunker-mvp
    bunker cp <battery.sh> iskip-chimera-v2-21:/home/bunker-iskip-chimera-v2-21/battery.sh --server bunker-mvp
    bunker exec iskip-chimera-v2-21 --server bunker-mvp --timeout 480 --raw -- /bin/sh /home/bunker-iskip-chimera-v2-21/battery.sh

Inside battery.sh, each stdout, stderr and exit code was saved separately:

    /usr/bin/python3 -V
    /usr/bin/python3 -m venv /tmp/iskip-venv
    /tmp/iskip-venv/bin/pip install "$HOME/chimera_deliberation-0.3.0.tar.gz"
    cd "$HOME/iskip-empty"
    /tmp/iskip-venv/bin/chimera --version
    /tmp/iskip-venv/bin/chimera config init
    test -f chimera.yaml
    /tmp/iskip-venv/bin/chimera -c chimera.yaml formations
    /tmp/iskip-venv/bin/chimera --help
    /tmp/iskip-venv/bin/chimera deliberate --help
    /tmp/iskip-venv/bin/chimera -c chimera.yaml -f simple run --json 'Explain in one sentence why testing a fresh install matters.'

The actual version invocation ran from the agent home; it is otherwise identical. Provider credentials were sent over the agent SSH connection through stdin into a private, temporary agent-home file and deleted before the deliberation ended. The XKIRO retry used an agent-only config based on the initialized example with provider xkiro, base URL https://api.xkiro.com/v1 and model xkiro/openai/gpt-6.1-terra; the same CLI command ran with -c xkiro.yaml. The initial attempt accidentally used the native DeepSeek routing and was discarded as a setup error. XKIRO returned scheduled maintenance, so this leg remains failed despite a reachable provider.

    bunker pull iskip-chimera-v2-21 /home/bunker-iskip-chimera-v2-21/iskip-results <scratch>/pulled3 --recursive --server bunker-mvp
    bunker destroy iskip-chimera-v2-21 --server bunker-mvp --purge
    bunker list --server bunker-mvp

Initial `bunker exec --script` produced an unterminated quoted-string error; the same script was transferred using `bunker cp` and executed with `--raw` successfully. Raw captures cover the successful battery and both provider calls, with sensitive masked key fragments redacted.
