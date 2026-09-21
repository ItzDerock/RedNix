# RedNix acceptance tests (PLAN.md §10.2)

Executable specifications for the claims in PLAN.md. They run against a real
host + real VMs, so most require a bootable environment. Setup:

    export REDNIX_TEST_EVENT=atest          # event name the suite may use
    export REDNIX_TEST_CANARY="$HOME/.rednix-canary"   # host-only file
    rednix init && rednix doctor && rednix build --pin

Run everything:

    tests/acceptance/run.sh

Tests marked [manual] fail unless the listed environment interaction is
performed by a human; they are checklists, not fake passes.
