#!/usr/bin/env bash
# import-matrix 模拟器内执行体（由 android-emulator-runner 的 script 调用）。
# 注意：emulator-runner 对多行 script 的分组结构（cmd || { ... }）会拆坏，
# 因此逻辑收敛到本文件（run 33170949136 Syntax error 实证）。
set -uo pipefail

WHEELS_INDEX="${1:?usage: emu-import-test.sh <wheels-index-url>}"
GRADLE_CMD=(gradle :app:connectedDebugAndroidTest -p testapp "-Pbtdeck.wheels.index=$WHEELS_INDEX")

# 冒烟：确认系统与 page-size（API 35 镜像应为 16384，留证闸门判据 6）
adb shell getprop ro.product.cpu.abi
adb shell getconf PAGESIZE

if "${GRADLE_CMD[@]}"; then
  echo "==== connected test PASSED ===="
  exit 0
fi

echo "==== connected test failed, dumping logcat ===="
adb logcat -d -b crash > "$HOME/logcat-crash.txt" 2>/dev/null || true
echo "---- crash buffer（最近 20k）----"
tail -c 20000 "$HOME/logcat-crash.txt" || true
echo "---- 应用相关行（btdeck/chaquopy/python/pydantic/linker/signal，最近 300 行）----"
adb logcat -d | grep -iE "btdeck|chaquopy|pydantic|python|linker|SIGSEGV|SIGABRT|Fatal signal" | tail -n 300 || true
exit 1
