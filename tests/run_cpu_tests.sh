#!/bin/bash

set -xeu

if [ "${SKIP_DISTRIB_TESTS:-0}" -eq "1" ]; then
    skip_distrib_opt=(-m "not distributed and not tpu and not multinode_distributed")
else
    skip_distrib_opt=(-m "")
fi

MATCH_TESTS_EXPRESSION=${1:-""}

# Catch exit code 5 when tests are deselected from previous passing run
CUDA_VISIBLE_DEVICES="" pytest ${EXTRA_PYTEST_ARGS:-} --cache-dir .cpu-not-distrib --tx 4*popen//python=python --cov ignite --cov-report term-missing --cov-report xml -vvv tests "${skip_distrib_opt[@]}" -k "$MATCH_TESTS_EXPRESSION" || { exit_code=$?; if [ "$exit_code" -eq 5 ]; then echo "All tests deselected"; else exit $exit_code; fi;}

# https://pubs.opengroup.org/onlinepubs/009695399/utilities/xcu_chap02.html#tag_02_06_02
if [ "${SKIP_DISTRIB_TESTS:-0}" -eq "1" ]; then
    exit 0
fi

export WORLD_SIZE=2
CUDA_VISIBLE_DEVICES="" pytest ${EXTRA_PYTEST_ARGS:-} --cache-dir .cpu-distrib --cov ignite --cov-append --cov-report term-missing --cov-report xml --dist=each --tx $WORLD_SIZE*popen//python=python tests -m distributed -vvv -k "$MATCH_TESTS_EXPRESSION"
unset WORLD_SIZE
