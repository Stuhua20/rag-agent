#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
REQUIREMENTS_FILE="$BACKEND_DIR/requirements.txt"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE_FILE="$BACKEND_DIR/.env.example"
BUNDLED_RUNTIME="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"

BACKEND_PID=""
FRONTEND_PID=""

fail() {
  printf '[ERROR] %s\n' "$1" >&2
  exit 1
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi

  if [[ -e "$ENV_FILE" ]]; then
    fail "环境变量路径存在但不是文件：$ENV_FILE"
  fi

  if [[ ! -f "$ENV_EXAMPLE_FILE" ]]; then
    fail "未找到环境变量模板：$ENV_EXAMPLE_FILE"
  fi

  cp "$ENV_EXAMPLE_FILE" "$ENV_FILE" || fail "创建环境变量文件失败：$ENV_FILE"
  printf '[INFO] 未发现 backend/.env，已从模板创建。\n'
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done

  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  fail "未找到后端依赖文件：$REQUIREMENTS_FILE"
fi

PYTHON_BIN=""
VENV_DIR=""
for candidate in "$ROOT_DIR/.venv" "$ROOT_DIR/venv"; do
  if [[ -x "$candidate/bin/python" ]]; then
    PYTHON_BIN="$candidate/bin/python"
    VENV_DIR="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$BUNDLED_RUNTIME/python/bin/python3" ]]; then
    PATH="$BUNDLED_RUNTIME/python/bin:$PATH"
    export PATH
  fi

  for candidate in python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done

  if [[ -z "$PYTHON_BIN" ]]; then
    fail "未找到 Python 3.10 或更高版本，请先安装 Python。"
  fi

  VENV_DIR="$ROOT_DIR/.venv"
  printf '[INFO] 未发现项目虚拟环境，正在创建 %s\n' "$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "创建 Python 虚拟环境失败。"
  PYTHON_BIN="$VENV_DIR/bin/python"
fi

[[ -x "$PYTHON_BIN" ]] || fail "虚拟环境中的 Python 不可执行：$PYTHON_BIN"
printf '[INFO] 使用 Python 环境：%s\n' "$VENV_DIR"
printf '[INFO] 正在检查并安装后端依赖...\n'
"$PYTHON_BIN" -m pip install -r "$REQUIREMENTS_FILE" || fail "后端依赖安装失败，请检查网络连接或 pip 配置。"

if [[ ! -x "$BUNDLED_RUNTIME/node/bin/node" ]] && ! command -v node >/dev/null 2>&1; then
  fail "未找到 Node.js，请先安装 Node.js，再运行此脚本。"
fi

if [[ -x "$BUNDLED_RUNTIME/node/bin/node" ]] && ! command -v node >/dev/null 2>&1; then
  PATH="$BUNDLED_RUNTIME/node/bin:$PATH"
  export PATH
fi

PNPM=()
if command -v pnpm >/dev/null 2>&1; then
  PNPM=(pnpm)
elif [[ -x "$BUNDLED_RUNTIME/bin/pnpm" ]]; then
  PNPM=("$BUNDLED_RUNTIME/bin/pnpm")
elif command -v corepack >/dev/null 2>&1; then
  PNPM=(corepack pnpm)
else
  fail "未找到 pnpm。请先安装 pnpm，或安装带 Corepack 的 Node.js。"
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  printf '[INFO] 未发现前端依赖，正在安装...\n'
  (cd "$FRONTEND_DIR" && "${PNPM[@]}" install --frozen-lockfile) || fail "前端依赖安装失败。"
fi

ensure_env_file

printf '\n[INFO] 后端：http://127.0.0.1:8000\n'
printf '[INFO] 前端：http://127.0.0.1:5173\n'
printf '[INFO] 按 Ctrl+C 可同时停止前后端。\n\n'

(
  cd "$BACKEND_DIR"
  exec "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  exec "${PNPM[@]}" run dev --host 127.0.0.1 --port 5173
) &
FRONTEND_PID=$!

process_is_running() {
  local process_status
  process_status="$(ps -o stat= -p "$1" 2>/dev/null || true)"
  [[ -n "$process_status" && "$process_status" != Z* ]]
}

while process_is_running "$BACKEND_PID" && process_is_running "$FRONTEND_PID"; do
  sleep 1
done

if ! process_is_running "$BACKEND_PID"; then
  wait "$BACKEND_PID" 2>/dev/null || true
  fail "后端服务已退出，正在停止前端。"
fi

wait "$FRONTEND_PID" 2>/dev/null || true
fail "前端服务已退出，正在停止后端。"
