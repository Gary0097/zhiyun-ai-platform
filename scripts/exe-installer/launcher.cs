// 灵泽万川智造云 AI-OS — 桌面启动器
// 双击体验：隐藏窗口拉起 8088 服务 → 探活就绪 → 用 Edge/Chrome 应用模式
// （--app=，无地址栏的独立窗口）打开 QwenPaw Console 桌面模式，随后退出。
// 服务进程独立存活，启动器退出不影响；再次双击时若 8088 已就绪则直接开窗。
// --smoke：冒烟模式，起服务并探活，不打开浏览器窗口，退出码 0=就绪 3=超时。
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

class Launcher
{
    const string Url = "http://127.0.0.1:8088";
    const int ReadyTimeoutSeconds = 240;

    [STAThread]
    static int Main(string[] args)
    {
        bool smoke = Array.IndexOf(args, "--smoke") >= 0;
        string here = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string serviceEntry = Path.Combine(here, "start-ai-os.cmd");

        Splash splash = smoke ? null : new Splash();
        Thread worker = new Thread(() =>
        {
            string fail = null;
            try
            {
                if (!ServiceReady())
                {
                    if (!File.Exists(serviceEntry))
                        throw new FileNotFoundException("未找到 start-ai-os.cmd", serviceEntry);
                    SetStatus(splash, "正在启动服务（首次约 1-3 分钟）…");
                    StartService(serviceEntry, Path.Combine(here, "launcher-service.log"));
                }
                SetStatus(splash, "等待服务就绪…");
                if (!WaitReady(ReadyTimeoutSeconds))
                    throw new TimeoutException("服务在 " + ReadyTimeoutSeconds + " 秒内未就绪");
                if (!smoke) OpenAppWindow();
                if (splash != null) splash.DoneAndExit();
                Environment.ExitCode = 0;
            }
            catch (Exception ex)
            {
                fail = ex.Message;
            }
            if (fail != null)
            {
                if (splash != null) splash.FailAndExit("启动失败：" + fail + "\n\n日志：" + Path.Combine(here, "launcher-service.log"));
                else Console.Error.WriteLine("启动失败：" + fail);
                Environment.ExitCode = 3;
            }
        });
        worker.Start();
        if (splash != null) Application.Run(splash);
        else worker.Join();
        return Environment.ExitCode;
    }

    static void SetStatus(Splash splash, string text)
    {
        if (splash != null) splash.SetStatus(text);
    }

    static bool ServiceReady ()
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(Url + "/api/version");
            req.Timeout = 2000;
            req.ReadWriteTimeout = 2000;
            using (var resp = req.GetResponse()) { return true; }
        }
        catch { return false; }
    }

    // 隐藏窗口运行 start-ai-os.cmd，输出重定向由 cmd 自身完成（进程不依赖
    // 启动器的管道，启动器退出后服务仍正常写日志）。
    static void StartService (string entry, string logPath)
    {
        var psi = new ProcessStartInfo("cmd.exe",
            "/c \"\"" + entry + "\" > \"" + logPath + "\" 2>&1\"")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        Process.Start(psi);
    }

    static bool WaitReady (int timeoutSeconds)
    {
        for (int i = 0; i < timeoutSeconds; i++)
        {
            if (ServiceReady()) return true;
            Thread.Sleep(1000);
        }
        return false;
    }

    // Edge/Chrome 应用模式：独立无边框窗口打开 Console；找不到则回退默认浏览器。
    static void OpenAppWindow ()
    {
        string[] candidates = {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Microsoft", "Edge", "Application", "msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Microsoft", "Edge", "Application", "msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Google", "Chrome", "Application", "chrome.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Google", "Chrome", "Application", "chrome.exe"),
        };
        foreach (string exe in candidates)
        {
            if (File.Exists(exe))
            {
                Process.Start(new ProcessStartInfo(exe, "--app=" + Url));
                return;
            }
        }
        Process.Start(new ProcessStartInfo(Url)); // 默认浏览器兜底
    }
}

// 启动闪屏：品牌标题 + 滚动进度 + 状态行；成功/失败后自行退出消息循环
class Splash : Form
{
    readonly Label _status;

    public Splash()
    {
        Text = "灵泽万川智造云 AI-OS";
        Width = 420; Height = 200;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        try { Icon = System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        Controls.Add(new Label
        {
            Text = "灵泽万川智造云 AI-OS",
            Left = 24, Top = 20, Width = 360, Height = 30,
            Font = new System.Drawing.Font("Microsoft YaHei UI", 14, System.Drawing.FontStyle.Bold),
        });
        var bar = new ProgressBar
        {
            Left = 24, Top = 70, Width = 356, Height = 18,
            Style = ProgressBarStyle.Marquee,
        };
        _status = new Label { Left = 24, Top = 100, Width = 356, Text = "正在准备…" };
        Controls.Add(bar);
        Controls.Add(_status);
    }

    public void SetStatus(string text)
    {
        if (InvokeRequired) { BeginInvoke((Action)(() => SetStatus(text))); return; }
        _status.Text = text;
    }

    public void DoneAndExit()
    {
        if (InvokeRequired) { BeginInvoke((Action)(DoneAndExit)); return; }
        Close(); // FormClosing 未拦截，直接结束消息循环
    }

    public void FailAndExit(string message)
    {
        if (InvokeRequired) { BeginInvoke((Action)(() => FailAndExit(message))); return; }
        MessageBox.Show(message, "灵泽万川智造云 AI-OS", MessageBoxButtons.OK, MessageBoxIcon.Error);
        Close();
    }
}
