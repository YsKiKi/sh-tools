#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════
#  sysinfo.sh · 系统体检报告
#  退出码：正常 0；仅在 --warn-only 且存在告警时返回 1
# ═══════════════════════════════════════════════════════════════════════
#
#  版权所有 (c) 2025-2026 YsKiKi
#  本文件以 MIT 许可证授权，许可证全文如下（与仓库根目录 LICENSE 一致）：
#
#  MIT License
#
#  Copyright (c) 2025-2026 YsKiKi
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
# ═══════════════════════════════════════════════════════════════════════

VERSION="1.0.0"

# 固定数字、日期、排序的输出格式
LC_ALL=C
export LC_ALL

set -u

# ── 选项默认值 ──────────────────────────────────────────────────────
ONLY=""
SKIP=""
BRIEF=0
WARNF=0
OUT=""
LIST=10
NO_COLOR_OPT=0
BRIEF_SKIP="hardware security"   # --brief 时跳过的段落
WARNF_SKIP="hardware sessions"   # --warn-only 时跳过的段落

# ═══════════════════════════════════════════════════════════════════════
#  输出小工具
# ═══════════════════════════════════════════════════════════════════════

usage() {
  cat <<'EOF'
sysinfo.sh —— 系统体检报告（只读，不改动被检查的机器）

用法：
    sh sysinfo.sh [选项]

选项：
    -b, --brief          精简模式：跳过硬件/安全段，列表只留 5 行
    -w, --warn-only      只输出结尾的告警汇总（有告警时退出码为 1）
        --only LIST      只跑指定段落，逗号分隔
        --skip LIST      跳过指定段落，逗号分隔
        --top N          每个排行显示 N 行（默认 10）
    -o, --output FILE    把报告写入文件（同时关闭颜色）
        --no-color       关闭颜色（管道输出时本来就是关的）
    -V, --version        版本号
    -h, --help           本帮助

段落名（--only / --skip 用）：
    overview  cpu  mem  disk  net  proc  systemd  containers  sessions  hardware  security

说明：
    --warn-only 会顺带跳过 hardware 与 sessions（这两段不产生告警，跳过可让 cron 更快）；
    想连它们一起跑就显式写 --only hardware,sessions。

示例：
    sh sysinfo.sh                                  # 完整报告
    sh sysinfo.sh --brief                          # 快速看一眼
    sh sysinfo.sh --only disk,mem                  # 只看磁盘和内存
    sh sysinfo.sh --skip security --top 5
    sh sysinfo.sh -o /tmp/sysinfo-$(hostname).txt  # 存成文件

在别的机器上直接跑（本站只对 192.168.1.0/24 与 tailscale 网段开放）：
    curl -fsSL http://192.168.1.72/memo/scripts/sysinfo.sh | sh
    curl -fsSL http://j4125/memo/scripts/sysinfo.sh | sh -s -- --brief
EOF
}

# 颜色：stdout 是终端时开启，写文件或管道时关闭
C_RST=""; C_B=""; C_DIM=""; C_KEY=""; C_OK=""; C_WARN=""; C_SUB=""
setup_color() {
  if [ "$NO_COLOR_OPT" = 0 ] && [ -z "${NO_COLOR:-}" ] && [ -z "$OUT" ] && [ -t 1 ]; then
    C_RST=$(printf '\033[0m');  C_B=$(printf '\033[1m');   C_DIM=$(printf '\033[2m')
    C_KEY=$(printf '\033[36m'); C_OK=$(printf '\033[32m'); C_WARN=$(printf '\033[33m')
    C_SUB=$(printf '\033[35m')
  fi
}

# --warn-only：打印类函数静默返回，采集与告警累积照常
sec() {   # 段标题
  [ "$WARNF" = 1 ] && return 0
  SEC_N=$((SEC_N + 1))
  printf '\n%s── %d. %s %s\n' "$C_B" "$SEC_N" "$1" "$(rule)"
  printf '%s' "$C_RST"
}
rule() { printf '────────────────────────────────────────────────────────'; }
sub() {   # 子标题
  [ "$WARNF" = 1 ] && return 0
  printf '\n  %s▸ %s%s\n' "$C_SUB" "$1" "$C_RST"
}
kv() {    # 键值行：中文标签用全角冒号
  [ "$WARNF" = 1 ] && return 0
  printf '  %s%s%s：%s\n' "$C_KEY" "$1" "$C_RST" "$2"
}
dim() {   # 说明 / 提示
  [ "$WARNF" = 1 ] && return 0
  printf '    %s%s%s\n' "$C_DIM" "$1" "$C_RST"
}
blk() {   # 多行原始输出缩进后打印（--warn-only 时读空但不显示）
  # 始终读完 stdin
  if [ "$WARNF" = 1 ]; then cat >/dev/null; return 0; fi
  sed 's/^/    /'
}

# 告警累积
WARN_COUNT=0
WARNINGS=""
warn_add() {
  WARN_COUNT=$((WARN_COUNT + 1))
  WARNINGS="${WARNINGS}  [$WARN_COUNT] $1
"
}

die() { printf 'sysinfo.sh: %s\n' "$1" >&2; exit 2; }

# ═══════════════════════════════════════════════════════════════════════
#  通用取值函数
# ═══════════════════════════════════════════════════════════════════════

have() { command -v "$1" >/dev/null 2>&1; }

pct() {   # pct USED TOTAL → 整数百分比
  if [ "${2:-0}" -gt 0 ]; then printf '%d' $(( $1 * 100 / $2 )); else printf '0'; fi
}

kb_human() {  # KiB → 人类可读
  _kb=${1:-0}
  if   [ "$_kb" -ge 1048576 ]; then awk -v k="$_kb" 'BEGIN{printf "%.2f GiB", k/1048576}'
  elif [ "$_kb" -ge 1024 ];    then awk -v k="$_kb" 'BEGIN{printf "%.1f MiB", k/1024}'
  else printf '%d KiB' "$_kb"; fi
}

sec_to_human() {
  _s=${1:-0}
  _d=$((_s / 86400)); _h=$(((_s % 86400) / 3600)); _m=$(((_s % 3600) / 60))
  if   [ "$_d" -gt 0 ]; then printf '%d 天 %d 小时 %d 分' "$_d" "$_h" "$_m"
  elif [ "$_h" -gt 0 ]; then printf '%d 小时 %d 分' "$_h" "$_m"
  else printf '%d 分' "$_m"; fi
}

os_pretty() {
  if [ -r /etc/os-release ]; then
    _p=$(. /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-${NAME:-}}")
    if [ -n "$_p" ]; then printf '%s' "$_p"; return; fi
  fi
  if [ -r /etc/redhat-release ]; then head -n 1 /etc/redhat-release; return; fi
  if [ -r /etc/alpine-release ]; then printf 'Alpine Linux %s' "$(cat /etc/alpine-release 2>/dev/null)"; return; fi
  if have sw_vers; then printf 'macOS %s' "$(sw_vers -productVersion 2>/dev/null)"; return; fi
  uname -s 2>/dev/null || printf '未知'
}

cpu_model() {
  if [ -r /proc/cpuinfo ]; then
    _m=$(awk -F': ' '/^model name|^Model|^Hardware|^cpu model/{print $2; exit}' /proc/cpuinfo 2>/dev/null)
    if [ -n "${_m:-}" ]; then printf '%s' "$_m"; return; fi
  fi
  if have lscpu; then
    _m=$(lscpu 2>/dev/null | awk -F': +' '/^Model name/{print $2; exit}')
    if [ -n "${_m:-}" ]; then printf '%s' "$_m"; return; fi
  fi
  if have sysctl; then sysctl -n machdep.cpu.brand_string 2>/dev/null; return; fi
  printf '未知'
}

cpu_cores() {
  if have nproc; then _c=$(nproc 2>/dev/null); [ -n "${_c:-}" ] && { printf '%s' "$_c"; return; }; fi
  if have getconf; then _c=$(getconf _NPROCESSORS_ONLN 2>/dev/null); [ -n "${_c:-}" ] && { printf '%s' "$_c"; return; }; fi
  if [ -r /proc/cpuinfo ]; then grep -c '^processor' /proc/cpuinfo 2>/dev/null && return; fi
  printf '?'
}

cpu_freq() {
  _f=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)
  if [ -n "${_f:-}" ]; then printf '%d MHz' $((_f / 1000)); return; fi
  if have lscpu; then
    _m=$(lscpu 2>/dev/null | awk -F': +' '/^CPU MHz/{print $2; exit}')
    [ -n "${_m:-}" ] && { printf '%s MHz' "$_m"; return; }
  fi
  printf ''
}

uptime_seconds() {
  if [ -r /proc/uptime ]; then cut -d' ' -f1 /proc/uptime 2>/dev/null; return; fi
  if have sysctl; then
    _b=$(sysctl -n kern.boottime 2>/dev/null | sed 's/.*sec *= *\([0-9]*\).*/\1/')
    [ -n "${_b:-}" ] && { echo $(( $(date +%s) - _b )); return; }
  fi
  printf ''
}

uptime_human() {
  _s=$(uptime_seconds)
  if [ -n "${_s:-}" ]; then sec_to_human "${_s%%.*}"
  elif have uptime; then uptime -p 2>/dev/null || uptime 2>/dev/null
  else printf '未知'; fi
}

boot_time() {
  _s=$(uptime_seconds)
  if [ -n "${_s:-}" ]; then
    _s=${_s%%.*}
    _now=$(date +%s 2>/dev/null)
    if [ -n "${_now:-}" ]; then
      _e=$((_now - _s))          # 开机时刻（epoch 秒）
      date -d "@$_e" '+%Y-%m-%d %H:%M' 2>/dev/null \
        || date -r "$_e" '+%Y-%m-%d %H:%M' 2>/dev/null \
        || printf '约 %s 前' "$(sec_to_human "$_s")"
    else
      printf '约 %s 前' "$(sec_to_human "$_s")"
    fi
  else printf '未知'; fi
}

load_line() {
  if [ -r /proc/loadavg ]; then
    # shellcheck disable=SC2046
    set -- $(cat /proc/loadavg 2>/dev/null)
    _n=$(cpu_cores)
    awk -v a="$1" -v b="$2" -v c="$3" -v n="$_n" 'BEGIN{
      if (n + 0 > 0) printf "%s / %s / %s（%s 核，单核 %.2f）", a, b, c, n, a / n;
      else           printf "%s / %s / %s", a, b, c }'
  elif have uptime; then
    uptime 2>/dev/null | sed 's/.*load average[s]*: *//'
  else printf '未知'; fi
}

virt_type() {
  if have systemd-detect-virt; then
    _v=$(systemd-detect-virt 2>/dev/null)
    case "${_v:-}" in
      none)     printf '物理机（未检测到虚拟化）'; return ;;
      ""|unknown) : ;;
      *)        printf '%s' "$_v"; return ;;
    esac
  fi
  if [ -r /proc/cpuinfo ] && grep -q hypervisor /proc/cpuinfo 2>/dev/null; then
    printf '虚拟机（CPU hypervisor 位）'; return
  fi
  if [ -r /sys/class/dmi/id/sys_vendor ]; then
    _ven=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)
    _mod=$(cat /sys/class/dmi/id/product_name 2>/dev/null)
    if [ -n "${_ven:-}${_mod:-}" ]; then printf '%s %s' "$_ven" "$_mod"; return; fi
  fi
  printf '未知'
}

mem_total_human() {
  if [ -r /proc/meminfo ]; then
    _t=$(awk '/^MemTotal:/{print $2; exit}' /proc/meminfo 2>/dev/null)
    [ -n "${_t:-}" ] && { kb_human "$_t"; return; }
  fi
  if have sysctl; then
    _b=$(sysctl -n hw.memsize 2>/dev/null)
    [ -n "${_b:-}" ] && { awk -v b="$_b" 'BEGIN{printf "%.1f GiB", b/1073741824}'; return; }
  fi
  printf '未知'
}

ntp_state() {
  if have timedatectl; then
    _n=$(timedatectl show -p NTPSynchronized --value 2>/dev/null)
    case "${_n:-}" in
      yes) printf '已同步（systemd-timesyncd/chrony）' ;;
      no)  printf '未同步' ;;
      *)   printf '未知' ;;
    esac
  elif have chronyc; then
    chronyc tracking >/dev/null 2>&1 && printf 'chrony 运行中' || printf 'chrony 未运行'
  else printf '未检测到时间同步服务'; fi
}

# 探测 ps 排序参数，不支持则回退到 ps aux
top_cpu() {
  sub "CPU 占用排行（前 $LIST 个）"
  if ps -eo pcpu,pmem,pid,user,comm --sort=-pcpu >/dev/null 2>&1; then
    ps -eo pcpu,pmem,pid,user,comm --sort=-pcpu 2>/dev/null | head -n $((LIST + 1)) | blk
  elif have ps; then
    ps aux 2>/dev/null | sort -k3 -rn | head -n $((LIST + 1)) | blk
  fi
}

top_mem() {
  sub "内存占用排行（前 $LIST 个）"
  if ps -eo pmem,pcpu,pid,user,comm --sort=-pmem >/dev/null 2>&1; then
    ps -eo pmem,pcpu,pid,user,comm --sort=-pmem 2>/dev/null | head -n $((LIST + 1)) | blk
  elif have ps; then
    ps aux 2>/dev/null | sort -k4 -rn | head -n $((LIST + 1)) | blk
  fi
}

# ═══════════════════════════════════════════════════════════════════════
#  各段落
# ═══════════════════════════════════════════════════════════════════════

sec_overview() {
  sec_on overview || return 0
  sec "概览"
  kv "主机名"     "$(hostname 2>/dev/null || cat /proc/sys/kernel/hostname 2>/dev/null || printf '?')"
  kv "操作系统"   "$(os_pretty)"
  kv "内核"       "$(uname -sr 2>/dev/null || printf '?')（$(uname -m 2>/dev/null || printf '?')）"
  kv "虚拟化"     "$(virt_type)"
  kv "CPU"        "$(cpu_model)（$(cpu_cores) 核）"
  kv "内存"       "$(mem_total_human)"
  kv "开机时间"   "$(boot_time)"
  kv "已运行"     "$(uptime_human)"
  kv "当前时间"   "$(date '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null)"
  kv "时间同步"   "$(ntp_state)"
  kv "负载 1/5/15" "$(load_line)"
  return 0
}

sec_cpu() {
  sec_on cpu || return 0
  sec "CPU"
  kv "型号"     "$(cpu_model)"
  kv "逻辑核心" "$(cpu_cores)"
  _f=$(cpu_freq); [ -n "$_f" ] && kv "当前频率" "$_f"
  _g=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
  [ -n "${_g:-}" ] && kv "调频策略" "$_g"
  if [ -r /proc/stat ]; then
    kv "累计上下文切换" "$(awk '/^ctxt/{print $2}' /proc/stat 2>/dev/null)"
    kv "累计中断次数"   "$(awk '/^intr/{print $2}' /proc/stat 2>/dev/null)"
  fi
  _n=$(cpu_cores)
  _l1=$(awk '{print $1}' /proc/loadavg 2>/dev/null)
  if [ -n "${_l1:-}" ] && [ "${_n:-0}" -gt 0 ]; then
    awk -v l="$_l1" -v n="$_n" 'BEGIN{ if (l > n * 2) exit 7; exit 0 }' \
      && : || warn_add "系统负载偏高：1 分钟负载 $_l1，共 $_n 核"
  fi
  top_cpu
  return 0
}

sec_mem() {
  sec_on mem || return 0
  sec "内存与交换"
  if [ -r /proc/meminfo ]; then
    # awk 输出字段：总计 可用 缓存+缓冲 交换总 交换空闲 脏页
    # shellcheck disable=SC2046
    set -- $(awk '
      /^MemTotal:/     { t  = $2 }
      /^MemAvailable:/ { a  = $2 }
      /^Buffers:/      { b  = $2 }
      /^Cached:/       { c  = $2 }
      /^SwapTotal:/    { st = $2 }
      /^SwapFree:/     { sf = $2 }
      /^Dirty:/        { d  = $2 }
      END { if (a == "") a = b + c; printf "%d %d %d %d %d %d", t, a, b + c, st, sf, d }' /proc/meminfo)
    _mt=${1:-0}; _ma=${2:-0}; _mc=${3:-0}; _st=${4:-0}; _sf=${5:-0}; _dirty=${6:-0}
    _used=$((_mt - _ma))
    kv "总内存"       "$(kb_human "$_mt")"
    kv "已用 / 可用"  "$(kb_human "$_used") / $(kb_human "$_ma")（使用率 $(pct "$_used" "$_mt")%）"
    kv "缓存与缓冲"   "$(kb_human "$_mc")"
    kv "脏页(待回写)" "$(kb_human "$_dirty")"
    if [ "$_st" -gt 0 ]; then
      _su=$((_st - _sf))
      kv "交换分区" "共 $(kb_human "$_st")，已用 $(kb_human "$_su")（$(pct "$_su" "$_st")%）"
      [ "$(pct "$_su" "$_st")" -ge 50 ] && warn_add "交换分区使用率 $(pct "$_su" "$_st")%，内存可能吃紧"
    else
      kv "交换分区" "未启用"
    fi
    [ "$(pct "$_used" "$_mt")" -ge 90 ] && warn_add "内存使用率 $(pct "$_used" "$_mt")%，接近耗尽"
  elif have free; then
    free -h 2>/dev/null | blk
  elif have vm_stat; then
    dim "macOS：vm_stat 前几行（单位 page，需自行换算）"
    vm_stat 2>/dev/null | head -n 8 | blk
  else
    dim "无法读取内存信息"
  fi
  top_mem
  return 0
}

sec_disk() {
  sec_on disk || return 0
  sec "磁盘与文件系统"

  sub "容量（已过滤 tmpfs / devtmpfs / squashfs）"
  if df -hT -x tmpfs -x devtmpfs -x squashfs >/dev/null 2>&1; then
    df -hT -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | blk
  else
    df -h 2>/dev/null | blk          # BSD / macOS 的 df 无 -T
  fi

  # 使用率告警：解析 df -P -k 输出（列位置固定）
  _hot=$(df -P -k 2>/dev/null | awk '
    NR > 1 {
      fs = $1
      if (fs ~ /^(tmpfs|devtmpfs|squashfs|udev|none|shm)$/) next
      u = $5; sub(/%/, "", u)
      if (u + 0 >= 85) printf "%s 已用 %s%%（挂载点 %s）\n", fs, u, $6
    }')
  if [ -n "$_hot" ]; then
    while IFS= read -r _line; do
      [ -n "$_line" ] && warn_add "磁盘空间告警：$_line"
    done <<EOF
$_hot
EOF
  fi

  sub "inode（只显示使用率 ≥ 50% 的）"
  if df -i -x tmpfs -x devtmpfs >/dev/null 2>&1; then
    df -i -x tmpfs -x devtmpfs 2>/dev/null | awk 'NR == 1 || ($5 + 0) >= 50' | blk
    dim "（inode 用满时同样无法新建文件，但 df -h 看着还有空间）"
  else
    df -i 2>/dev/null | awk 'NR == 1 || ($5 + 0) >= 50' | blk
  fi

  sub "只读挂载的真实设备（/proc/mounts 里带 ro 的块设备）"
  if [ -r /proc/mounts ]; then
    _ro=$(awk '$1 ~ /^\/dev\// && $4 ~ /(^|,)ro(,|$)/ { print $2 }' /proc/mounts 2>/dev/null)
    if [ -n "$_ro" ]; then
      printf '%s\n' "$_ro" | blk
      case " $_ro " in *" / "*) warn_add "根文件系统处于只读挂载状态，多数写入都会失败" ;; esac
    else
      dim "无（根分区正常可写）"
    fi
  fi

  if have zpool; then
    sub "ZFS 池"
    zpool list 2>/dev/null | blk || dim "需要 root 才能查询"
  fi
  return 0
}

sec_net() {
  sec_on net || return 0
  sec "网络"

  sub "接口地址"
  if have ip && ip -brief addr show >/dev/null 2>&1; then
    ip -brief addr show 2>/dev/null | grep -v '^lo ' | blk
  elif have ip; then
    ip -o addr show 2>/dev/null | awk '$2 != "lo" { printf "%-10s %-6s %s\n", $2, $3, $4 }' | blk
  elif have ifconfig; then
    ifconfig -a 2>/dev/null | grep -E '^[a-z0-9]+:|inet ' | blk
  else
    dim "没有 ip / ifconfig，无法列出地址"
  fi

  sub "默认路由"
  if have ip; then
    _dr=$(ip route show default 2>/dev/null); [ -n "$_dr" ] && printf '%s\n' "$_dr" | blk || dim "无默认路由"
  elif have netstat; then
    netstat -rn 2>/dev/null | awk '$1 == "default" || $1 == "0.0.0.0"' | blk
  fi

  sub "DNS"
  if [ -r /etc/resolv.conf ]; then
    _dns=$(awk '/^nameserver/{printf "%s ", $2}' /etc/resolv.conf 2>/dev/null)
    kv "nameserver" "${_dns:-无}"
    _search=$(awk '/^search|^domain/{ $1=""; sub(/^ /,""); print; exit }' /etc/resolv.conf 2>/dev/null)
    [ -n "${_search:-}" ] && kv "搜索域" "$_search"
  else
    dim "读不到 /etc/resolv.conf"
  fi

  sub "监听端口"
  if have ss; then
    _listen=$(ss -tuln 2>/dev/null | awk 'NR > 1 { printf "%-5s %s\n", $1, $5 }' | sort -u)
    _port_n=$(printf '%s\n' "$_listen" | grep -c .)
    kv "监听条目" "$_port_n"
    printf '%s\n' "$_listen" | head -n "$LIST" | blk
    [ "$_port_n" -gt "$LIST" ] && dim "… 其余 $((_port_n - LIST)) 条省略（--top N 可调整）"
    dim "跨用户看进程名需要 root：sudo ss -tulnp"
  elif have netstat; then
    netstat -tuln 2>/dev/null | awk 'NR <= 2 || $1 ~ /^(tcp|udp)/ { printf "%-5s %s\n", $1, $4 }' | head -n $((LIST + 2)) | blk
  else
    dim "没有 ss / netstat"
  fi

  if have ss; then
    sub "TCP 连接状态统计"
    ss -tan 2>/dev/null | awk 'NR > 1 { c[$1]++ } END { for (k in c) printf "%s=%d  ", k, c[k]; print "" }' | blk
    _est=$(ss -tan 2>/dev/null | awk 'NR > 1 && $1 == "ESTAB" { n++ } END { print n + 0 }')
    kv "已建立连接" "$_est"
  fi

  sub "防火墙"
  if have ufw; then
    _u=$(ufw status 2>/dev/null | head -n 1)
    case "${_u:-}" in
      *active*)   kv "ufw" "已启用" ;;
      *inactive*) kv "ufw" "未启用" ;;
      *)          kv "ufw" "需 root 才能查看（sudo ufw status）" ;;
    esac
  fi
  if have nft; then
    _n=$(nft list ruleset 2>/dev/null | grep -c .)
    if [ "${_n:-0}" -gt 0 ]; then kv "nftables" "规则输出 $_n 行"
    else kv "nftables" "无规则或需 root"; fi
  fi
  if have iptables; then
    _n=$(iptables -S 2>/dev/null | grep -c .)
    if [ "${_n:-0}" -gt 0 ]; then kv "iptables" "规则 $_n 条"
    else kv "iptables" "无规则或需 root"; fi
  fi
  if have firewall-cmd; then kv "firewalld" "$(firewall-cmd --state 2>/dev/null || printf '需 root')"; fi
  if ! have ufw && ! have nft && ! have iptables && ! have firewall-cmd; then
    dim "未发现常见防火墙工具"
  fi

  if have tailscale; then
    sub "Tailscale"
    _ts=$(tailscale ip -4 2>/dev/null | head -n 1)
    kv "本机地址" "${_ts:-查询失败（可能需要 sudo 或 operator 授权）}"
  fi
  return 0
}

sec_proc() {
  sec_on proc || return 0
  sec "进程与调度"

  _total=$(ps -e --no-headers 2>/dev/null | grep -c .)
  if [ "${_total:-0}" -eq 0 ]; then
    _total=$(ps -e 2>/dev/null | grep -c .)
    [ "$_total" -gt 0 ] && _total=$((_total - 1))   # 去掉表头
  fi
  kv "进程总数" "$_total"

  if [ -r /proc/loadavg ]; then
    # 第 4 字段形如 "2/483"：就绪线程 / 总线程
    _thr=$(awk '{print $4}' /proc/loadavg 2>/dev/null)
    kv "运行中/总线程" "$_thr"
  fi

  _z=$(ps -eo stat 2>/dev/null | grep -c '^Z')
  if [ "${_z:-0}" -gt 0 ]; then
    kv "僵尸进程" "$_z"
    ps -eo pid,ppid,stat,comm 2>/dev/null | awk '$3 ~ /^Z/' | blk
    warn_add "存在 $_z 个僵尸进程（父进程未回收，通常是程序 bug）"
  else
    kv "僵尸进程" "无"
  fi

  if have vmstat; then
    sub "CPU / IO 瞬时采样（vmstat 1 2 的最后一行）"
    vmstat 1 2 2>/dev/null | tail -n 1 | blk
    dim "r=等待运行进程  b=不可中断睡眠  wa=IO 等待占比  st=被虚拟化偷走的时间"
    _wa=$(vmstat 1 2 2>/dev/null | tail -n 1 | awk '{print $16}')
    if [ -n "${_wa:-}" ] && [ "${_wa:-0}" -ge 20 ]; then
      warn_add "IO 等待（wa）达 ${_wa}%，磁盘可能是瓶颈"
    fi
  fi
  return 0
}

sec_systemd() {
  sec_on systemd || return 0
  if ! have systemctl; then
    sec "systemd"
    dim "本机没有 systemctl（非 systemd 系统），跳过"
    return 0
  fi
  sec "systemd"
  kv "运行状态" "$(systemctl is-system-running 2>/dev/null || printf '无法查询')"

  _run=$(systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null | grep -c .)
  kv "运行中服务" "$_run"

  _failed=$(systemctl --failed --no-legend --no-pager 2>/dev/null | grep -v '^$')
  _fn=$(printf '%s\n' "$_failed" | grep -c .)
  kv "失败单元" "$_fn"
  if [ "$_fn" -gt 0 ]; then
    printf '%s\n' "$_failed" | head -n "$LIST" | blk
    while IFS= read -r _line; do
      [ -n "$_line" ] && warn_add "systemd 单元失败：$(printf '%s' "$_line" | awk '{print $1}')"
    done <<EOF
$(printf '%s\n' "$_failed" | head -n 5)
EOF
  fi

  _boot=$(systemd-analyze 2>/dev/null | head -n 1)
  [ -n "${_boot:-}" ] && kv "本次启动耗时" "$_boot"

  sub "定时任务（systemd timers，按触发时间排序）"
  systemctl list-timers --no-pager 2>/dev/null | head -n $((LIST + 1)) | blk

  sub "本次启动以来的错误级日志（最后 5 条）"
  if have journalctl; then
    _err=$(journalctl -p err -b --no-pager -q 2>/dev/null | tail -n 5)
    _en=$(journalctl -p err -b --no-pager -q 2>/dev/null | grep -c .)
    if [ -n "$_err" ]; then
      printf '%s\n' "$_err" | blk
      kv "错误日志条数" "$_en"
      [ "${_en:-0}" -ge 20 ] && warn_add "本次启动已有 $_en 条 error 级日志，建议翻 journalctl -p err -b"
    else
      dim "无错误日志（或当前用户无权限：加入 adm / systemd-journal 组可看）"
    fi
  else
    dim "没有 journalctl"
  fi
  return 0
}

sec_containers() {
  sec_on containers || return 0
  if ! have docker && ! have podman; then
    sec "容器"
    dim "未安装 docker / podman，跳过"
    return 0
  fi
  sec "容器"

  if have docker; then
    _ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null)
    if [ -n "${_ver:-}" ]; then
      kv "Docker 服务端" "$_ver"
      _all=$(docker ps -aq 2>/dev/null | grep -c .)
      _run=$(docker ps -q 2>/dev/null | grep -c .)
      kv "容器 运行/全部" "$_run / $_all"
      if [ "${_run:-0}" -gt 0 ]; then
        sub "运行中的容器"
        docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | blk
      fi
      _bad=$(docker ps --filter health=unhealthy --format '{{.Names}}' 2>/dev/null)
      if [ -n "${_bad:-}" ]; then
        kv "不健康容器" "$(printf '%s' "$_bad" | tr '\n' ' ')"
        warn_add "存在 unhealthy 容器：$(printf '%s' "$_bad" | tr '\n' ' ')"
      fi
      _restart=$(docker ps --filter status=restarting --format '{{.Names}}' 2>/dev/null)
      [ -n "${_restart:-}" ] && warn_add "容器反复重启：$(printf '%s' "$_restart" | tr '\n' ' ')"
      sub "Docker 磁盘占用"
      docker system df 2>/dev/null | blk
    else
      dim "docker 命令在，但连不上守护进程 / 当前用户不在 docker 组"
      dim "  → 临时：sudo docker ps    永久：sudo usermod -aG docker \$USER 后重新登录"
    fi
  fi

  if have podman; then
    sub "Podman"
    _p=$(podman ps --format '{{.Names}} {{.Image}} {{.Status}}' 2>/dev/null)
    if [ -n "${_p:-}" ]; then printf '%s\n' "$_p" | blk
    else dim "无运行中的 podman 容器（或需要 root）"; fi
  fi
  return 0
}

sec_sessions() {
  sec_on sessions || return 0
  sec "终端会话与登录"

  if have tmux; then
    _t=$(tmux ls 2>/dev/null)
    sub "tmux"
    if [ -n "${_t:-}" ]; then printf '%s\n' "$_t" | blk; else dim "无活跃会话"; fi
  fi

  if have screen; then
    _s=$(screen -ls 2>/dev/null | grep -E '\((Attached|Detached)\)')
    sub "screen"
    if [ -n "${_s:-}" ]; then printf '%s\n' "$_s" | blk; else dim "无活跃会话"; fi
  fi

  sub "当前登录用户"
  if have who; then
    _w=$(who 2>/dev/null)
    if [ -n "${_w:-}" ]; then printf '%s\n' "$_w" | blk; else dim "无（只有你自己这次执行）"; fi
  fi

  sub "最近登录记录"
  if have last; then last -n 5 2>/dev/null | head -n 5 | blk; else dim "没有 last 命令"; fi
  return 0
}

sec_hardware() {
  sec_on hardware || return 0
  sec "硬件"

  sub "显示设备"
  if have lspci; then
    _gpu=$(lspci -nn 2>/dev/null | grep -Ei 'vga|3d|display')
    if [ -n "${_gpu:-}" ]; then printf '%s\n' "$_gpu" | blk; else dim "无匹配的显示设备"; fi
  else
    dim "没有 lspci（装 pciutils）"
  fi
  if have nvidia-smi; then
    sub "NVIDIA GPU"
    nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu \
      --format=csv,noheader 2>/dev/null | blk
  fi

  sub "块设备"
  if have lsblk; then
    lsblk -d -o NAME,SIZE,TYPE,ROTA,MODEL 2>/dev/null | blk
    dim "ROTA=1 为机械盘，ROTA=0 为固态"
  fi

  sub "温度"
  _temp=0
  if have sensors; then
    sensors 2>/dev/null | grep -E '°C|°F' | head -n 12 | blk
    _temp=1
  fi
  if [ "$_temp" = 0 ]; then
    {
      for _z in /sys/class/thermal/thermal_zone*; do
        [ -r "$_z/temp" ] || continue
        _t=$(cat "$_z/temp" 2>/dev/null)
        _ty=$(cat "$_z/type" 2>/dev/null)
        awk -v t="$_t" -v ty="$_ty" 'BEGIN{printf "    %s：%.1f ℃\n", ty, t/1000}'
      done
      printf '    %s\n' "（无 lm-sensors，数据取自 /sys/class/thermal；sudo apt install lm-sensors 更详细）"
    } | blk
  fi
  return 0
}

sec_security() {
  sec_on security || return 0
  sec "安全与合规"

  sub "本机账号"
  _root=$(awk -F: '$3 == 0 { printf "%s ", $1 }' /etc/passwd 2>/dev/null)
  kv "UID 0 账号" "${_root:-未知}"
  _nopw=$(awk -F: '$2 == "" { printf "%s ", $1 }' /etc/shadow 2>/dev/null)
  if [ -n "${_nopw:-}" ]; then
    kv "空密码账号" "$_nopw"
    warn_add "存在空密码账号：$_nopw"
  else
    kv "空密码账号" "无（或 /etc/shadow 不可读，需 root 复核）"
  fi

  sub "SSH 主配置（/etc/ssh/sshd_config，不含 Include 的子文件）"
  if [ -r /etc/ssh/sshd_config ]; then
    for _k in Port PermitRootLogin PasswordAuthentication PubkeyAuthentication; do
      _v=$(awk -v k="$_k" 'tolower($1) == tolower(k) { print $2 }' /etc/ssh/sshd_config 2>/dev/null | tail -n 1)
      kv "$_k" "${_v:-未显式设置（用默认）}"
    done
    case "$(awk 'tolower($1) == "permitrootlogin" { print $2 }' /etc/ssh/sshd_config 2>/dev/null | tail -n 1)" in
      yes) warn_add "SSH 允许 root 直接登录（PermitRootLogin yes）" ;;
    esac
    case "$(awk 'tolower($1) == "passwordauthentication" { print $2 }' /etc/ssh/sshd_config 2>/dev/null | tail -n 1)" in
      yes) warn_add "SSH 开着密码登录（PasswordAuthentication yes），建议改密钥登录" ;;
    esac
    dim "Ubuntu 24.04 起主文件多为 Include 片段，准确值请用 sudo sshd -T | grep -Ei 'port|permitrootlogin|passwordauth'"
  else
    dim "读不到 /etc/ssh/sshd_config"
  fi

  _ak="${HOME:-/root}/.ssh/authorized_keys"
  if [ -r "$_ak" ]; then kv "authorized_keys 条数" "$(grep -c . "$_ak" 2>/dev/null)"; fi

  sub "强制访问控制"
  if have getenforce; then
    kv "SELinux" "$(getenforce 2>/dev/null)"
  elif [ -r /sys/fs/selinux/enforce ]; then
    kv "SELinux" "$([ "$(cat /sys/fs/selinux/enforce 2>/dev/null)" = 1 ] && printf 'Enforcing' || printf 'Permissive')"
  else
    kv "SELinux" "未启用"
  fi
  if [ -r /sys/module/apparmor/parameters/enabled ]; then
    kv "AppArmor" "$(grep -qi '^Y' /sys/module/apparmor/parameters/enabled 2>/dev/null && printf '已启用' || printf '未启用')"
  fi

  sub "补丁状态"
  if have apt-get; then
    _up=$(apt-get -s -o Debug::NoLocking=true upgrade 2>/dev/null | grep -c '^Inst ')
    kv "可升级软件包" "${_up:-0}（仅用本地索引模拟，未联网）"
    [ "${_up:-0}" -ge 20 ] && warn_add "有 $_up 个软件包可升级，建议安排一次 apt upgrade"
  elif have dnf; then
    _up=$(dnf -q check-update 2>/dev/null | grep -c .)
    kv "可升级软件包" "${_up:-0}（check-update，可能联网）"
  elif have apk; then
    dim "Alpine：用 apk version -l '<' 查看可升级包"
  fi

  if [ -f /run/reboot-required ] || [ -f /var/run/reboot-required ]; then
    kv "待重启" "是（内核或关键库更新过）"
    warn_add "系统要求重启：/run/reboot-required 存在"
  else
    kv "待重启" "否"
  fi

  _kr=$(uname -r 2>/dev/null)
  _new=$(ls -1 /boot/vmlinuz-* 2>/dev/null | sed 's#.*/vmlinuz-##' | sort -V 2>/dev/null | tail -n 1)
  if [ -n "${_new:-}" ] && [ "${_kr:-}" != "$_new" ]; then
    kv "内核 运行/最新" "$_kr / $_new"
    warn_add "当前内核 $_kr 不是已安装的最新内核 $_new（重启后生效）"
  fi

  if have fail2ban-client; then
    _j=$(fail2ban-client status 2>/dev/null | awk -F'\t' '/Jail list/{print $2}')
    kv "fail2ban 监狱" "${_j:-需 root 才能查询}"
  fi
  return 0
}

# ═══════════════════════════════════════════════════════════════════════
#  段落开关与汇总
# ═══════════════════════════════════════════════════════════════════════

sec_on() {   # $1 = 段落名
  _found=0
  for _s in $ONLY; do [ "$_s" = "$1" ] && _found=1; done
  if [ -n "$ONLY" ] && [ "$_found" = 0 ]; then return 1; fi
  for _s in $SKIP; do [ "$_s" = "$1" ] && return 1; done
  if [ "$WARNF" = 1 ]; then
    for _s in $WARNF_SKIP; do [ "$_s" = "$1" ] && return 1; done
  fi
  if [ "$BRIEF" = 1 ]; then
    for _s in $BRIEF_SKIP; do [ "$_s" = "$1" ] && return 1; done
  fi
  return 0
}

sec_summary() {
  if [ "$WARNF" = 1 ]; then printf '%s%s%s\n' "$C_B" "$(rule)" "$C_RST"
  else printf '\n%s%s%s\n' "$C_B" "$(rule)" "$C_RST"; fi
  if [ "$WARN_COUNT" -eq 0 ]; then
    printf '%s✔ 体检结论：未发现明显异常%s\n' "$C_OK" "$C_RST"
  else
    printf '%s⚠ 体检结论：%d 项需要关注%s\n%s' "$C_WARN" "$WARN_COUNT" "$C_RST" "$WARNINGS"
  fi
  [ "$WARNF" = 0 ] && dim "提示：--brief 精简 / --only disk,mem 只看某几段 / -o 文件 存盘 / --warn-only 只输出告警"
  return 0
}

# ═══════════════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════════════

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)    usage; exit 0 ;;
    -V|--version) printf 'sysinfo.sh %s\n' "$VERSION"; exit 0 ;;
    -b|--brief)   BRIEF=1; LIST=5 ;;
    -w|--warn-only) WARNF=1 ;;
    --no-color)   NO_COLOR_OPT=1 ;;
    --top)        [ -n "${2:-}" ] || die "--top 需要一个数字"; LIST=$2; shift ;;
    -o|--output)  [ -n "${2:-}" ] || die "-o 需要一个文件路径"; OUT=$2; shift ;;
    --only)       [ -n "${2:-}" ] || die "--only 需要一个列表，如 cpu,mem"; ONLY=$(printf '%s' "$2" | tr ',' ' '); shift ;;
    --skip)       [ -n "${2:-}" ] || die "--skip 需要一个列表，如 security"; SKIP=$(printf '%s' "$2" | tr ',' ' '); shift ;;
    --)           shift; break ;;
    *)            printf 'sysinfo.sh: 未知选项 %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$LIST" in
  ''|*[!0-9]*) die "--top 必须是正整数" ;;
esac

setup_color

# -o：正文写入文件，完成提示仍回终端（fd 3 保存原始 stdout）
if [ -n "$OUT" ]; then
  exec 3>&1
  # 可写性探测放在子 shell 中执行，失败只影响子 shell
  if ! ( : >"$OUT" ) 2>/dev/null; then
    printf 'sysinfo.sh: 无法写入 %s（目录不存在或不可写？）\n' "$OUT" >&2
    exit 2
  fi
  exec >"$OUT" 2>&1
fi

SEC_N=0

if [ "$WARNF" = 1 ]; then
  printf '[warn-only] %s · %s\n' \
    "$(hostname 2>/dev/null || printf '?')" "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
else
  printf '%s════════════════════════════════════════════════════════════%s\n' "$C_B" "$C_RST"
  printf '%s  sysinfo.sh v%s · 只读系统体检报告%s\n' "$C_B" "$VERSION" "$C_RST"
  printf '%s  采集时间 %s · 主机 %s%s\n' "$C_DIM" \
    "$(date '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null)" \
    "$(hostname 2>/dev/null || printf '?')" "$C_RST"
  printf '%s════════════════════════════════════════════════════════════%s\n' "$C_B" "$C_RST"
fi

sec_overview
sec_cpu
sec_mem
sec_disk
sec_net
sec_proc
sec_systemd
sec_containers
sec_sessions
sec_hardware
sec_security
sec_summary

if [ -n "$OUT" ]; then
  exec 1>&3 2>&3
  exec 3>&-
  printf '报告已写入 %s\n' "$OUT"
fi

# --warn-only 且有告警时返回 1
if [ "$WARNF" = 1 ] && [ "$WARN_COUNT" -gt 0 ]; then exit 1; fi
exit 0