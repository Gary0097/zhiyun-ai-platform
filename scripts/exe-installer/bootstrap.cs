// 灵泽万川智造云 AI-OS — 自解压安装向导
// 编译为 stub.exe 后，把离线 zip 以 8 字节标记拼接在其尾部：
//   copy /b stub.exe + payload.bin（payload.bin = 标记 + zip）
// 运行流程：向导（欢迎 → 选择目录 → 解压/装运行时分阶段进度 → 完成）。
// 支持 --dir <目录> 静默安装：无 UI，进度写 <目标目录>\install-log.txt，
// 退出码 0=成功 2=失败（与 CI/引导脚本约定，勿改语义）。
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Net;
using System.Threading;
using System.Windows.Forms;

class Installer
{
    // 与 make-exe-installer.mjs 约定的载荷标记（stub 之后紧跟此标记 + zip）
    static readonly byte[] PayloadMarker = System.Text.Encoding.ASCII.GetBytes("ZYLZWC1!");

    [STAThread]
    static void Main()
    {
        try
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Run();
        }
        catch (Exception ex)
        {
            Environment.ExitCode = 2;
            MessageBox.Show("安装失败：" + ex.Message, "灵泽万川智造云 AI-OS",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    static void Run()
    {
        string payload = FindPayload();
        if (payload == null)
        {
            Environment.ExitCode = 2;
            MessageBox.Show("安装包数据缺失（未找到内置载荷）。请重新下载完整安装程序。",
                "灵泽万川智造云 AI-OS", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        try
        {
            // 静默安装分支：无任何 UI，不创建窗口或消息循环
            string[] args = Environment.GetCommandLineArgs();
            int dirIdx = Array.IndexOf(args, "--dir");
            if (dirIdx >= 0 && dirIdx + 1 < args.Length)
            {
                SilentInstall(payload, args[dirIdx + 1]);
                return;
            }

            Application.Run(new WizardForm(payload));
        }
        finally
        {
            // 无论成功、失败还是用户取消，都清掉临时载荷，避免多 GB 副本滞留 %TEMP%
            try { if (payload != null) File.Delete(payload); } catch { }
        }
    }


    // ── 系统集成：对齐官方 QwenPaw Desktop 的安装体验 ──────────────
    // 桌面/开始菜单快捷方式 + 控制面板卸载项 + 启动器与卸载脚本。
    internal static bool RegisterIntegration(string targetDir, bool createDesktop = true)
    {
        try
        {
            // 桌面启动器 exe（离线包内嵌；缺失时快捷方式回退到 .cmd 入口）
            string launcherExe = Path.Combine(targetDir, "智造云AI-OS.exe");
            bool hasLauncher = File.Exists(launcherExe);

            // 批处理内容用“行数组运行时拼接”，避免源码转义拼写出错
            string[] launcherLines = {
                "@echo off", "chcp 65001 >nul",
                "title Lingze Wanchuan Zhizaoyun AI-OS",
                "cd /d \"%~dp0\"",
                "start \"\" http://127.0.0.1:8088",
                "call start-ai-os.cmd" };
            string launcher = Path.Combine(targetDir, "智造云AI-OS启动.cmd");
            File.WriteAllText(launcher, string.Join("\r\n", launcherLines) + "\r\n",
                new System.Text.UTF8Encoding(false));

            string uninstaller = Path.Combine(targetDir, "Uninstall.exe");
            if (!File.Exists(uninstaller)) throw new IOException("图形卸载程序缺失，请重新下载完整安装包。");
            RecordInstalledFiles(targetDir, new[] { "智造云AI-OS启动.cmd" });

            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            object shellObj = Activator.CreateInstance(shellType);
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string startMenuDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "Microsoft", "Windows", "Start Menu", "Programs");
            // 品牌图标随包分发（branding/app.ico）；快捷方式与卸载面板均显式指向它，
            // 避免目标 .cmd 显示成默认命令行图标
            string iconSource = Path.Combine(targetDir, "branding", "app.ico");
            string iconRef = File.Exists(iconSource) ? iconSource + ",0" : launcher;
            foreach (string dir in new[] { desktopDir, startMenuDir })
            {
                if (dir == desktopDir && !createDesktop) continue;
                object sc = shellType.InvokeMember("CreateShortcut",
                    System.Reflection.BindingFlags.InvokeMethod, null, shellObj,
                    new object[] { Path.Combine(dir, "智造云 AI-OS.lnk") });
                // IDispatch 后期绑定：属性用属性名 + SetProperty 直接设置
                shellType.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, sc,
                    new object[] { hasLauncher ? launcherExe : launcher });
                shellType.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, sc,
                    new object[] { targetDir });
                shellType.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, sc,
                    new object[] { "灵泽万川智造云 AI-OS" });
                shellType.InvokeMember("IconLocation", System.Reflection.BindingFlags.SetProperty, null, sc,
                    new object[] { iconRef });
                shellType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, sc, null);
            }

            using (var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Uninstall\ZhizaoyunAIOS"))
            {
                key.SetValue("DisplayName", "灵泽万川智造云 AI-OS");
                key.SetValue("DisplayVersion", AppVersion);
                key.SetValue("InstallLocation", targetDir);
                key.SetValue("DisplayIcon", hasLauncher ? launcherExe : iconRef);
                key.SetValue("UninstallString", "\"" + uninstaller + "\"");
                key.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine("integration failed: " + ex.Message);
            return false;
        }
        return true;
    }

    // Node 可用性：离线包可能未内嵌 node.exe（打包仅告警），此时要求系统 PATH
    // 存在 node（与 install-usb.cmd 的检查一致），否则服务无法启动
    internal static bool HasNodeAvailable(string targetDir)
    {
        // 与 start-ai-os.cmd/install-usb.cmd 一致：要求 Node 20+，只查存在
        // 会把 Node 16 误判为可用
        string node = File.Exists(Path.Combine(targetDir, "extras", "node", "node.exe"))
            ? Path.Combine(targetDir, "extras", "node", "node.exe")
            : "node";
        try
        {
            var psi = new ProcessStartInfo(node,
                "-e \"process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (var p = Process.Start(psi))
            {
                if (!p.WaitForExit(30000)) { p.Kill(); return false; }
                return p.ExitCode == 0;
            }
        }
        catch { return false; }
    }

    internal static string AppVersion { get { return VersionInfo.AppVersion; } }

    // 目标根目录前缀（兼容盘符根：GetFullPath("H:\") 已以分隔符结尾，不重复追加）
    static string TargetRoot(string targetDir)
    {
        string root = Path.GetFullPath(targetDir);
        if (!root.EndsWith(Path.DirectorySeparatorChar.ToString()) &&
            !root.EndsWith(Path.AltDirectorySeparatorChar.ToString()))
            root += Path.DirectorySeparatorChar;
        return root;
    }

    // 覆盖升级：旧实例不停止会锁住 venv 文件导致解压失败，且 launcher 会
    // 因 8088 已就绪而直接打开旧实例（新插件永不加载）。安装前强制停止。
    internal static void StopLiveService(string installRoot)
    {
        try
        {
            // 8088 监听进程必须经命令行归属校验（命令行包含本安装目录）后才
            // 终止——通用关键词会把其他 QwenPaw 安装也误认成“自己的”。
            // 目录经 env 传入，避开 cmd/正则的双重转义
            var ps = "$root=[regex]::Escape($env:Z_INSTALL_ROOT); " +
                "Get-NetTCPConnection -LocalPort 8088,8000 -State Listen -ErrorAction SilentlyContinue | " +
                "ForEach-Object { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.OwningProcess); " +
                "if ($p -and $p.CommandLine -match $root) { & taskkill.exe /T /F /PID $p.ProcessId | Out-Null } }";
            var psi = new ProcessStartInfo("powershell.exe", "-NoProfile -Command \"" + ps + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            psi.EnvironmentVariables["Z_INSTALL_ROOT"] = TargetRoot(installRoot);
            using (var p = Process.Start(psi)) p.WaitForExit(30000);
            // 驻留托盘启动器按映像名精确结束，避免升级解压时 exe 被锁
            foreach (var proc in Process.GetProcessesByName("智造云AI-OS"))
            {
                try { if (proc.MainModule.FileName.StartsWith(TargetRoot(installRoot), StringComparison.OrdinalIgnoreCase)) proc.Kill(); }
                catch { }
            }
        }
        catch { /* 无运行实例或权限不足时继续安装 */ }
    }

    // 终止整棵进程树：taskkill /T 递归结束 cmd 包装之下的 PowerShell/Node/QwenPaw
    // 子进程；Process.Kill() 只杀直接包装进程，孤儿进程会继续改写安装目录。
    static void KillProcessTree(int rootPid)
    {
        var psi = new ProcessStartInfo("cmd.exe", "/c taskkill /T /F /PID " + rootPid + " >nul 2>&1")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        using (var p = Process.Start(psi)) p.WaitForExit(30000);
    }

    // 端口预检：8088 仍被监听（StopLiveService 后仍在，即非本产品进程）返回 true
    internal static bool PortOccupied()
    {
        try
        {
            var psi = new ProcessStartInfo("powershell.exe",
                "-NoProfile -Command \"if (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) { exit 1 }\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (var p = Process.Start(psi))
            {
                p.WaitForExit(30000);
                return p.ExitCode == 1;
            }
        }
        catch { return false; }
    }

    // 静默安装就绪探活：/api/version 200 即服务可用
    static bool ServiceReady()
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8088/api/version");
            req.Timeout = 2000;
            req.ReadWriteTimeout = 2000;
            using (var resp = req.GetResponse()) { return true; }
        }
        catch { return false; }
    }

    static bool WaitReady(int timeoutSeconds)
    {
        for (int i = 0; i < timeoutSeconds; i++)
        {
            if (ServiceReady()) return true;
            Thread.Sleep(1000);
        }
        return false;
    }

    static void SilentInstall(string payloadPath, string targetDir)
    {
        targetDir = Path.GetFullPath(targetDir);
        Directory.CreateDirectory(targetDir);
        using (var log = new StreamWriter(new FileStream(Path.Combine(targetDir, "install-log.txt"), FileMode.Create, FileAccess.Write, FileShare.Read)))
        {
            log.AutoFlush = true;
            try {
                StopLiveService(targetDir);
                if (PortOccupied()) throw new IOException("端口 8088 正被其他应用使用。");
                log.WriteLine("Extracting application files");
                ExtractTo(payloadPath, targetDir, null);
                int code = RunRuntimeSetup(targetDir, Path.Combine(targetDir, "install-runtime.log"));
                if (code != 0) throw new IOException("运行环境配置失败：" + code);
                if (!HasNodeAvailable(targetDir)) throw new IOException("Node.js 20+ 不可用。");
                if (!RegisterIntegration(targetDir)) throw new IOException("系统集成失败。");
                string launcher = Path.Combine(targetDir, "智造云AI-OS.exe");
                if (!File.Exists(launcher)) throw new IOException("桌面启动器缺失。");
                log.WriteLine("Starting application; waiting for service readiness");
                var child = Process.Start(new ProcessStartInfo(launcher) { WorkingDirectory = targetDir, UseShellExecute = false });
                bool ready = WaitReady(600);
                if (!ready) { try { KillProcessTree(child.Id); } catch { } throw new IOException("服务未在 600 秒内就绪。"); }
                log.WriteLine("service ready");
                Environment.ExitCode = 0;
            } catch (Exception ex) { log.WriteLine("failed: " + ex.Message); Environment.ExitCode = 2; }
        }
    }

    // 公共解压：防路径穿越（兼容盘符根），progress 可为 null（静默模式）
    internal static int ExtractTo(string payloadPath, string targetDir, IExtractProgress progress)
    {
        string root = TargetRoot(targetDir);
        int files = 0;
        var installed = new System.Collections.Generic.List<string>();
        using (var archive = ZipFile.OpenRead(payloadPath))
        {
            // Validate the complete archive before changing any installed file.
            foreach (var entry in archive.Entries)
                ValidateDestination(targetDir, entry.FullName);
            int total = archive.Entries.Count, done = 0;
            foreach (var entry in archive.Entries)
            {
                string rel = entry.FullName;
                if (rel.StartsWith("./")) rel = rel.Substring(2);
                if (string.IsNullOrEmpty(rel)) continue;
                string dest = Path.Combine(targetDir, rel.Replace('/', Path.DirectorySeparatorChar));
                string fullDest = Path.GetFullPath(dest);
                if (!fullDest.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("安装包包含越界路径：" + rel);
                // Existing user data and administrator Hub settings are never package-owned.
                string normalized = fullDest.Substring(root.Length).Replace('\\', '/');
                if (File.Exists(fullDest) && (normalized.StartsWith("apps/zhizaoyunAIOS/workspace/", StringComparison.OrdinalIgnoreCase) ||
                    normalized.Equals("hub.yaml", StringComparison.OrdinalIgnoreCase))) continue;
                if (string.IsNullOrEmpty(entry.Name)) // 目录项
                {
                    Directory.CreateDirectory(fullDest);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(fullDest));
                entry.ExtractToFile(fullDest, true);
                if (!Uninstaller.Protected(normalized)) installed.Add(normalized);
                done++; files++;
                if (progress != null && done % 200 == 0)
                    progress.SetProgress(done, total, entry.Name);
            }
        }
        RecordInstalledFiles(targetDir, installed);
        return files;
    }

    internal static void RecordInstalledFiles(string targetDir, System.Collections.Generic.IEnumerable<string> paths)
    {
        string manifest = Uninstaller.CheckedPath(targetDir, Uninstaller.Manifest);
        var entries = new System.Collections.Generic.HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (File.Exists(manifest)) foreach (string line in File.ReadAllLines(manifest)) entries.Add(line);
        foreach (string path in paths) if (!Uninstaller.Protected(path)) entries.Add(path);
        // This only records names; it does not touch the listed files. The
        // uninstaller checks every filesystem path again before any deletion.
        foreach (string path in entries) Uninstaller.NormalizedPath(targetDir, path);
        File.WriteAllLines(manifest, entries);
    }

    static void ValidateDestination(string targetDir, string entryName)
    {
        string root = TargetRoot(targetDir);
        string rel = entryName.Replace('/', Path.DirectorySeparatorChar);
        if (rel.StartsWith("." + Path.DirectorySeparatorChar)) rel = rel.Substring(2);
        if (string.IsNullOrEmpty(rel)) return;
        if (Path.IsPathRooted(rel) || rel.Contains(":"))
            throw new InvalidDataException("安装包包含非法路径：" + entryName);
        string dest = Path.GetFullPath(Path.Combine(targetDir, rel));
        if (!dest.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("安装包包含越界路径：" + entryName);
        // A junction within the installation must not redirect writes elsewhere.
        for (string current = dest; !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
        {
            if ((File.Exists(current) || Directory.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("安装路径包含链接，请选择普通目录：" + current);
        }
    }

    // 隐藏窗口运行运行时安装（setup-ai-os.ps1 -Offline），输出重定向到日志文件
    // （cmd 自身重定向，进程不依赖向导的管道）。返回退出码。
    internal static int RunRuntimeSetup(string targetDir, string logPath)
    {
        var psi = new ProcessStartInfo("powershell.exe",
            "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(targetDir, "setup-ai-os.ps1") +
            "\" -Offline -CacheDir \"" + Path.Combine(targetDir, "apps", "zhizaoyunAIOS", "runtime", "cache") + "\"")
        {
            WorkingDirectory = targetDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        // 便携 Node 优先（与 install-usb.cmd 一致）
        string portableNode = Path.Combine(targetDir, "extras", "node");
        if (Directory.Exists(portableNode))
            psi.EnvironmentVariables["Path"] = portableNode + ";" + Environment.GetEnvironmentVariable("Path");
        using (var log = new StreamWriter(logPath, false, new System.Text.UTF8Encoding(false)))
        using (var p = new Process { StartInfo = psi })
        {
            object sync = new object();
            log.AutoFlush = true;
            DataReceivedEventHandler receive = delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) lock(sync) log.WriteLine(e.Data); };
            p.OutputDataReceived += receive; p.ErrorDataReceived += receive;
            p.Start(); p.BeginOutputReadLine(); p.BeginErrorReadLine();
            if (!p.WaitForExit(15 * 60 * 1000)) { KillProcessTree(p.Id); p.WaitForExit(); return 2; }
            p.WaitForExit(); // Drain asynchronous redirected output before closing the log.
            if (p.ExitCode == 0) RecordRuntimeFiles(targetDir);
            return p.ExitCode;
        }
    }

    static void RecordRuntimeFiles(string targetDir)
    {
        string prefix = TargetRoot(targetDir);
        var paths = new System.Collections.Generic.List<string>();
        var pending = new System.Collections.Generic.Stack<string>();
        foreach (string relative in new[] { "apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv", "apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv" })
        {
            string folder = Uninstaller.CheckedPath(targetDir, relative);
            if (Directory.Exists(folder)) pending.Push(folder);
        }
        while (pending.Count > 0) {
            string folder = pending.Pop();
            Uninstaller.CheckedPath(targetDir, folder.Substring(prefix.Length));
            foreach (string path in Directory.GetFileSystemEntries(folder)) {
                string relative = path.Substring(prefix.Length);
                var attributes = File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("运行环境包含链接：" + path);
                if ((attributes & FileAttributes.Directory) != 0) pending.Push(path); else paths.Add(relative);
            }
        }
        RecordInstalledFiles(targetDir, paths);
    }

    // 取日志文件最后一个非空行，供进度页实时回显
    internal static string LastLogLine(string logPath)
    {
        try
        {
            using (var s = new FileStream(logPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var r = new StreamReader(s))
            {
                string last = "", line;
                while ((line = r.ReadLine()) != null)
                    if (line.Trim().Length > 0) last = line;
                return last;
            }
        }
        catch { return ""; }
    }

    // 在自身文件中流式定位标记并把载荷复制到临时 zip：
    // 不整包读入内存（数百 MB 的 EXE 全量加载会造成严重内存峰值/分配失败）。
    static string FindPayload()
    {
        string self = Assembly.GetExecutingAssembly().Location;
        int markerLen = PayloadMarker.Length;
        string tempZip = Path.Combine(Path.GetTempPath(), "zhizaoyun-aos-payload-" +
            Guid.NewGuid().ToString("N") + ".zip");

        const int chunk = 1 << 20; // 1 MB
        byte[] buffer = new byte[chunk + markerLen];
        long searchPos = 64; // 跳过 .NET 头
        long payloadOffset = -1;
        using (var input = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            while (payloadOffset < 0)
            {
                input.Position = searchPos;
                int read = input.Read(buffer, 0, buffer.Length);
                if (read < markerLen) break;
                int limit = read - markerLen;
                for (int i = 0; i <= limit; i++)
                {
                    bool match = true;
                    for (int j = 0; j < markerLen; j++)
                    {
                        if (buffer[i + j] != PayloadMarker[j]) { match = false; break; }
                    }
                    if (match) { payloadOffset = searchPos + i + markerLen; break; }
                }
                if (payloadOffset < 0) searchPos += Math.Max(1, read - markerLen + 1);
            }
            if (payloadOffset < 0) return null;

            input.Position = payloadOffset;
            using (var output = new FileStream(tempZip, FileMode.Create, FileAccess.Write))
            {
                byte[] copy = new byte[chunk];
                int n;
                while ((n = input.Read(copy, 0, copy.Length)) > 0)
                    output.Write(copy, 0, n);
            }
        }
        return tempZip;
    }
}

// 解压进度回调（向导实现；静默模式传 null）
interface IExtractProgress
{
    void SetProgress(int done, int total, string current);
}
