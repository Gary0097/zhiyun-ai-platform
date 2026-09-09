using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Threading;
using System.Windows.Forms;

// Native, offline installation UI. No embedded browser or network assets.
class WizardForm : Form, IExtractProgress
{
    readonly string payload;
    readonly Panel content = new Panel();
    readonly Label heading = new Label(), subtitle = new Label(), status = new Label(), detail = new Label();
    readonly TextBox location = new TextBox();
    readonly ProgressBar progress = new ProgressBar();
    readonly Button primary = new Button(), secondary = new Button();
    readonly CheckBox desktop = new CheckBox();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    string target, log;
    bool running, succeeded, createDesktop;
    int page;
    static readonly Color Ink = Color.FromArgb(24, 38, 43), Muted = Color.FromArgb(99, 115, 120);
    static readonly Color Accent = Color.FromArgb(0, 112, 119);

    public WizardForm(string path)
    {
        payload = path;
        Text = "智造云 AIOS · 安装";
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96, 96);
        Font = new Font("Microsoft YaHei UI", 10);
        ClientSize = new Size(880, 560);
        MinimumSize = new Size(896, 599);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.White;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

        var brand = new BrandPanel { Dock = DockStyle.Left, Width = 292 };
        Controls.Add(brand);
        content.Bounds = new Rectangle(332, 42, 508, 480);
        Controls.Add(content);
        heading.Bounds = new Rectangle(0, 16, 500, 48);
        heading.Font = new Font(Font.FontFamily, 23, FontStyle.Bold);
        heading.ForeColor = Ink;
        subtitle.Bounds = new Rectangle(0, 76, 495, 68);
        subtitle.ForeColor = Muted;
        location.Bounds = new Rectangle(0, 205, 400, 34);
        location.Text = ExistingInstall() ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "ZhizaoyunAIOS");
        desktop.Bounds = new Rectangle(0, 262, 400, 30);
        desktop.Text = "在桌面创建快捷方式";
        desktop.Checked = true;
        status.Bounds = new Rectangle(0, 163, 496, 38);
        status.ForeColor = Ink;
        detail.Bounds = new Rectangle(0, 310, 495, 86);
        detail.ForeColor = Muted;
        detail.AutoEllipsis = true;
        progress.Bounds = new Rectangle(0, 240, 496, 8);
        progress.Style = ProgressBarStyle.Continuous;
        primary.Bounds = new Rectangle(318, 425, 178, 46);
        StyleButton(primary, true);
        secondary.Bounds = new Rectangle(0, 425, 145, 46);
        StyleButton(secondary, false);
        foreach (Control c in new Control[] { heading, subtitle, location, desktop, status, detail, progress, primary, secondary }) content.Controls.Add(c);
        primary.Click += delegate {
            if (page == 0) BeginInstall();
            else if (succeeded) { Launch(); Close(); }
            else ShowReady();
        };
        secondary.Click += delegate {
            if (page == 0) {
                using (var dialog = new FolderBrowserDialog { SelectedPath = location.Text, Description = "选择智造云 AIOS 安装位置" })
                    if (dialog.ShowDialog(this) == DialogResult.OK) location.Text = dialog.SelectedPath;
            } else if (!running) Close();
        };
        timer.Interval = 700;
        timer.Tick += delegate { if (log != null) { var line = Installer.LastLogLine(log); if (line.Length > 0) detail.Text = line; } };
        ShowReady();
    }

    static string ExistingInstall()
    {
        using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\ZhizaoyunAIOS"))
            return key == null ? null : key.GetValue("InstallLocation") as string;
    }
    static void StyleButton(Button b, bool filled)
    {
        b.FlatStyle = FlatStyle.Flat;
        b.FlatAppearance.BorderSize = filled ? 0 : 1;
        b.FlatAppearance.BorderColor = Color.FromArgb(219, 226, 226);
        b.BackColor = filled ? Accent : Color.White;
        b.ForeColor = filled ? Color.White : Ink;
        b.Cursor = Cursors.Hand;
    }
    void ShowReady()
    {
        page = 0;
        heading.Text = "让工作，多一种可能。";
        subtitle.Text = "安装智造云 AIOS " + Installer.AppVersion + "\n为你的电脑开启智能体工作空间。";
        status.Text = "安装位置";
        detail.Text = "安装后可使用单机工作空间，或启动 Hub 团队服务。\n升级保留现有工作区和账号数据。";
        detail.ForeColor = Muted;
        location.Visible = desktop.Visible = true;
        progress.Visible = false;
        primary.Text = "安装智造云 AIOS";
        primary.Enabled = secondary.Enabled = true;
        secondary.Text = "更改位置";
        AcceptButton = primary;
    }
    void BeginInstall()
    {
        try {
            target = Path.GetFullPath(location.Text.Trim());
            if (target.TrimEnd(Path.DirectorySeparatorChar).Equals(Path.GetPathRoot(target).TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
                throw new Exception("请选择独立的应用文件夹，不能直接安装到磁盘根目录。");
            if (new DriveInfo(Path.GetPathRoot(target)).AvailableFreeSpace < 3L * 1024 * 1024 * 1024)
                throw new Exception("安装至少需要 3 GB 可用空间，请更换位置。");
            Directory.CreateDirectory(target);
            string probe = Path.Combine(target, ".write-probe-" + Guid.NewGuid().ToString("N"));
            File.WriteAllText(probe, ""); File.Delete(probe);
        } catch (Exception ex) { MessageBox.Show(this, ex.Message, "无法使用这个位置", MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
        createDesktop = desktop.Checked;
        running = true; page = 1;
        heading.Text = "正在为你准备。";
        subtitle.Text = "安装将在此窗口内完成。\n完成后即可开启你的第一个工作空间。";
        location.Visible = desktop.Visible = false;
        progress.Visible = true;
        primary.Text = "安装中…"; primary.Enabled = secondary.Enabled = false;
        status.Text = "01 / 03    正在展开应用文件";
        detail.Text = "正在检查安装环境…";
        var worker = new Thread(Install); worker.IsBackground = true; worker.Start();
    }
    void Ui(Action action) { if (!IsDisposed && IsHandleCreated) BeginInvoke(action); }
    void Install()
    {
        try {
            Installer.StopLiveService(target);
            if (Installer.PortOccupied()) throw new Exception("端口 8088 正被其他应用使用，请关闭占用程序后重试。");
            Installer.ExtractTo(payload, target, this);
            log = Path.Combine(target, "install-wizard.log");
            Ui(delegate { status.Text = "02 / 03    正在配置运行环境"; progress.Style = ProgressBarStyle.Marquee; timer.Start(); });
            int code = Installer.RunRuntimeSetup(target, log);
            Ui(delegate { timer.Stop(); });
            if (code != 0) throw new Exception("运行环境配置失败（" + code + "）。可以重试，详细原因已保存在安装日志。");
            if (!Installer.HasNodeAvailable(target)) throw new Exception("Node.js 20+ 运行环境不可用，请重新下载完整安装包。");
            Ui(delegate { status.Text = "03 / 03    正在完成应用设置"; });
            if (!Installer.RegisterIntegration(target, createDesktop)) throw new Exception("系统快捷方式或卸载项创建失败，请检查目录权限后重试。");
            succeeded = true;
            Ui(delegate { Complete(null); });
        } catch (Exception ex) { Ui(delegate { Complete(ex.Message); }); }
    }
    void Complete(string error)
    {
        running = false; page = 2; timer.Stop();
        progress.Style = ProgressBarStyle.Continuous; progress.Value = error == null ? 100 : 0;
        heading.Text = error == null ? "准备就绪。" : "还差一步。";
        subtitle.Text = error == null ? "智造云 AIOS 已安装到你的电脑。\n现在，开始你的第一段对话。" : "安装未完成。处理下面的问题后，可以直接重试。";
        status.Text = error == null ? "安装完成  ·  " + Installer.AppVersion : "安装需要你的关注";
        detail.Text = error == null ? "首次打开时创建自己的登录账号。\n你的工作区保存在安装目录中。" : error + (log == null ? "" : "\n日志：" + log);
        detail.ForeColor = error == null ? Muted : Color.FromArgb(160, 55, 42);
        primary.Text = error == null ? "打开智造云 AIOS" : "重试安装";
        secondary.Text = error == null ? "稍后打开" : "关闭";
        primary.Enabled = secondary.Enabled = true;
    }
    void Launch()
    {
        string exe = Path.Combine(target, "智造云AI-OS.exe");
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(File.Exists(exe) ? exe : Path.Combine(target, "智造云AI-OS启动.cmd")) { WorkingDirectory = target, UseShellExecute = true }); }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "启动失败"); }
    }
    public void SetProgress(int done, int total, string file)
    {
        Ui(delegate { progress.Value = Math.Min(100, (int)(100L * done / Math.Max(1, total))); detail.Text = "正在展开应用文件  ·  " + progress.Value + "%"; });
    }
    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        // Never leave a background installer modifying files after closing the window.
        if (running) { e.Cancel = true; return; }
        timer.Dispose();
        base.OnFormClosing(e);
    }
}

class BrandPanel : Panel
{
    public BrandPanel() { DoubleBuffered = true; }
    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics; g.SmoothingMode = SmoothingMode.AntiAlias;
        float s = Width / 292f;
        g.ScaleTransform(s, s);
        using (var bg = new LinearGradientBrush(new Rectangle(0, 0, 292, 600), Color.FromArgb(232, 243, 239), Color.FromArgb(210, 232, 228), 70)) g.FillRectangle(bg, 0, 0, 292, Height / s);
        using (var ink = new SolidBrush(Color.FromArgb(21, 66, 64)))
        using (var title = new Font("Microsoft YaHei UI", 18, FontStyle.Bold))
        using (var small = new Font("Microsoft YaHei UI", 9)) {
            g.DrawString("智造云 AIOS", title, ink, 28, 36);
            g.DrawString("你的智能体工作空间", small, ink, 30, 78);
            using (var pen = new Pen(Color.FromArgb(95, 155, 147), 1.5f)) {
                for (int i = 0; i < 5; i++) { g.TranslateTransform(146, 270); g.RotateTransform(36); g.DrawEllipse(pen, -77, -105, 154, 210); g.TranslateTransform(-146, -270); }
            }
            g.ResetTransform(); g.ScaleTransform(s, s);
            g.DrawString("思考 · 连接 · 行动", new Font("Microsoft YaHei UI", 13, FontStyle.Bold), ink, 30, 430);
            g.DrawString("灵泽万川\n为每一个想法，提供行动的空间。", small, ink, 30, 478);
        }
    }
}
