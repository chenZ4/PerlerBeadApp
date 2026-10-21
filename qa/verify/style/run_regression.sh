#!/usr/bin/env bash
# T17 回归复核：顺序跑 4 套测试（严格不并发），日志落 qa/verify/evidence/style/logs/
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
LOGDIR="$ROOT/qa/verify/evidence/style/logs"
mkdir -p "$LOGDIR"
cd "$ROOT"
rc_total=0
run() {
  local name="$1"; shift
  local log="$LOGDIR/$name.log"
  echo "=== $name start $(date '+%H:%M:%S') ===" | tee -a "$LOGDIR/run_all.log"
  "$@" > "$log" 2>&1
  local rc=$?
  local pass fail
  pass=$(grep -c '\[PASS\]' "$log" 2>/dev/null || true)
  fail=$(grep -c '\[FAIL\]' "$log" 2>/dev/null || true)
  echo "=== $name rc=$rc PASS=$pass FAIL=$fail $(date '+%H:%M:%S') ===" | tee -a "$LOGDIR/run_all.log"
  [ $rc -ne 0 ] && rc_total=1
  return 0
}
run run_tests bash -lc 'cd "$0" && conda run -n pindou python tests/run_tests.py' "$ROOT"
run gui_smoke bash -lc 'cd "$0" && conda run -n pindou python tests/gui_smoke.py' "$ROOT"
run stress_protocol bash -lc 'cd "$0" && conda run -n pindou python tests/stress_protocol.py' "$ROOT"
run swift_test bash -lc 'cd "$0/app" && swift test --disable-sandbox' "$ROOT"
# swift 汇总
grep -E 'Executed [0-9]+ tests' "$LOGDIR/swift_test.log" | tail -1 | tee -a "$LOGDIR/run_all.log"
echo "TOTAL_RC=$rc_total" | tee -a "$LOGDIR/run_all.log"
exit $rc_total
