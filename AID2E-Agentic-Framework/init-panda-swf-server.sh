#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# SWF MCP tunnel/test helper
#
# Communication path:
#   local laptop -> SSH tunnel -> SDCC rcfsub -> pandaserver02.sdcc.bnl.gov
#
# Local URL used by test-epic-mcp.py:
#   https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/
# ------------------------------------------------------------

LOCAL_PORT="${LOCAL_PORT:-8443}"
REMOTE_HOST="${REMOTE_HOST:-pandaserver02.sdcc.bnl.gov}"
REMOTE_PORT="${REMOTE_PORT:-443}"
JUMP_HOST="${JUMP_HOST:-rcfsub}"
CERT_DIR="${CERT_DIR:-/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/sdcc-grid-certificates}"
TEST_SCRIPT="${TEST_SCRIPT:-test-epic-mcp.py}"
TOKEN_FILE="${TOKEN_FILE:-.token-swf}"

HOSTS_ADDED="false"
TUNNEL_TERMINAL_STARTED="false"
SKIP_TUNNEL="${SKIP_TUNNEL:-0}"

TUNNEL_CMD="ssh -N -L ${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT} ${JUMP_HOST}"


# IF tunneing is already established, you can skip starting a new tunnel by setting SKIP_TUNNEL=1 before running this script.
#Tunneling command ssh -N -L 8443:pandaserver02.sdcc.bnl.gov:443 rcfsub
SKIP_TUNNEL=1
cleanup() {
    echo
    echo "[cleanup] Removing temporary /etc/hosts entry for ${REMOTE_HOST}..."

    if [[ "${HOSTS_ADDED}" == "true" ]]; then
        sudo sed -i.bak "/${REMOTE_HOST}/d" /etc/hosts
        echo "[cleanup] Removed ${REMOTE_HOST} from /etc/hosts"
        echo "[cleanup] Backup saved as /etc/hosts.bak"
    else
        echo "[cleanup] This script did not add a new hosts entry; leaving /etc/hosts unchanged."
    fi

    echo

    if [[ "${TUNNEL_TERMINAL_STARTED}" == "true" ]]; then
        echo "[cleanup] The SSH tunnel was started in a separate terminal."
        echo "[cleanup] Close that terminal manually when done, or run:"
        echo "          pkill -f \"${TUNNEL_CMD}\""
    elif [[ "${SKIP_TUNNEL}" == "1" ]]; then
        echo "[cleanup] SKIP_TUNNEL=1 was used. This script did not start the SSH tunnel."
    else
        echo "[cleanup] SSH tunnel terminal was not started."
    fi
}

trap cleanup EXIT INT TERM

check_required_commands() {
    echo "[step 1] Checking required commands..."

    for cmd in ssh rsync python3 grep sudo; do
        if ! command -v "${cmd}" >/dev/null 2>&1; then
            echo "ERROR: Required command not found: ${cmd}"
            exit 1
        fi
    done

    if [[ ! -f "${TEST_SCRIPT}" ]]; then
        echo "ERROR: Test script not found: ${TEST_SCRIPT}"
        echo "Run this wrapper from the directory containing ${TEST_SCRIPT}, or set:"
        echo "  TEST_SCRIPT=/path/to/test-epic-mcp.py"
        exit 1
    fi
}

load_token() {
    echo "[step 2] Loading SWF monitor MCP token..."

    if [[ ! -f "${TOKEN_FILE}" ]]; then
        echo "ERROR: Token file not found: ${TOKEN_FILE}"
        echo "Create it with:"
        echo "  printf '%s\n' 'your-token-here' > ${TOKEN_FILE}"
        echo "  chmod 600 ${TOKEN_FILE}"
        exit 1
    fi

    export SWF_MONITOR_MCP_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"

    echo "[info] Loaded SWF_MONITOR_MCP_TOKEN from ${TOKEN_FILE}"
}

copy_certificates() {
    echo "[step 3] Copying SDCC grid certificates..."

    if [[ -d "${CERT_DIR}" && "$(ls -A "${CERT_DIR}")" ]]; then
        echo "[info] ${CERT_DIR} already exists and is not empty; skipping certificate copy."
    else
        echo "[info] Copying certificates from ${JUMP_HOST} to ${CERT_DIR}..."
        mkdir -p "${CERT_DIR}"
        rsync -av "${JUMP_HOST}:/etc/grid-security/certificates/" "${CERT_DIR}/"
    fi

    export SSL_CERT_DIR="${CERT_DIR}"
    echo "[info] SSL_CERT_DIR=${SSL_CERT_DIR}"
}

add_hosts_entry() {
    echo "[step 4] Adding temporary /etc/hosts entry..."

    if grep -qE "^[[:space:]]*127\.0\.0\.1[[:space:]]+${REMOTE_HOST}([[:space:]]|$)" /etc/hosts; then
        echo "[info] Existing localhost entry for ${REMOTE_HOST}:"
        grep "${REMOTE_HOST}" /etc/hosts || true
    elif grep -q "${REMOTE_HOST}" /etc/hosts; then
        echo "WARNING: ${REMOTE_HOST} already exists in /etc/hosts but may not point to 127.0.0.1:"
        grep "${REMOTE_HOST}" /etc/hosts || true
        echo
        echo "This script will not modify the existing entry."
        echo "Make sure it resolves to 127.0.0.1 while using the SSH tunnel."
    else
        echo "127.0.0.1 ${REMOTE_HOST}" | sudo tee -a /etc/hosts >/dev/null
        HOSTS_ADDED="true"
        echo "[info] Added: 127.0.0.1 ${REMOTE_HOST}"
    fi
}

open_tunnel_terminal() {
    local terminal_script
    local terminal_script_file

    terminal_script_file="$(mktemp /tmp/swf-mcp-tunnel.XXXXXX.sh)"

    cat > "${terminal_script_file}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

echo "[ssh tunnel] Starting tunnel:"
echo "             localhost:${LOCAL_PORT} -> ${JUMP_HOST} -> ${REMOTE_HOST}:${REMOTE_PORT}"
echo
echo "[ssh tunnel] Enter your SSH key passphrase/password if prompted."
echo "[ssh tunnel] Keep this terminal open while using the MCP server."
echo

${TUNNEL_CMD}

echo
echo "[ssh tunnel] Tunnel exited."
echo "[ssh tunnel] Press Enter to close this terminal."
read -r _
EOF

    chmod +x "${terminal_script_file}"

    echo "[info] Tunnel command:"
    echo "       ${TUNNEL_CMD}"
    echo

    # Prefer x-terminal-emulator on Ubuntu/Debian. This usually points to the working system default.
    if command -v x-terminal-emulator >/dev/null 2>&1; then
        x-terminal-emulator -e bash -lc "${terminal_script_file}" &
        TUNNEL_TERMINAL_STARTED="true"
        return 0
    fi

    # Try common non-GNOME terminals first.
    if command -v konsole >/dev/null 2>&1; then
        konsole --new-tab -e bash -lc "${terminal_script_file}" &
        TUNNEL_TERMINAL_STARTED="true"
        return 0
    fi

    if command -v xfce4-terminal >/dev/null 2>&1; then
        xfce4-terminal --command "bash -lc '${terminal_script_file}'" &
        TUNNEL_TERMINAL_STARTED="true"
        return 0
    fi

    if command -v mate-terminal >/dev/null 2>&1; then
        mate-terminal -- bash -lc "${terminal_script_file}" &
        TUNNEL_TERMINAL_STARTED="true"
        return 0
    fi

    if command -v xterm >/dev/null 2>&1; then
        xterm -hold -e bash -lc "${terminal_script_file}" &
        TUNNEL_TERMINAL_STARTED="true"
        return 0
    fi

    # GNOME terminal last because it failed on your system due to snap/core20 GLIBC mismatch.
    if command -v gnome-terminal >/dev/null 2>&1; then
        env -u LD_LIBRARY_PATH \
            -u GTK_PATH \
            -u GIO_MODULE_DIR \
            -u GDK_PIXBUF_MODULE_FILE \
            gnome-terminal -- bash -lc "${terminal_script_file}" &
        TUNNEL_TERMINAL_STARTED="true"
        return 0
    fi

    echo "ERROR: No supported terminal emulator found."
    echo
    echo "Open another terminal manually and run:"
    echo
    echo "  ${TUNNEL_CMD}"
    echo
    echo "Then rerun this script with:"
    echo
    echo "  SKIP_TUNNEL=1 $0"
    echo

    rm -f "${terminal_script_file}"
    exit 1
}

wait_for_tunnel() {
    echo "[step] Waiting for tunnel on 127.0.0.1:${LOCAL_PORT}..."

    for _ in {1..90}; do
        if command -v nc >/dev/null 2>&1; then
            if nc -z 127.0.0.1 "${LOCAL_PORT}"; then
                echo "[info] Tunnel is ready on port ${LOCAL_PORT}."
                return 0
            fi
        else
            if timeout 1 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/${LOCAL_PORT}" 2>/dev/null; then
                echo "[info] Tunnel is ready on port ${LOCAL_PORT}."
                return 0
            fi
        fi

        sleep 1
    done

    echo "ERROR: Tunnel did not become ready on 127.0.0.1:${LOCAL_PORT}."
    echo
    echo "Check the separate SSH terminal for authentication or connection errors."
    echo
    echo "You can also manually run this in another terminal:"
    echo
    echo "  ${TUNNEL_CMD}"
    echo
    echo "Then rerun this script with:"
    echo
    echo "  SKIP_TUNNEL=1 $0"
    exit 1
}

verify_test_url() {
    echo "[step 6] Verifying URL inside ${TEST_SCRIPT}..."

    local expected_url
    expected_url="https://${REMOTE_HOST}:${LOCAL_PORT}/swf-monitor/mcp/"

    if grep -q "URL *= *\"${expected_url}\"" "${TEST_SCRIPT}"; then
        echo "[info] ${TEST_SCRIPT} already has expected URL:"
        echo "       ${expected_url}"
    else
        echo "WARNING: ${TEST_SCRIPT} may not have the expected URL."
        echo "Expected:"
        echo "  URL = \"${expected_url}\""
        echo
        echo "Current matching lines:"
        grep -n "URL *= *" "${TEST_SCRIPT}" || true
        echo
        echo "Edit ${TEST_SCRIPT} before relying on the test result."
    fi
}

run_test() {
    echo "[step 7] Running MCP test script..."
    python3 "${TEST_SCRIPT}"
    echo
    echo "[done] Test completed successfully."
}

main() {
    check_required_commands
    load_token
    copy_certificates
    add_hosts_entry

    if [[ "${SKIP_TUNNEL}" == "1" ]]; then
        echo "[step 5] SKIP_TUNNEL=1 set; assuming tunnel is already running."
        echo "[info] Expected tunnel:"
        echo "       ${TUNNEL_CMD}"
    else
        echo "[step 5] Opening SSH tunnel in a separate terminal..."
        open_tunnel_terminal
    fi

    wait_for_tunnel
    verify_test_url
    run_test

}

main "$@"
echo "\n [info] You may have to set SWF_MONITOR_MCP_TOKEN in your environment manually to run the test script again without this wrapper."
