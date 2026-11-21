#!/bin/sh
H=/home/bunker-iskipchimera21r2
R=$H/results
mkdir -p "$R" "$H/empty"
{ python3 -V; python3 -m venv "$H/venv" && "$H/venv/bin/pip" install "$H/chimera_deliberation-0.3.0.tar.gz"; } >"$R/install.out" 2>"$R/install.err"; echo $? >"$R/install.rc"
cd "$H/empty" || exit 1
"$H/venv/bin/chimera" --version >"$R/version.out" 2>"$R/version.err"; echo $? >"$R/version.rc"
"$H/venv/bin/chimera" config init >"$R/config.out" 2>"$R/config.err"; rc=$?; test -f chimera.yaml || rc=1; echo $rc >"$R/config.rc"
"$H/venv/bin/chimera" -c chimera.yaml formations >"$R/formations.out" 2>"$R/formations.err"; echo $? >"$R/formations.rc"
