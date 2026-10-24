# -*- coding: utf-8 -*-
"""POC-2: 最小可打包验证程序
目的：验证 PyInstaller --onedir 产物在【无 Python 环境】的机器上，能否完成
      ① 读注册表卸载项  ② 调 PowerShell 取 Appx 包  ③ 枚举目录  ④ 加载 Tkinter
用法：
  poc2_min.exe --selftest        无界面自检，输出 JSON
  poc2_min.exe                   带目录选择窗口（GUI 冒烟）
"""
import os, sys, json, time, subprocess, argparse

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
CREATE_NO_WINDOW = 0x08000000


def count_uninstall_entries():
    import winreg
    paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    total, named = 0, 0
    for hive, sub in paths:
        try:
            with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ) as k:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    total += 1
                    try:
                        with winreg.OpenKey(k, name, 0, winreg.KEY_READ) as sk:
                            dn, _ = winreg.QueryValueEx(sk, "DisplayName")
                            if dn:
                                named += 1
                    except OSError:
                        pass
        except OSError:
            pass
    return {"total_keys": total, "with_displayname": named}


def count_appx_packages():
    ps = ("$ErrorActionPreference='SilentlyContinue';"
          "(Get-AppxPackage | Measure-Object).Count")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=120,
                       creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
    out = (r.stdout or "").strip().splitlines()
    return {"count": int(out[-1]) if out and out[-1].isdigit() else None,
            "stderr": (r.stderr or "").strip()[:200]}


def walk_small(root, limit=200000):
    files = dirs = size = denied = reparse = 0
    stack = [root]
    while stack and files + dirs < limit:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        denied += 1
                        continue
                    if st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                        reparse += 1
                        continue
                    if st.st_mode & 0o040000:
                        dirs += 1
                        stack.append(e.path)
                    else:
                        files += 1
                        size += st.st_size
        except (PermissionError, OSError):
            denied += 1
    return {"files": files, "dirs": dirs, "size_mb": round(size / 1024**2, 1),
            "denied": denied, "reparse": reparse}


def selftest():
    t0 = time.perf_counter()
    res = {"frozen": getattr(sys, "frozen", False), "exe": sys.executable,
           "python": sys.version.split()[0], "cwd": os.getcwd()}
    try:
        import tkinter
        res["tkinter"] = "ok " + str(tkinter.TkVersion)
    except Exception as e:
        res["tkinter"] = "FAIL: %r" % (e,)
    try:
        res["registry"] = count_uninstall_entries()
    except Exception as e:
        res["registry"] = "FAIL: %r" % (e,)
    try:
        res["appx"] = count_appx_packages()
    except Exception as e:
        res["appx"] = "FAIL: %r" % (e,)
    target = os.path.expanduser("~\\AppData\\Local")
    try:
        res["walk"] = walk_small(target)
        res["walk"]["root"] = target
    except Exception as e:
        res["walk"] = "FAIL: %r" % (e,)
    res["elapsed_sec"] = round(time.perf_counter() - t0, 2)
    return res


def gui_smoke():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.title("POC-2 GUI 冒烟")
    root.geometry("520x150")
    lbl = tk.Label(root, text="点下面按钮选择目录（验证 Tkinter 在打包产物中可用）")
    lbl.pack(pady=16)
    picked = {"v": None}

    def pick():
        d = filedialog.askdirectory()
        picked["v"] = d
        lbl.config(text="已选择: " + (d or "（取消）"))

    tk.Button(root, text="选择目录", command=pick).pack()
    root.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        out = selftest()
        txt = json.dumps(out, ensure_ascii=False, indent=2)
        print(txt)
        try:
            with open(os.path.join(os.path.dirname(sys.executable), "selftest_result.json"), "w",
                      encoding="utf-8") as f:
                f.write(txt)
        except Exception:
            pass
    else:
        gui_smoke()
