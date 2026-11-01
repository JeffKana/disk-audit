# T2-09 sub-item 3 (VM capacity deviation retest, after T2-08 merge) - baseline rebuild tool.
# Rebuilds the "Explorer size-on-disk" registry equivalent inside a headless guest,
# producing baseline_vm.json for tools/check_size_deviation.py --baseline.
#
# Method (v2, pure-handle): per-file CreateFileW(FILE_READ_ATTRIBUTES) +
# GetFileInformationByHandleEx(FileStandardInfo) -> AllocationSize sum. This is the same
# external ground-truth anchor as DR-004 grad 2' ("mixed vs pure-handle <0.1%") and the
# scanner's handle-based segments; v1 (GetCompressedFileSizeW) was discarded after host
# calibration showed GCFW returns LOGICAL size for regular files (5000B -> 5000, not 8192),
# undercounting small-file-heavy trees (host Programs: 1.74% vs Explorer-registered).
#
# Alignment notes (mirrors docs/evidence/T2-09 record; keep this file ASCII for PS 5.1 / GBK hosts):
#   1. Files only; directory MFT/index overhead excluded (scanner counts files only).
#   2. Reparse points (junction dirs and reparse files) skipped (scanner X-1 reparse semantics).
#   3. Hidden/system files included (Explorer folder properties semantics).
#   4. Enumeration/query failures counted as n_fail and skipped (X-1 skip+count+continue).
#
# Compatible with Windows PowerShell 5.1 (guests only ship 5.1). Console output is ASCII.
param(
    [string]$OutJson = 'C:\stage\t209c\baseline_vm.json',
    [string]$TargetsRaw = ''
)
if ($TargetsRaw) { $targets = $TargetsRaw -split '\|' } else {
    $targets = @(
        'C:\Users\qa\AppData\Roaming\Tencent',
        'C:\ProgramData\Package Cache',
        'C:\Users\qa\AppData\Local\Programs',
        'C:\Users\qa\AppData\Local\kingsoft',
        'C:\Users\qa\AppData\Local\Google'
    )
}

if (-not ('NativeAlloc' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct FILE_STANDARD_INFO {
    public long AllocationSize;
    public long EndOfFile;
    public uint NumberOfLinks;
    public byte DeletePending;
    public byte Directory;
}

public static class NativeAlloc {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr CreateFileW(
        string lpFileName,
        uint dwDesiredAccess,
        uint dwShareMode,
        IntPtr lpSecurityAttributes,
        uint dwCreationDisposition,
        uint dwFlagsAndAttributes,
        IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetFileInformationByHandleEx(
        IntPtr hFile,
        int FileStandardInfoClass,
        out FILE_STANDARD_INFO lpInfo,
        uint dwBufferSize);

    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr hObject);

    public const uint FILE_READ_ATTRIBUTES = 0x80;
    public const uint FILE_SHARE_ALL = 0x7;
    public const uint OPEN_EXISTING = 3;
    public const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
    public const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
    public const int FileStandardInfo = 1;
    public static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);
}
"@
}

function Get-AllocBytes([string]$Path) {
    $h = [NativeAlloc]::CreateFileW(
        $Path,
        [NativeAlloc]::FILE_READ_ATTRIBUTES,
        [NativeAlloc]::FILE_SHARE_ALL,
        [IntPtr]::Zero,
        [NativeAlloc]::OPEN_EXISTING,
        ([NativeAlloc]::FILE_FLAG_BACKUP_SEMANTICS -bor [NativeAlloc]::FILE_FLAG_OPEN_REPARSE_POINT),
        [IntPtr]::Zero)
    if ($h -eq [NativeAlloc]::INVALID_HANDLE_VALUE) { return -1 }
    try {
        $info = New-Object FILE_STANDARD_INFO
        $buf = [uint32][System.Runtime.InteropServices.Marshal]::SizeOf([type][FILE_STANDARD_INFO])
        if (-not [NativeAlloc]::GetFileInformationByHandleEx($h, [NativeAlloc]::FileStandardInfo, [ref]$info, $buf)) { return -1 }
        return [int64]$info.AllocationSize
    } finally {
        [void][NativeAlloc]::CloseHandle($h)
    }
}

$records = @()
foreach ($t in $targets) {
    if (-not (Test-Path -LiteralPath $t -PathType Container)) {
        Write-Output ("MISSING`t" + $t)
        continue
    }
    $stack = New-Object System.Collections.Stack
    $stack.Push((Get-Item -LiteralPath $t -Force))
    $sumFiles = [int64]0; $nFiles = [int64]0; $nDirs = [int64]0; $nFail = [int64]0; $nReparse = [int64]0
    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        $nDirs++
        $children = $null
        try {
            $children = Get-ChildItem -LiteralPath $dir.FullName -Force -ErrorAction Stop
        } catch { $nFail++; continue }
        foreach ($c in $children) {
            if (($c.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { $nReparse++; continue }
            if ($c.PSIsContainer) { $stack.Push($c) }
            else {
                $a = Get-AllocBytes $c.FullName
                if ($a -lt 0) { $nFail++ } else { $sumFiles += $a; $nFiles++ }
            }
        }
    }
    Write-Output ("OK`t" + $t + "`tfiles=" + $nFiles + "`tdirs=" + $nDirs + "`tfail=" + $nFail + "`treparse=" + $nReparse + "`talloc=" + $sumFiles)
    $records += [ordered]@{
        path = $t
        explorer_allocated_bytes = $sumFiles
        method = 'pure_handle_allocation_size_sum_rebuilt_in_vm'
        n_files = $nFiles; n_dirs = $nDirs; n_fail = $nFail; n_reparse = $nReparse
    }
}

$json = ConvertTo-Json -InputObject @($records) -Depth 3
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($OutJson, $json, $utf8NoBom)
Write-Output ("WROTE`t" + $OutJson + "`trecords=" + $records.Count)
