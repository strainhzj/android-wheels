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

echo "==== connected test failed, dumping logcat (last 30k chars) ===="
adb logcat -d > "$HOME/logcat-failure.txt"
tail -c 30000 "$HOME/logcat-failure.txt" || true
exit 1
