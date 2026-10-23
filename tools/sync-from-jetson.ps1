# 从 Jetson 一键同步源码到本仓库
#
# 用法（Windows PowerShell，工作目录=仓库根）：
#   .\tools\sync-from-jetson.ps1                 # 默认走 USB 地址
#   .\tools\sync-from-jetson.ps1 -Host 172.20.10.8
#
# 做的事：
#   1. 在 Jetson 上打包 ~/jiaoda、FAST-LIVO2 配置、雷达配置、systemd 单元
#   2. 拷回本地并解压覆盖 docs/source/
#   3. 打印文件数与差异提示
#
# 目的：避免"机器上改了、仓库里还是旧版"。

param(
    [string]$Host = "192.168.55.1",
    [string]$Out  = "docs/source"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1. 在 Jetson 上打包 ==" -ForegroundColor Cyan
$remote = @'
set -e
cd /tmp
rm -f sync.tar.gz
tar czf /tmp/sync.tar.gz --exclude=__pycache__ --exclude="*.log" \
  -C /home/sjytt jiaoda \
  -C /home/sjytt/livo2_ws/src/FAST-LIVO2 config launch \
  -C /home/sjytt/unilidar_sdk2/unitree_lidar_ros/src/unitree_lidar_ros config launch package.xml \
  -C /etc/systemd/system jiaoda-calib.service jiaoda-campub.service jiaoda-chassis.service \
     jiaoda-console.service jiaoda-control.service jiaoda-fastlivo.service jiaoda-grid.service \
     jiaoda-lidar.service jiaoda-mission.service jiaoda-nav.service jiaoda-netwatch.service \
     jiaoda-netwatch.timer jiaoda-posebridge.service jiaoda-powerlog.service jiaoda-restamp.service \
     jiaoda-safe-stop.service 2>/dev/null || true
ls -l /tmp/sync.tar.gz
'@
($remote -replace "`r", "") | ssh -o BatchMode=yes -o ConnectTimeout=8 "sjytt@$Host" 'bash -s'
if ($LASTEXITCODE -ne 0) { throw "远程打包失败，检查 SSH 连通性" }

Write-Host "== 2. 拷回本地 ==" -ForegroundColor Cyan
$tmp = Join-Path $env:TEMP "jetson-sync.tar.gz"
scp -o BatchMode=yes "sjytt@${Host}:/tmp/sync.tar.gz" $tmp
if ($LASTEXITCODE -ne 0) { throw "scp 失败" }

Write-Host "== 3. 解压到 $Out ==" -ForegroundColor Cyan
$staging = Join-Path $env:TEMP "jetson-sync"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null
tar -xzf $tmp -C $staging

# jiaoda 覆盖
Copy-Item (Join-Path $staging "jiaoda\*") (Join-Path $root "$Out\jiaoda") -Recurse -Force
# 配置覆盖
if (Test-Path (Join-Path $staging "config")) {
    Copy-Item (Join-Path $staging "config\*") (Join-Path $root "$Out\FAST-LIVO2\config") -Recurse -Force
}
if (Test-Path (Join-Path $staging "launch")) {
    Copy-Item (Join-Path $staging "launch\*") (Join-Path $root "$Out\FAST-LIVO2\launch") -Recurse -Force
}
# systemd 单元
Get-ChildItem $staging -Filter "jiaoda-*.service" | Copy-Item -Destination (Join-Path $root "$Out\systemd") -Force
Get-ChildItem $staging -Filter "jiaoda-*.timer"   | Copy-Item -Destination (Join-Path $root "$Out\systemd") -Force

Remove-Item $tmp -Force
Write-Host "== 4. 结果 ==" -ForegroundColor Cyan
$files = Get-ChildItem (Join-Path $root $Out) -Recurse -File
Write-Host ("   {0} 个文件, {1:N1} MB" -f $files.Count, (($files | Measure-Object Length -Sum).Sum / 1MB))
Write-Host "   下一步: git add -A; git commit -m '同步实机最新代码'; git push" -ForegroundColor Yellow
