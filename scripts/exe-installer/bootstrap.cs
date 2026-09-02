// 灵泽万川智造云 AI-OS — 自解压安装引导器
// 编译为 stub.exe 后，把离线 zip 以 8 字节标记拼接在其尾部：
//   copy /b stub.exe + payload.bin（payload.bin = 标记 + zip）
// 运行时：选择安装目录 → 解压全部文件 → 自动执行 install-usb.cmd。
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
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
            Run();
        }
        catch (Exception ex)
        {
            MessageBox.Show("安装失败：" + ex.Message, "灵泽万川智造云 AI-OS",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    static void Run()
    {
        string payload = FindPayload();
        if (payload == null)
        {
            MessageBox.Show("安装包数据缺失（未找到内置载荷）。请重新下载完整安装程序。",
                "灵泽万川智造云 AI-OS", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        try
        {
            // 支持 --dir <目录> 静默安装：无任何 UI，不创建窗口或消息循环，
            // 进度写入 <目标目录>\install-log.txt，退出码 0=成功 2=失败。
            string[] args = Environment.GetCommandLineArgs();
            int dirIdx = Array.IndexOf(args, "--dir");
            if (dirIdx >= 0 && dirIdx + 1 < args.Length)
            {
                SilentInstall(payload, args[dirIdx + 1]);
                return;
            }

            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择安装目录（需要约 2.5 GB 可用空间，路径建议不含空格）";
                dialog.ShowNewFolderButton = true;
                if (dialog.ShowDialog() != DialogResult.OK) return;
                Install(payload, dialog.SelectedPath);
            }
        }
        finally
        {
            // 无论成功、失败还是用户取消，都清掉临时载荷，避免多 GB 副本滞留 %TEMP%
            try { if (payload != null) File.Delete(payload); } catch { }
        }
    }


    // ── 系统集成：对齐官方 QwenPaw Desktop 的安装体验 ──────────────
    // 桌面/开始菜单快捷方式 + 控制面板卸载项 + 启动器与卸载脚本。
    static void RegisterIntegration(string targetDir)
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

            string[] uninstallerLines = {
                "@echo off", "chcp 65001 >nul",
                "cd /d \"%~dp0\"",
                "for /f \"tokens=5\" %%p in ('netstat -ano ^| findstr :8088 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1",
                "reg delete HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZhizaoyunAIOS /f >nul 2>&1",
                "del \"%USERPROFILE%\\Desktop\\智造云 AI-OS.lnk\" >nul 2>&1",
                "del \"%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\智造云 AI-OS.lnk\" >nul 2>&1",
                "echo 已移除快捷方式与卸载项；如需彻底删除请手动删除整个安装目录。",
                "pause" };
            string uninstaller = Path.Combine(targetDir, "卸载智造云AI-OS.cmd");
            File.WriteAllText(uninstaller, string.Join("\r\n", uninstallerLines) + "\r\n",
                new System.Text.UTF8Encoding(false));

            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            object shellObj = Activator.CreateInstance(shellType);
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string startMenuDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "Microsoft", "Windows", "Start Menu", "Programs");
            foreach (string dir in new[] { desktopDir, startMenuDir })
            {
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
                shellType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, sc, null);
            }

            using (var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Uninstall\ZhizaoyunAIOS"))
            {
                key.SetValue("DisplayName", "灵泽万川智造云 AI-OS");
                key.SetValue("DisplayVersion", AppVersion);
                key.SetValue("InstallLocation", targetDir);
                key.SetValue("DisplayIcon", hasLauncher ? launcherExe : launcher);
                key.SetValue("UninstallString", "\"" + uninstaller + "\"");
                key.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine("integration failed: " + ex.Message);
        }
    }

    static string AppVersion { get { return VersionInfo.AppVersion; } }

    // 目标根目录前缀（兼容盘符根：GetFullPath("H:\") 已以分隔符结尾，不重复追加）
    static string TargetRoot(string targetDir)
    {
        string root = Path.GetFullPath(targetDir);
        if (!root.EndsWith(Path.DirectorySeparatorChar.ToString()) &&
            !root.EndsWith(Path.AltDirectorySeparatorChar.ToString()))
            root += Path.DirectorySeparatorChar;
        return root;
    }

    static void SilentInstall(string payloadPath, string targetDir)
    {
        string logPath = Path.Combine(targetDir, "install-log.txt");
        Directory.CreateDirectory(targetDir);
        using (var log = new StreamWriter(
            new FileStream(Path.Combine(targetDir, "install-log.txt"), FileMode.Create, FileAccess.Write, FileShare.Read)))
        {
            try
            {
                int files = ExtractTo(payloadPath, targetDir, null, null);
                RegisterIntegration(targetDir);
                log.WriteLine("done: " + files + " files");
                log.Flush();
                var installer = Path.Combine(targetDir, "install-usb.cmd");
                if (File.Exists(installer))
                {
                    log.WriteLine("launching install-usb.cmd");
                    log.Flush();
                    var child = Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + installer + "\"")
                    {
                        WorkingDirectory = targetDir,
                        UseShellExecute = false
                    });
                    // install-usb 正常路径是“装运行时→起服务（前台常驻）”，子进程
                    // 不会退出。这里只收割早期失败：若在窗口期内以非零码退出则视为
                    // 安装失败；超时仍在运行说明服务已起，按成功处理。
                    if (child.WaitForExit(180000))
                    {
                        log.WriteLine("install-usb.cmd exited: " + child.ExitCode);
                        log.Flush();
                        Environment.ExitCode = child.ExitCode == 0 ? 0 : 2;
                    }
                    else
                    {
                        log.WriteLine("install-usb.cmd still running (service online)");
                        Environment.ExitCode = 0;
                    }
                }
                else
                {
                    log.WriteLine("warning: install-usb.cmd not found");
                    Environment.ExitCode = 0;
                }
            }
            catch (Exception ex)
            {
                log.WriteLine("failed: " + ex.Message);
                Environment.ExitCode = 2;
            }
        }
    }

    static void Install(string payloadPath, string targetDir)
    {
        Directory.CreateDirectory(targetDir);
        var progress = new ProgressForm();
        var thread = new Thread(() =>
        {
            try
            {
                ExtractTo(payloadPath, targetDir, progress, null);
                RegisterIntegration(targetDir);
                progress.Done();
                var installer = Path.Combine(targetDir, "install-usb.cmd");
                if (File.Exists(installer))
                {
                    Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + installer + "\"")
                    {
                        WorkingDirectory = targetDir,
                        UseShellExecute = false
                    });
                }
                else
                {
                    MessageBox.Show("解压完成，但未找到 install-usb.cmd，请手动运行 start-ai-os.cmd。",
                        "灵泽万川智造云 AI-OS");
                }
            }
            catch (Exception ex)
            {
                progress.Fail("解压失败：" + ex.Message);
            }
        });
        thread.Start();
        Application.Run(progress);
        if (thread.IsAlive) thread.Join(2000);
    }

    // 公共解压：防路径穿越（兼容盘符根），progress 可为 null（静默模式）
    static int ExtractTo(string payloadPath, string targetDir, ProgressForm progress, object unused)
    {
        string root = TargetRoot(targetDir);
        int files = 0;
        using (var archive = ZipFile.OpenRead(payloadPath))
        {
            int total = archive.Entries.Count, done = 0;
            foreach (var entry in archive.Entries)
            {
                string rel = entry.FullName;
                if (rel.StartsWith("./")) rel = rel.Substring(2);
                if (string.IsNullOrEmpty(rel)) continue;
                string dest = Path.Combine(targetDir, rel.Replace('/', Path.DirectorySeparatorChar));
                string fullDest = Path.GetFullPath(dest);
                if (!fullDest.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    continue;
                if (string.IsNullOrEmpty(entry.Name)) // 目录项
                {
                    Directory.CreateDirectory(fullDest);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(fullDest));
                entry.ExtractToFile(fullDest, true);
                done++; files++;
                if (progress != null && done % 200 == 0)
                    progress.SetProgress(done, total, entry.Name);
            }
        }
        return files;
    }

    // 在自身文件中流式定位标记并把载荷复制到临时 zip：
    // 不整包读入内存（数百 MB 的 EXE 全量加载会造成严重内存峰值/分配失败）。
    static string FindPayload()
    {
        string self = Assembly.GetExecutingAssembly().Location;
        int markerLen = PayloadMarker.Length;
        string tempZip = Path.Combine(Path.GetTempPath(), "zhizaoyun-aos-payload-" +
            DateTime.Now.ToString("yyyyMMddHHmmss") + ".zip");

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

// 简易进度窗口
class ProgressForm : Form
{
    readonly Label _label;
    readonly ProgressBar _bar;
    bool _closed;

    public ProgressForm()
    {
        Text = "灵泽万川智造云 AI-OS 安装";
        Width = 520; Height = 150;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        _label = new Label { Left = 16, Top = 18, Width = 470, Text = "正在准备…" };
        _bar = new ProgressBar { Left = 16, Top = 50, Width = 470, Height = 22 };
        Controls.Add(_label);
        Controls.Add(_bar);
        FormClosing += (s, e) => { if (!_closed) e.Cancel = true; };
    }

    public void SetProgress(int done, int total, string current)
    {
        if (InvokeRequired) { BeginInvoke((Action)(() => SetProgress(done, total, current))); return; }
        _bar.Maximum = Math.Max(1, total);
        _bar.Value = Math.Min(done, total);
        _label.Text = "正在解压 " + done + " / " + total + " … " + (current ?? "");
    }

    public void Done()
    {
        if (InvokeRequired) { BeginInvoke((Action)(Done)); return; }
        _closed = true;
        _label.Text = "解压完成，正在启动安装…";
        Close();
    }

    public void Fail(string message)
    {
        if (InvokeRequired) { BeginInvoke((Action)(() => Fail(message))); return; }
        _closed = true;
        MessageBox.Show(message, "灵泽万川智造云 AI-OS", MessageBoxButtons.OK, MessageBoxIcon.Error);
        Close();
    }
}
