#!/bin/bash
#SBATCH -J coupons_ext_test
#SBATCH -c 2
#SBATCH --mem=4G
#SBATCH -t 20
#SBATCH -o .temp/logs/%x_%j.out
# Chromium, then Firefox. Browser profiles live on the node's own disk, since /home is near its file-count cap.
S=/tmp/coupons_test_$SLURM_JOB_ID
PY=~/.conda/envs/browser/bin/python
$PY tests/run_tests.py extension "$S/chromium"; rc1=$?
# Firefox needs GLIBCXX_3.4.26, newer than Rocky 8's libstdc++; this folder holds only a link to a newer one.
LD_LIBRARY_PATH=$HOME/.cache/local_llm/stdcxx${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} $PY tests/run_firefox.py extension "$S/firefox"; rc2=$?
rm -rf "$S"
exit $((rc1 + rc2))
