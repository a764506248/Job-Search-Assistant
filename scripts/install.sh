#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
MANIFEST="$SCRIPT_DIR/release-manifest.env"

if [ ! -f "$MANIFEST" ]; then
  echo "错误：找不到版本清单 $MANIFEST" >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$MANIFEST"

MODE=install
DRY_RUN=0
OPEN_SETUP=1
INSTALL_DIR=${JSA_INSTALL_DIR:-"$HOME/.job-search-assistant"}
COMPOSE_FILE="$INSTALL_DIR/docker-compose.release.yml"
SOURCE_DIR="$INSTALL_DIR/source"
EXTENSION_ZIP="$INSTALL_DIR/job-search-assistant-chrome-mv3.zip"
RUNNER_SCRIPT="$INSTALL_DIR/automation-runner.py"
RUNNER_PID="$INSTALL_DIR/automation-runner.pid"
RUNNER_LOG="$INSTALL_DIR/automation-runner.log"

usage() {
  cat <<'EOF'
用法：scripts/install.sh [--check|--install|--upgrade|--uninstall] [--dry-run] [--no-open]

  --check      只检查 Docker、Compose、Chrome、端口和现有安装
  --install    安装并启动（默认）
  --upgrade    拉取清单指定镜像并更新扩展包
  --uninstall  停止容器并移除安装器托管文件；保留 data/ 用户数据
  --dry-run    仅打印将执行的操作
  --no-open    完成后不自动打开首次使用向导
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) MODE=check ;;
    --install) MODE=install ;;
    --upgrade) MODE=upgrade ;;
    --uninstall) MODE=uninstall ;;
    --dry-run) DRY_RUN=1 ;;
    --no-open) OPEN_SETUP=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run]'
    printf ' %s' "$@"
    printf '\n'
  else
    "$@"
  fi
}

has_command() { command -v "$1" >/dev/null 2>&1; }

find_chrome() {
  if [ "$(uname -s)" = Darwin ]; then
    [ -d "/Applications/Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ]
  else
    has_command google-chrome || has_command google-chrome-stable || has_command chromium || has_command chromium-browser
  fi
}

port_available() {
  port=$1
  if has_command lsof; then
    ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  elif has_command nc; then
    ! nc -z 127.0.0.1 "$port" >/dev/null 2>&1
  else
    return 0
  fi
}

check_environment() {
  failures=0
  say "Job Search Assistant ${JSA_RELEASE_VERSION} 环境检查"
  if has_command docker; then
    say "✓ Docker 命令已安装"
  else
    say "✗ 未安装 Docker Desktop / Docker Engine"
    failures=$((failures + 1))
  fi
  if has_command docker && docker compose version >/dev/null 2>&1; then
    say "✓ Docker Compose 可用"
  else
    say "✗ Docker Compose v2 不可用"
    failures=$((failures + 1))
  fi
  if has_command curl; then say "✓ curl 可用"; else say "✗ 未安装 curl"; failures=$((failures + 1)); fi
  if find_chrome; then say "✓ Chrome/Chromium 已安装"; else say "! 未检测到 Chrome/Chromium"; fi
  if port_available 8765 || [ -f "$COMPOSE_FILE" ]; then say "✓ 管理后台端口可用或由现有安装管理"; else say "✗ 端口 8765 已被其他程序占用"; failures=$((failures + 1)); fi
  return "$failures"
}

compose() {
  JSA_IMAGE_TAG="$JSA_IMAGE_TAG" docker compose -f "$COMPOSE_FILE" "$@"
}

prepare_source() {
  if [ -f "$REPO_ROOT/docker-compose.release.yml" ] && [ -d "$REPO_ROOT/apps/extension" ]; then
    SOURCE_DIR=$REPO_ROOT
    return
  fi
  archive_url="https://github.com/$JSA_REPOSITORY/archive/$JSA_REPOSITORY_REF.tar.gz"
  run mkdir -p "$SOURCE_DIR"
  if [ "$DRY_RUN" -eq 1 ]; then
    say "[dry-run] 下载源码归档 $archive_url 到 $SOURCE_DIR"
    return
  fi
  temp_dir=$(mktemp -d)
  trap 'rm -rf "$temp_dir"' EXIT HUP INT TERM
  curl -fL "$archive_url" -o "$temp_dir/source.tar.gz"
  tar -xzf "$temp_dir/source.tar.gz" -C "$temp_dir"
  extracted=$(find "$temp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  cp -R "$extracted"/. "$SOURCE_DIR"/
}

package_extension() {
  source_output="$SOURCE_DIR/apps/extension/.output/chrome-mv3"
  if [ -d "$source_output" ] && has_command zip; then
    if [ "$DRY_RUN" -eq 1 ]; then
      say "[dry-run] 打包 Chrome 扩展 v${JSA_EXTENSION_VERSION} 到 $EXTENSION_ZIP"
    else
      rm -f "$EXTENSION_ZIP"
      (cd "$source_output" && zip -qr "$EXTENSION_ZIP" .)
      say "✓ Chrome 扩展包：$EXTENSION_ZIP"
    fi
  else
    say "! 当前源码没有已构建扩展；请从 GitHub Actions 下载 job-search-assistant-chrome-mv3"
  fi
}

install_runner() {
  run cp "$SOURCE_DIR/scripts/automation-runner.py" "$RUNNER_SCRIPT"
  run chmod +x "$RUNNER_SCRIPT"
}

stop_runner() {
  [ -f "$RUNNER_PID" ] || return 0
  [ "$DRY_RUN" -eq 1 ] && { say "[dry-run] 停止宿主 automation runner"; return; }
  runner_pid=$(cat "$RUNNER_PID" 2>/dev/null || true)
  case "$runner_pid" in
    ''|*[!0-9]*) ;;
    *) kill "$runner_pid" 2>/dev/null || true ;;
  esac
  run rm -f "$RUNNER_PID"
}

start_runner() {
  [ "$DRY_RUN" -eq 1 ] && { say "[dry-run] 启动宿主 automation runner"; return; }
  stop_runner
  if ! has_command python3; then
    say "! 未检测到 python3，后台任务 API 可用，但宿主 runner 未启动"
    return
  fi
  nohup python3 "$RUNNER_SCRIPT" >"$RUNNER_LOG" 2>&1 &
  printf '%s\n' "$!" >"$RUNNER_PID"
  say "✓ 宿主 runner 已启动（日志：$RUNNER_LOG）"
}

wait_for_service() {
  [ "$DRY_RUN" -eq 1 ] && return 0
  say "等待本地服务健康…"
  attempts=0
  while [ "$attempts" -lt 90 ]; do
    if curl -fsS http://127.0.0.1:8765/v1/health >/dev/null 2>&1; then
      say "✓ 本地服务已就绪"
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  say "错误：本地服务未在 180 秒内就绪，请运行 docker compose -f $COMPOSE_FILE logs" >&2
  return 1
}

open_setup() {
  [ "$OPEN_SETUP" -eq 0 ] && return
  if [ "$DRY_RUN" -eq 1 ]; then say "[dry-run] 打开 $JSA_SETUP_URL"; return; fi
  if [ "$(uname -s)" = Darwin ]; then open "$JSA_SETUP_URL"
  elif has_command xdg-open; then xdg-open "$JSA_SETUP_URL" >/dev/null 2>&1 || true
  else say "请打开 $JSA_SETUP_URL"; fi
}

uninstall() {
  stop_runner
  if [ -f "$COMPOSE_FILE" ] && has_command docker; then run compose down; fi
  run rm -f "$COMPOSE_FILE" "$EXTENSION_ZIP" "$RUNNER_SCRIPT" "$RUNNER_LOG"
  say "已停止服务并移除安装器托管包。用户数据保留在 $INSTALL_DIR/data"
}

if [ "$MODE" = check ]; then
  check_environment
  exit $?
fi

if [ "$MODE" = uninstall ]; then
  uninstall
  exit 0
fi

check_environment || {
  say "请先解决以上阻塞项，再重新运行安装器。" >&2
  exit 1
}
run mkdir -p "$INSTALL_DIR"
prepare_source
run cp "$SOURCE_DIR/docker-compose.release.yml" "$COMPOSE_FILE"
package_extension
stop_runner
say "正在拉取 Web 与本地服务镜像并启动内置执行器，耗时取决于网络。"
run compose pull
run compose up -d
wait_for_service
open_setup
say "完成。首次使用向导：$JSA_SETUP_URL"
