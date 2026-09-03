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
    internal static bool RegisterIntegration(string targetDir)
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
            // 品牌图标随包分发（branding/app.ico）；快捷方式与卸载面板均显式指向它，
            // 避免目标 .cmd 显示成默认命令行图标
            string iconSource = Path.Combine(targetDir, "branding", "app.ico");
            string iconRef = File.Exists(iconSource) ? iconSource + ",0" : launcher;
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
        if (File.Exists(Path.Combine(targetDir, "extras", "node", "node.exe"))) return true;
        try
        {
            var psi = new ProcessStartInfo("cmd.exe", "/c where node >nul 2>&1")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (var p = Process.Start(psi))
            {
                p.WaitForExit(15000);
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
    internal static void StopLiveService()
    {
        try
        {
            // 8088 监听进程必须经命令行归属校验（zhizaoyunAIOS|qwenpaw，
            // 与 start.mjs stopStaleInstance 同规则）后才终止，避免误杀
            // 恰好占用该端口的无关应用
            var ps = "Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue | " +
                "ForEach-Object { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.OwningProcess); " +
                "if ($p -and $p.CommandLine -match 'zhizaoyunAIOS|qwenpaw') { Stop-Process -Id $p.ProcessId -Force } }";
            var psi = new ProcessStartInfo("powershell.exe", "-NoProfile -Command \"" + ps + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (var p = Process.Start(psi)) p.WaitForExit(30000);
            // 驻留托盘启动器按映像名精确结束，避免升级解压时 exe 被锁
            try { foreach (var proc in Process.GetProcessesByName("智造云AI-OS")) proc.Kill(); } catch { }
        }
        catch { /* 无运行实例或权限不足时继续安装 */ }
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
        string logPath = Path.Combine(targetDir, "install-log.txt");
        Directory.CreateDirectory(targetDir);
        using (var log = new StreamWriter(
            new FileStream(Path.Combine(targetDir, "install-log.txt"), FileMode.Create, FileAccess.Write, FileShare.Read)))
        {
            try
            {
                StopLiveService();
                int files = ExtractTo(payloadPath, targetDir, null);
                log.WriteLine("integration: " + (RegisterIntegration(targetDir) ? "ok" : "failed"));
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
                    // 无论哪条路径，静默安装的成功契约都是“服务就绪”，
                    // 统一以 /api/version 探活结果为准。
                    bool success;
                    if (child.WaitForExit(180000))
                    {
                        log.WriteLine("install-usb.cmd exited: " + child.ExitCode);
                        log.Flush();
                        if (child.ExitCode != 0)
                        {
                            log.WriteLine("failed: install-usb.cmd exit code " + child.ExitCode);
                            Environment.ExitCode = 2;
                            return;
                        }
                        success = WaitReady(240);
                    }
                    else
                    {
                        log.WriteLine("install-usb.cmd still running");
                        success = WaitReady(240);
                    }
                    log.WriteLine(success ? "service ready" : "service not ready within timeout");
                    log.Flush();
                    Environment.ExitCode = success ? 0 : 2;
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

    // 公共解压：防路径穿越（兼容盘符根），progress 可为 null（静默模式）
    internal static int ExtractTo(string payloadPath, string targetDir, IExtractProgress progress)
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

    // 隐藏窗口运行运行时安装（setup-ai-os.ps1 -Offline），输出重定向到日志文件
    // （cmd 自身重定向，进程不依赖向导的管道）。返回退出码。
    internal static int RunRuntimeSetup(string targetDir, string logPath)
    {
        var psi = new ProcessStartInfo("cmd.exe",
            "/c powershell -NoProfile -ExecutionPolicy Bypass -File setup-ai-os.ps1 -Offline -CacheDir \"apps\\zhizaoyunAIOS\\runtime\\cache\" > \"" + logPath + "\" 2>&1")
        {
            WorkingDirectory = targetDir,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        // 便携 Node 优先（与 install-usb.cmd 一致）
        string portableNode = Path.Combine(targetDir, "extras", "node");
        if (Directory.Exists(portableNode))
            psi.EnvironmentVariables["Path"] = portableNode + ";" + Environment.GetEnvironmentVariable("Path");
        using (var p = Process.Start(psi))
        {
            p.WaitForExit();
            return p.ExitCode;
        }
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

// 解压进度回调（向导实现；静默模式传 null）
interface IExtractProgress
{
    void SetProgress(int done, int total, string current);
}

// 四页向导：欢迎 → 目录 → 进度 → 完成/失败
class WizardForm : Form, IExtractProgress
{
    readonly string _payload;
    Panel _welcome, _dir, _progress, _done;
    TextBox _dirBox;
    Label _stageLabel, _detailLabel, _errorLabel;
    ProgressBar _bar;
    Button _installBtn, _launchBtn;
    readonly System.Windows.Forms.Timer _tailTimer;
    string _targetDir, _setupLog;
    bool _installStarted, _finished;

    public WizardForm(string payload)
    {
        _payload = payload;
        Text = "灵泽万川智造云 AI-OS 安装向导";
        Width = 640; Height = 420;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false; MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        try { Icon = System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

        _welcome = Page(WelcomeContent());
        _dir = Page(DirContent());
        _progress = Page(ProgressContent());
        _done = Page(DoneContent());
        Controls.Add(_welcome);
        ShowWelcome();

        // 运行时安装阶段每 600ms 回显日志尾部
        _tailTimer = new System.Windows.Forms.Timer();
        _tailTimer.Interval = 600;
        _tailTimer.Tick += delegate
        {
            if (_setupLog != null)
            {
                string line = Installer.LastLogLine(_setupLog);
                if (line.Length > 0) _detailLabel.Text = line;
            }
        };
    }

    Panel Page(Control content)
    {
        var p = new Panel { Dock = DockStyle.Fill, Visible = false };
        p.Controls.Add(content);
        return p;
    }

    // ── 第 1 页：欢迎 ──────────────────────────────────────────
    Control WelcomeContent()
    {
        var box = new Panel { Dock = DockStyle.Fill };
        box.Controls.Add(new Label
        {
            Text = "欢迎使用 灵泽万川智造云 AI-OS",
            Left = 40, Top = 50, Width = 540,
            Font = new System.Drawing.Font("Microsoft YaHei UI", 16, System.Drawing.FontStyle.Bold),
        });
        box.Controls.Add(new Label
        {
            Text = "版本 " + Installer.AppVersion + "   ·   QwenPaw 2.1.0 运行时",
            Left = 40, Top = 95, Width = 540, ForeColor = System.Drawing.Color.Gray,
        });
        box.Controls.Add(new Label
        {
            Text = "本向导将完成以下步骤：\n" +
                   "  1. 解压程序文件（约 2.5 GB）\n" +
                   "  2. 安装内嵌的 Python 运行时与锁定应用（离线，无需联网）\n" +
                   "  3. 创建桌面快捷方式并启动\n\n" +
                   "要求：Windows 10/11 x64，目标磁盘剩余空间 ≥ 3 GB。",
            Left = 40, Top = 140, Width = 540, Height = 150,
        });
        var next = new Button { Text = "下一步 >", Left = 500, Top = 320, Width = 90 };
        next.Click += delegate { ShowDir(); };
        box.Controls.Add(next);
        return box;
    }

    // ── 第 2 页：选择目录 ──────────────────────────────────────
    Control DirContent()
    {
        var box = new Panel { Dock = DockStyle.Fill };
        box.Controls.Add(new Label
        {
            Text = "选择安装目录",
            Left = 40, Top = 50, Width = 540,
            Font = new System.Drawing.Font("Microsoft YaHei UI", 14, System.Drawing.FontStyle.Bold),
        });
        box.Controls.Add(new Label { Text = "安装到：", Left = 40, Top = 110, Width = 70 });
        _dirBox = new TextBox
        {
            Left = 115, Top = 106, Width = 380,
            Text = Path.Combine(Path.GetPathRoot(Environment.SystemDirectory), "zhizaoyunAIOS"),
        };
        box.Controls.Add(_dirBox);
        var browse = new Button { Text = "浏览…", Left = 505, Top = 104, Width = 75 };
        browse.Click += delegate
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择安装目录（建议路径不含空格）";
                dialog.ShowNewFolderButton = true;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                    _dirBox.Text = dialog.SelectedPath;
            }
        };
        box.Controls.Add(browse);
        var hint = new Label { Left = 40, Top = 150, Width = 540, Height = 120, ForeColor = System.Drawing.Color.Gray };
        hint.Text = "提示：\n" +
                    "· 目录不存在时会自动创建；建议使用不含空格与中文的路径。\n" +
                    "· 安装完成后可在控制面板“应用”中卸载。";
        box.Controls.Add(hint);
        _installBtn = new Button { Text = "开始安装", Left = 500, Top = 320, Width = 90 };
        _installBtn.Click += delegate { StartInstall(); };
        box.Controls.Add(_installBtn);
        return box;
    }

    // ── 第 3 页：进度 ──────────────────────────────────────────
    Control ProgressContent()
    {
        var box = new Panel { Dock = DockStyle.Fill };
        _stageLabel = new Label
        {
            Left = 40, Top = 60, Width = 540,
            Font = new System.Drawing.Font("Microsoft YaHei UI", 12, System.Drawing.FontStyle.Bold),
            Text = "正在准备…",
        };
        _bar = new ProgressBar { Left = 40, Top = 110, Width = 540, Height = 22 };
        _detailLabel = new Label { Left = 40, Top = 145, Width = 540, Height = 60, Text = "" };
        box.Controls.Add(_stageLabel);
        box.Controls.Add(_bar);
        box.Controls.Add(_detailLabel);
        return box;
    }

    // ── 第 4 页：完成 / 失败 ───────────────────────────────────
    Control DoneContent()
    {
        var box = new Panel { Dock = DockStyle.Fill };
        _errorLabel = new Label
        {
            Left = 40, Top = 60, Width = 540, Height = 180, Text = "",
            Font = new System.Drawing.Font("Microsoft YaHei UI", 11),
        };
        box.Controls.Add(_errorLabel);
        _launchBtn = new Button { Text = "立即启动", Left = 400, Top = 320, Width = 90, Visible = false };
        _launchBtn.Click += delegate { LaunchApp(); };
        box.Controls.Add(_launchBtn);
        var finish = new Button { Text = "完成", Left = 500, Top = 320, Width = 90 };
        finish.Click += delegate { Close(); };
        box.Controls.Add(finish);
        return box;
    }

    void ShowWelcome() { Swap(_welcome); }
    void ShowDir() { Swap(_dir); }

    void Swap(Panel page)
    {
        foreach (Control c in Controls)
            if (c is Panel) ((Panel)c).Visible = false;
        Controls.Add(page);
        page.Visible = true;
    }

    void StartInstall()
    {
        string dir = _dirBox.Text.Trim();
        if (dir.Length == 0)
        {
            MessageBox.Show(this, "请填写安装目录。", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        // 空间预检（要求 3GB）
        try
        {
            var drive = new DriveInfo(Path.GetPathRoot(Path.GetFullPath(dir)));
            if (!drive.IsReady || drive.AvailableFreeSpace < 3L * 1024 * 1024 * 1024)
            {
                MessageBox.Show(this, "目标磁盘可用空间不足 3 GB，请换一个目录。",
                    Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "目录不可用：" + ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        _targetDir = dir;
        _installStarted = true;
        Swap(_progress);
        _stageLabel.Text = "第 1 步 / 共 3 步：解压程序文件";
        _bar.Style = ProgressBarStyle.Continuous;

        var thread = new Thread(RunInstall);
        thread.IsBackground = true;
        thread.Start();
    }

    void RunInstall()
    {
        string fail = null;
        try
        {
            Installer.StopLiveService();
            Directory.CreateDirectory(_targetDir);
            int files = Installer.ExtractTo(_payload, _targetDir, this);
            SetStage("第 2 步 / 共 3 步：安装运行时与应用（离线，约 3-10 分钟）");

            _setupLog = Path.Combine(_targetDir, "install-wizard.log");
            RunOnUi(delegate { _bar.Style = ProgressBarStyle.Marquee; _tailTimer.Start(); });
            int code = Installer.RunRuntimeSetup(_targetDir, _setupLog);
            RunOnUi(delegate { _tailTimer.Stop(); });
            if (code != 0)
                throw new Exception("运行时安装失败（退出码 " + code + "），详见日志：\n" + _setupLog);

            SetStage("第 3 步 / 共 3 步：创建快捷方式");
            bool integrationOk = Installer.RegisterIntegration(_targetDir);

            // Node 可用性校验（extras 内嵌或系统 PATH），缺 Node 则服务无法启动，
            // 不得向用户报告安装成功
            if (!Installer.HasNodeAvailable(_targetDir))
                throw new Exception("未检测到 Node.js 运行环境（包内未内嵌且系统 PATH 中无 node）。" +
                    "本安装包需要 Node.js 20+，请安装后重新运行安装程序。\nhttps://nodejs.org/zh-cn");

            _finished = true;
            RunOnUi(delegate
            {
                _errorLabel.Text = "安装完成！\n\n" +
                    (integrationOk
                        ? "· 桌面与开始菜单已创建“智造云 AI-OS”快捷方式\n"
                        : "· 注意：快捷方式创建失败，请使用安装目录中的启动脚本\n") +
                    "· 双击即以独立应用窗口启动（自动拉起本地服务）\n" +
                    "· 默认管理员账号见安装目录 USB-INSTALL.md";
                _launchBtn.Visible = File.Exists(Path.Combine(_targetDir, "智造云AI-OS.exe")) ||
                                     File.Exists(Path.Combine(_targetDir, "智造云AI-OS启动.cmd"));
                Swap(_done);
            });
        }
        catch (Exception ex)
        {
            fail = ex.Message;
        }
        if (fail != null)
        {
            RunOnUi(delegate
            {
                _tailTimer.Stop();
                _errorLabel.Text = "安装失败：\n\n" + fail + "\n\n" +
                    (_setupLog != null ? "日志：" + _setupLog : "可重试安装程序。");
                _errorLabel.ForeColor = System.Drawing.Color.Firebrick;
                Swap(_done);
            });
        }
    }

    void LaunchApp()
    {
        string exe = Path.Combine(_targetDir, "智造云AI-OS.exe");
        if (File.Exists(exe)) Process.Start(exe);
        else Process.Start(Path.Combine(_targetDir, "智造云AI-OS启动.cmd"));
    }

    void SetStage(string text) { RunOnUi(delegate { _stageLabel.Text = text; }); }
    void RunOnUi(Action a)
    {
        if (InvokeRequired) { BeginInvoke(a); return; }
        a();
    }

    // IExtractProgress：解压进度（每 200 个文件回调一次）
    public void SetProgress(int done, int total, string current)
    {
        RunOnUi(delegate
        {
            _bar.Maximum = Math.Max(1, total);
            _bar.Value = Math.Min(done, total);
            _detailLabel.Text = "已解压 " + done + " / " + total + " 个文件";
        });
    }

    // 开始安装后不允许直接关窗（避免解压/装运行时中途被打断留下半成品）
    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (_installStarted && !_finished && e.CloseReason == CloseReason.UserClosing)
        {
            var r = MessageBox.Show(this,
                "安装仍在进行，中断可能留下不完整的安装。确定退出吗？",
                Text, MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (r == DialogResult.No) { e.Cancel = true; return; }
        }
        base.OnFormClosing(e);
    }
}
