using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

class Uninstaller
{
    internal const string Manifest = ".aios-installed-files";
    const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\ZhizaoyunAIOS";
    [STAThread]
    static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try {
            string root = Path.GetDirectoryName(Application.ExecutablePath);
            if (args.Length == 2 && args[0] == "--root") root = Path.GetFullPath(args[1]);
            else {
                // Run outside the installation so the installed executable can be removed.
                string copy = Path.Combine(Path.GetTempPath(), "aios-uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
                File.Copy(Application.ExecutablePath, copy);
                Process.Start(new ProcessStartInfo(copy, "--root \"" + root.TrimEnd('\\') + "\"") { UseShellExecute = true });
                return;
            }
            if (!File.Exists(Path.Combine(root, Manifest))) throw new IOException("找不到安装文件清单，无法安全卸载。请先修复安装。");
            Application.Run(new UninstallForm(root));
        } catch (Exception ex) { Environment.ExitCode = 2; MessageBox.Show(ex.Message, "无法卸载智造云 AIOS"); }
    }

    internal static bool Protected(string relative)
    {
        string p = relative.Replace('\\', '/');
        return p.Equals("hub.yaml", StringComparison.OrdinalIgnoreCase) ||
            p.StartsWith("apps/zhizaoyunAIOS/workspace/", StringComparison.OrdinalIgnoreCase) ||
            p.StartsWith("apps/zhizaoyunAIOS/workspace.secret/", StringComparison.OrdinalIgnoreCase);
    }

    internal static string CheckedPath(string root, string relative)
    {
        string prefix = Path.GetFullPath(root).TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
        if (Path.IsPathRooted(relative) || relative.Contains(":")) throw new IOException("安装清单包含非法路径。");
        string full = Path.GetFullPath(Path.Combine(prefix, relative));
        if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new IOException("安装清单路径越界。");
        for (string p = full; !string.IsNullOrEmpty(p); p = Path.GetDirectoryName(p))
            if ((File.Exists(p) || Directory.Exists(p)) && (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("安装路径包含链接，已停止卸载：" + p);
        return full;
    }

    internal static int RemoveFiles(string root)
    {
        string manifest = CheckedPath(root, Manifest);
        var files = new List<string>();
        string prefix = Path.GetFullPath(root).TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
        // Validate all paths before deleting any file. Unknown files remain untouched.
        foreach (string relative in File.ReadAllLines(manifest)) {
            if (string.IsNullOrWhiteSpace(relative)) continue;
            string full = CheckedPath(root, relative);
            if (!Protected(full.Substring(prefix.Length))) files.Add(full);
        }
        foreach (string file in files) if (File.Exists(file)) File.Delete(file);
        return files.Count;
    }

    internal static void RemoveIntegration(string root)
    {
        using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(RegistryPath)) {
            var registered = key == null ? null : key.GetValue("InstallLocation") as string;
            if (registered == null || !string.Equals(Path.GetFullPath(registered).TrimEnd('\\'), Path.GetFullPath(root).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) return;
        }
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        foreach (string dir in new[] { Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Microsoft", "Windows", "Start Menu", "Programs") }) {
            string link = Path.Combine(dir, "智造云 AI-OS.lnk");
            if (!File.Exists(link)) continue;
            object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { link });
            string target = (string)shellType.InvokeMember("TargetPath", BindingFlags.GetProperty, null, shortcut, null);
            if (target.StartsWith(Path.GetFullPath(root).TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase)) File.Delete(link);
        }
        Microsoft.Win32.Registry.CurrentUser.DeleteSubKeyTree(RegistryPath, false);
    }
}

class UninstallForm : Form
{
    readonly string root;
    readonly Label detail = new Label();
    readonly Button remove = new Button();
    bool busy, finished;
    public UninstallForm(string target)
    {
        root = target; Text = "智造云 AIOS · 卸载";
        AutoScaleMode = AutoScaleMode.Dpi; AutoScaleDimensions = new SizeF(96,96);
        ClientSize = new Size(600,330); FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.White; Font = new Font("Microsoft YaHei UI",10);
        Controls.Add(new Label { Text = "卸载应用，保留你的工作。", Font = new Font(Font.FontFamily,20,FontStyle.Bold), Bounds = new Rectangle(32,32,540,48), ForeColor = Color.FromArgb(24,38,43) });
        detail.Text = "将移除本安装的程序文件和快捷方式。\n工作区、账号与 Hub 配置会保留，方便以后继续使用。\n\n安装位置：" + root;
        detail.Bounds = new Rectangle(34,105,530,120); detail.AutoEllipsis = true; Controls.Add(detail);
        remove.Text = "卸载应用"; remove.Bounds = new Rectangle(410,260,150,42); remove.BackColor = Color.FromArgb(0,112,119); remove.ForeColor = Color.White; remove.FlatStyle = FlatStyle.Flat; Controls.Add(remove);
        remove.Click += delegate {
            if (finished) { Close(); return; }
            busy = true; remove.Enabled = false; detail.Text = "正在移除程序文件，请稍候…";
            new Thread(delegate() {
                string error = null;
                try { Installer.StopLiveService(root); Uninstaller.RemoveFiles(root); Uninstaller.RemoveIntegration(root); File.Delete(Path.Combine(root, Uninstaller.Manifest)); }
                catch (Exception ex) { error = ex.Message; }
                BeginInvoke(new Action(delegate { busy = false; finished = error == null; remove.Enabled = true; remove.Text = finished ? "完成" : "重试"; detail.Text = finished ? "应用已卸载。你的工作区和配置仍保存在：\n\n" + root : "卸载未完成，可处理问题后重试：\n" + error; }));
            }) { IsBackground = true }.Start();
        };
    }
    protected override void OnFormClosing(FormClosingEventArgs e) { if (busy) e.Cancel = true; base.OnFormClosing(e); }
}
