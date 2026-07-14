#!/usr/bin/env bash

set -euo pipefail

target_user="${1:-${SUDO_USER:-${USER:-}}}"
rule_path="/etc/polkit-1/rules.d/49-unode-networkmanager.rules"

if [[ ! "${target_user}" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "Invalid local user name: ${target_user}" >&2
    exit 2
fi

if ! id "${target_user}" >/dev/null 2>&1; then
    echo "Local user does not exist: ${target_user}" >&2
    exit 2
fi

temporary_rule="$(mktemp)"
trap 'rm -f "${temporary_rule}"' EXIT

printf '%s\n' \
    'polkit.addRule(function(action, subject) {' \
    "    if (subject.user !== \"${target_user}\") {" \
    '        return polkit.Result.NOT_HANDLED;' \
    '    }' \
    '' \
    '    const allowed = [' \
    '        "org.freedesktop.NetworkManager.network-control",' \
    '        "org.freedesktop.NetworkManager.settings.modify.own",' \
    '        "org.freedesktop.NetworkManager.settings.modify.system",' \
    '        "org.freedesktop.NetworkManager.wifi.scan"' \
    '    ];' \
    '' \
    '    if (allowed.indexOf(action.id) >= 0) {' \
    '        return polkit.Result.YES;' \
    '    }' \
    '' \
    '    return polkit.Result.NOT_HANDLED;' \
    '});' \
    > "${temporary_rule}"

sudo install \
    --owner=root \
    --group=root \
    --mode=0644 \
    "${temporary_rule}" \
    "${rule_path}"

echo "Installed uNode NetworkManager policy for ${target_user}: ${rule_path}"
