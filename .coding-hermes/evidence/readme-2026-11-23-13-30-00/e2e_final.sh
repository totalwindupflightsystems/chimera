#!/bin/bash
# Final arms: CLI tables (README:110), README:610 example line claim, 9router count cross-doc.
E2E=/home/kara/.hermes/stand-in/readme/chimera-v2/run/e2e
V=/home/kara/chimera-v2/.venv/bin
export CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only
echo "=== A1: chimera formations (README:110 tables claim; exit 0) ==="
$V/chimera --config $E2E/local-fixture.yaml formations > $E2E/formations.out 2>$E2E/formations.err
echo "rc=$?"; head -12 $E2E/formations.out
echo "=== A2: chimera models (README:110) ==="
$V/chimera --config $E2E/local-fixture.yaml models > $E2E/models.out 2>$E2E/models.err
echo "rc=$?"; head -8 $E2E/models.out
echo "=== A3: README:610 claims quick-panel at chimera.yaml.example lines 55-62 ==="
sed -n '55,62p' /home/kara/chimera-v2/chimera.yaml.example
echo "=== A4: 9router count coherence README vs docs/CONFIG.md ==="
grep -n '323\|measured 2026-10-19' /home/kara/chimera-v2/README.md | head -4
grep -n 'models across\|upstream prefixes' /home/kara/chimera-v2/docs/CONFIG.md | head -5
echo "ARM_FINAL_DONE"
