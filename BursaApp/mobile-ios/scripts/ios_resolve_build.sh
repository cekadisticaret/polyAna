#!/usr/bin/env bash
# Native iOS build numarası — project.yml üzerinden.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

read_project() {
  local yml="${1:-$ROOT/project.yml}"
  version_name=$(grep 'MARKETING_VERSION:' "$yml" | head -1 | sed 's/.*MARKETING_VERSION:[[:space:]]*//' | tr -d '"')
  local_build=$(grep 'CURRENT_PROJECT_VERSION:' "$yml" | head -1 | sed 's/.*CURRENT_PROJECT_VERSION:[[:space:]]*//' | tr -d '"')
  [[ "$local_build" =~ ^[0-9]+$ ]] || local_build=0
  [[ -n "$version_name" ]] || version_name="1.0.0"
  PROJECT_YML="$yml"
}

fetch_store_latest() {
  asc=0 tf=0
  if [[ -n "${MOCK_ASC_LATEST:-}" ]]; then
    asc="$MOCK_ASC_LATEST"
  elif [[ -n "${APP_STORE_APPLE_ID:-}" ]] && command -v app-store-connect >/dev/null 2>&1; then
    asc=$(app-store-connect get-latest-app-store-build-number "$APP_STORE_APPLE_ID" 2>/dev/null || echo 0)
    tf=$(app-store-connect get-latest-testflight-build-number "$APP_STORE_APPLE_ID" 2>/dev/null || echo 0)
  fi
  [[ "$asc" =~ ^[0-9]+$ ]] || asc=0
  [[ "$tf" =~ ^[0-9]+$ ]] || tf=0
  latest=$local_build
  for v in "$asc" "$tf"; do
    if [ "$v" -gt "$latest" ]; then latest=$v; fi
  done
  next=$((latest + 1))
}

# Binary/XML plist dosyasından CFBundleVersion okur (PlistBuddy öncelikli).
plist_bundle_version() {
  local plist_file="${1:?plist_file}"
  local ver=""
  [[ -f "$plist_file" ]] || return 1
  if [[ -x /usr/libexec/PlistBuddy ]]; then
    ver=$(/usr/libexec/PlistBuddy -c 'Print CFBundleVersion' "$plist_file" 2>/dev/null || true)
  fi
  if [[ -z "$ver" ]] && command -v plutil >/dev/null 2>&1; then
    ver=$(plutil -extract CFBundleVersion raw "$plist_file" 2>/dev/null || true)
  fi
  if [[ -z "$ver" ]]; then
    ver=$(grep -A1 '<key>CFBundleVersion</key>' "$plist_file" 2>/dev/null | tail -1 | sed -n 's/.*<string>\(.*\)<\/string>.*/\1/p' || true)
  fi
  [[ -n "$ver" ]] || return 1
  printf '%s' "$ver"
}

cmd_resolve() {
  read_project "${1:-$ROOT/project.yml}"
  fetch_store_latest
  echo "version_name=$version_name"
  echo "local_build=$local_build"
  echo "asc_latest=$asc"
  echo "tf_latest=$tf"
  echo "store_latest=$latest"
  echo "next_build=$next"
}

cmd_should_upload() {
  local built="${1:?built}"
  local store_latest="${2:?store_latest}"
  if [ "$built" -le "$store_latest" ]; then
    echo "SKIP: build $built zaten App Store'da (son=$store_latest)"
    return 1
  fi
  echo "UPLOAD: build $built > son $store_latest"
  return 0
}

cmd_apply() {
  local vn="${1:?version_name}"
  local bn="${2:?build_number}"
  local yml="${3:-$ROOT/project.yml}"
  sed -i '' "s/MARKETING_VERSION: .*/MARKETING_VERSION: ${vn}/" "$yml"
  sed -i '' "s/CURRENT_PROJECT_VERSION: .*/CURRENT_PROJECT_VERSION: ${bn}/" "$yml"
}

cmd_apply_pbxproj() {
  local vn="${1:?version_name}"
  local bn="${2:?build_number}"
  local pbx="${3:-$ROOT/BursaApp.xcodeproj/project.pbxproj}"
  if [[ ! -f "$pbx" ]]; then
    echo "HATA: pbxproj yok: $pbx" >&2
    return 1
  fi
  sed -i '' "s/CURRENT_PROJECT_VERSION = [^;]*;/CURRENT_PROJECT_VERSION = ${bn};/g" "$pbx"
  sed -i '' "s/MARKETING_VERSION = [^;]*;/MARKETING_VERSION = ${vn};/g" "$pbx"
  if ! grep -q "CURRENT_PROJECT_VERSION = ${bn};" "$pbx"; then
    echo "HATA: pbxproj CURRENT_PROJECT_VERSION=${bn} uygulanamadı" >&2
    grep CURRENT_PROJECT_VERSION "$pbx" | head -5 >&2 || true
    return 1
  fi
  echo "pbxproj → MARKETING_VERSION=${vn} CURRENT_PROJECT_VERSION=${bn}"
}

cmd_plist_build() {
  plist_bundle_version "${1:?plist}"
}

cmd_ipa_build_number() {
  local ipa="${1:?ipa}"
  local plist_path tmpdir plist_file ver
  [[ -f "$ipa" ]] || return 1
  plist_path=$(unzip -Z1 "$ipa" 2>/dev/null | grep -E '^Payload/[^/]+\.app/Info\.plist$' | head -1 || true)
  [[ -n "$plist_path" ]] || {
    echo "HATA: IPA içinde Info.plist yok: $ipa" >&2
    unzip -Z1 "$ipa" 2>/dev/null | head -20 >&2 || true
    return 1
  }
  tmpdir=$(mktemp -d 2>/dev/null || mktemp -d -t bursa-ipa)
  plist_file="$tmpdir/Info.plist"
  unzip -p "$ipa" "$plist_path" > "$plist_file" 2>/dev/null || {
    rm -rf "$tmpdir"
    return 1
  }
  ver=$(plist_bundle_version "$plist_file" || true)
  rm -rf "$tmpdir"
  [[ -n "$ver" ]] || return 1
  printf '%s' "$ver"
}

cmd_archive_build_number() {
  local search_root="${1:-$ROOT/build/ios/xcarchive}"
  local plist
  plist=$(find "$search_root" -path '*/Products/Applications/*.app/Info.plist' 2>/dev/null | head -1 || true)
  [[ -n "$plist" ]] || {
    echo "HATA: xcarchive Info.plist yok under $search_root" >&2
    return 1
  }
  plist_bundle_version "$plist"
}

cmd_verify_build() {
  local expected="${1:?expected_build}"
  local archive_build ipa_build ipa
  archive_build=$(cmd_archive_build_number "${2:-$ROOT/build/ios/xcarchive}" || true)
  ipa="${3:-$ROOT/build/ios/ipa/BursaApp.ipa}"
  if [[ ! -f "$ipa" ]]; then
    ipa=$(find "$ROOT/build/ios/ipa" -name '*.ipa' 2>/dev/null | head -1 || true)
  fi
  ipa_build=""
  if [[ -n "$ipa" && -f "$ipa" ]]; then
    ipa_build=$(cmd_ipa_build_number "$ipa" || true)
  fi
  echo "expected=$expected archive=$archive_build ipa=${ipa_build:-?} ipa_path=${ipa:-yok}"
  if [[ -z "$archive_build" ]]; then
    echo "HATA: xcarchive CFBundleVersion okunamadı" >&2
    return 1
  fi
  if [[ "$archive_build" != "$expected" ]]; then
    echo "HATA: archive build $archive_build != $expected" >&2
    return 1
  fi
  if [[ -z "$ipa_build" ]]; then
    echo "HATA: IPA CFBundleVersion okunamadı ($ipa)" >&2
    return 1
  fi
  if [[ "$ipa_build" != "$expected" ]]; then
    echo "HATA: IPA build $ipa_build != $expected (archive=$archive_build)" >&2
    return 1
  fi
  echo "OK: build $expected doğrulandı"
}

case "${1:-}" in
  resolve) cmd_resolve "${2:-}" ;;
  should-upload) cmd_should_upload "$2" "$3" ;;
  apply) cmd_apply "$2" "$3" "${4:-}" ;;
  apply-pbxproj) cmd_apply_pbxproj "$2" "$3" "${4:-}" ;;
  plist-build) cmd_plist_build "$2" ;;
  ipa-build) cmd_ipa_build_number "$2" ;;
  archive-build) cmd_archive_build_number "${2:-}" ;;
  verify-build) cmd_verify_build "$2" "${3:-}" "${4:-}" ;;
  *)
    echo "usage: $0 resolve|should-upload|apply|apply-pbxproj|plist-build|ipa-build|archive-build|verify-build ..."
    exit 2
    ;;
esac
