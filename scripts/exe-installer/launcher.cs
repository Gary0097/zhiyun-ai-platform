// 灵泽万川智造云 AI-OS — 桌面启动器（托盘常驻）
// 双击体验：隐藏窗口拉起 8088 服务 → 探活就绪 → 用 Edge/Chrome 应用模式
// （--app=，无地址栏的独立窗口）打开 QwenPaw Console。之后进程驻留系统
// 托盘：图标实时反映服务状态（绿=运行中/橙=启动中/灰=已停止），右键菜单
// 可打开应用、启停服务、退出。解决"关掉网页后服务仍在后台且不可见"。
//
// 单实例：重复双击不会出现第二个托盘，而是探活后再开一个应用窗口。
// --smoke：冒烟模式，起服务并探活，不打开窗口、不驻留，退出码 0=就绪 3=超时。
// --selftest：验证状态图标生成后立即退出（供自动化检查）。
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

class Launcher
{
    const string Url = "http://127.0.0.1:8088";
    const int ReadyTimeoutSeconds = 240;
    static Mutex _single;

    [STAThread]
    static int Main(string[] args)
    {
        bool smoke = Array.IndexOf(args, "--smoke") >= 0;
        bool selftest = Array.IndexOf(args, "--selftest") >= 0;
        string here = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string serviceEntry = Path.Combine(here, "start-ai-os.cmd");

        if (selftest)
        {
            foreach (TrayIconFactory.State s in Enum.GetValues(typeof(TrayIconFactory.State)))
            {
                using (Icon icon = TrayIconFactory.Build(s))
                {
                    if (icon == null || icon.Width < 16) { Console.Error.WriteLine("icon build failed: " + s); return 4; }
                }
            }
            Console.WriteLine("selftest OK");
            return 0;
        }

        if (smoke)
        {
            return Smoke(serviceEntry);
        }

        // 单实例：已有托盘驻留时，探活等待后直接再开一个应用窗口并退出
        bool created;
        _single = new Mutex(true, "Local\\ZhizaoyunAIOS.Launcher.Single", out created);
        if (!created)
        {
            if (!ServiceReady()) WaitReady(ReadyTimeoutSeconds);
            if (ServiceReady()) OpenAppWindow();
            return 0;
        }

        var context = new TrayContext(here, serviceEntry);
        Application.Run(context);
        return context.ExitCode;
    }

    static int Smoke(string serviceEntry)
    {
        try
        {
            if (!ServiceReady())
            {
                if (!File.Exists(serviceEntry))
                {
                    Console.Error.WriteLine("not found: " + serviceEntry);
                    return 3;
                }
                StartService(serviceEntry, Path.Combine(Path.GetDirectoryName(serviceEntry), "launcher-service.log"));
            }
            if (!WaitReady(ReadyTimeoutSeconds))
            {
                Console.Error.WriteLine("service not ready within " + ReadyTimeoutSeconds + "s");
                return 3;
            }
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("启动失败：" + ex.Message);
            return 3;
        }
    }

    static bool ServiceReady()
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

    static bool WaitReady(int timeoutSeconds)
    {
        for (int i = 0; i < timeoutSeconds; i++)
        {
            if (ServiceReady()) return true;
            Thread.Sleep(1000);
        }
        return false;
    }

    // 隐藏窗口运行 start-ai-os.cmd；cmd 自身重定向输出，进程不依赖启动器管道
    internal static void StartService(string entry, string logPath)
    {
        var psi = new ProcessStartInfo("cmd.exe",
            "/c \"\"" + entry + "\" > \"" + logPath + "\" 2>&1\"")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        Process.Start(psi);
    }

    // 强制停止 8088 监听实例（与卸载脚本同一命令，已在安装/升级路径实测）
    internal static void StopLiveService()
    {
        try
        {
            var psi = new ProcessStartInfo("cmd.exe",
                "/c for /f \"tokens=5\" %p in ('netstat -ano ^| findstr :8088 ^| findstr LISTENING') do taskkill /PID %p /F >nul 2>&1")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (var p = Process.Start(psi)) p.WaitForExit(15000);
        }
        catch { }
    }

    // Edge/Chrome 应用模式：独立无边框窗口打开 Console；找不到则回退默认浏览器
    internal static void OpenAppWindow()
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

// 托盘上下文：状态轮询 + 右键菜单 + 状态角标图标
class TrayContext : ApplicationContext
{
    enum ServiceState { Starting, Running, Stopped }

    const int StartTimeoutSeconds = 250;

    readonly string _here, _serviceEntry;
    readonly NotifyIcon _tray;
    readonly System.Windows.Forms.Timer _poll;
    readonly MenuItem _startItem, _stopItem;
    ServiceState _state = ServiceState.Starting;
    int _startingTicks;
    bool _failShown;

    public int ExitCode { get; private set; }

    public TrayContext(string here, string serviceEntry)
    {
        _here = here;
        _serviceEntry = serviceEntry;

        var menu = new ContextMenu();
        menu.MenuItems.Add("打开智造云", delegate { Open(); });
        menu.MenuItems.Add("-");
        _startItem = new MenuItem("启动后台服务", delegate { Start(); });
        _stopItem = new MenuItem("停止后台服务", delegate { Stop(); });
        menu.MenuItems.Add(_startItem);
        menu.MenuItems.Add(_stopItem);
        menu.MenuItems.Add("-");
        menu.MenuItems.Add("退出（并停止后台服务）", delegate { ExitApp(); });

        _tray = new NotifyIcon
        {
            Icon = TrayIconFactory.Build(TrayIconFactory.State.Starting),
            Text = "智造云 AI-OS：启动中…",
            ContextMenu = menu,
            Visible = true,
        };
        _tray.DoubleClick += delegate { Open(); };

        _poll = new System.Windows.Forms.Timer { Interval = 2000 };
        _poll.Tick += delegate { Poll(); };
        _poll.Start();

        // 首次进入：服务没跑就自动拉起
        if (ServiceUp())
        {
            SetState(ServiceState.Running);
        }
        else
        {
            Start();
        }
    }

    bool ServiceUp()
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

    void Open()
    {
        if (_state == ServiceState.Stopped) Start();
        Launcher.OpenAppWindow();
    }

    void Start()
    {
        if (_state == ServiceState.Starting || _state == ServiceState.Running) return;
        if (!File.Exists(_serviceEntry))
        {
            MessageBox.Show("未找到 start-ai-os.cmd，请确认安装目录完整。", "智造云 AI-OS",
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        _startingTicks = Environment.TickCount;
        _failShown = false;
        Launcher.StartService(_serviceEntry, Path.Combine(_here, "launcher-service.log"));
        SetState(ServiceState.Starting);
    }

    void Stop()
    {
        if (_state == ServiceState.Stopped) return;
        Launcher.StopLiveService();
        SetState(ServiceState.Stopped);
    }

    void ExitApp()
    {
        Launcher.StopLiveService();
        _poll.Stop();
        _tray.Visible = false;
        _tray.Dispose();
        ExitCode = 0;
        Application.Exit();
    }

    // 轮询收敛：Starting 只在服务真正就绪时转为 Running（本地意图优先），
    // 超过就绪窗口仍未就绪则弹一次错误并落入 Stopped；其余状态跟随实际
    void Poll()
    {
        bool up = ServiceUp();
        if (_state == ServiceState.Starting)
        {
            if (up) { SetState(ServiceState.Running); return; }
            if (_startingTicks > 0 && Environment.TickCount - _startingTicks > StartTimeoutSeconds * 1000)
            {
                _startingTicks = 0;
                if (!_failShown)
                {
                    _failShown = true;
                    MessageBox.Show("服务在约 " + StartTimeoutSeconds + " 秒内未能就绪，请查看安装目录 launcher-service.log。",
                        "智造云 AI-OS", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                SetState(ServiceState.Stopped);
            }
            return;
        }
        ServiceState actual = up ? ServiceState.Running : ServiceState.Stopped;
        if (_state != actual) SetState(actual);
    }

    void SetState(ServiceState state)
    {
        _state = state;
        _startItem.Enabled = state == ServiceState.Stopped;
        _stopItem.Enabled = state != ServiceState.Stopped;
        try { _tray.Icon.Dispose(); } catch { }
        _tray.Icon = TrayIconFactory.Build(
            state == ServiceState.Running ? TrayIconFactory.State.Running
          : state == ServiceState.Starting ? TrayIconFactory.State.Starting
          : TrayIconFactory.State.Stopped);
        _tray.Text =
            state == ServiceState.Running ? "智造云 AI-OS：运行中（双击打开，右键可停止）" :
            state == ServiceState.Starting ? "智造云 AI-OS：启动中，请稍候…" :
            "智造云 AI-OS：已停止（右键启动）";
    }
}

// 状态图标工厂：以安装器品牌图标为底，右下角叠加状态角标
// （绿=运行中，橙=启动中，灰=已停止），无需额外图标资源
class TrayIconFactory
{
    public enum State { Running, Starting, Stopped }

    public static Icon Build(State state)
    {
        using (Icon baseIcon = ExtractBrandIcon())
        using (Bitmap bmp = baseIcon.ToBitmap())
        {
            using (var g = Graphics.FromImage(bmp))
            {
                Color color = state == State.Running ? Color.FromArgb(0, 176, 80)
                            : state == State.Starting ? Color.FromArgb(255, 140, 0)
                            : Color.FromArgb(160, 160, 160);
                int d = Math.Max(8, bmp.Width / 4);       // 角标直径
                int x = bmp.Width - d - 1, y = bmp.Height - d - 1;
                using (var brush = new SolidBrush(Color.White))
                    g.FillEllipse(brush, x - 1, y - 1, d + 2, d + 2); // 白描边
                using (var brush = new SolidBrush(color))
                    g.FillEllipse(brush, x, y, d, d);
            }
            IntPtr hIcon = bmp.GetHicon();
            using (Icon tmp = Icon.FromHandle(hIcon))
            {
                Icon cloned = (Icon)tmp.Clone();
                DestroyIcon(hIcon);
                return cloned;
            }
        }
    }

    static Icon ExtractBrandIcon()
    {
        try
        {
            Icon icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            if (icon != null) return icon;
        }
        catch { }
        return SystemIcons.Application;
    }

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto)]
    static extern bool DestroyIcon(IntPtr handle);
}
