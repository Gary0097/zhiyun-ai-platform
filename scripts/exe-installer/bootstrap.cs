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

        // 支持 --dir <目录> 静默安装（无界面，便于企业批量部署与自动化测试）
        string[] args = Environment.GetCommandLineArgs();
        int dirIdx = Array.IndexOf(args, "--dir");
        if (dirIdx >= 0 && dirIdx + 1 < args.Length)
        {
            Install(payload, args[dirIdx + 1]);
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

    static void Install(string payloadPath, string targetDir)
    {
        Directory.CreateDirectory(targetDir);
        var progress = new ProgressForm();
        var thread = new Thread(() =>
        {
            try
            {
                using (var archive = ZipFile.OpenRead(payloadPath))
                {
                    int total = archive.Entries.Count, done = 0;
                    foreach (var entry in archive.Entries)
                    {
                        string rel = entry.FullName;
                        if (rel.StartsWith("./")) rel = rel.Substring(2);
                        if (string.IsNullOrEmpty(rel)) continue;
                        string dest = Path.Combine(targetDir, rel.Replace('/', Path.DirectorySeparatorChar));
                        // 防路径穿越
                        string fullDest = Path.GetFullPath(dest);
                        if (!fullDest.StartsWith(Path.GetFullPath(targetDir) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                            continue;
                        if (string.IsNullOrEmpty(entry.Name)) // 目录项
                        {
                            Directory.CreateDirectory(fullDest);
                            continue;
                        }
                        Directory.CreateDirectory(Path.GetDirectoryName(fullDest));
                        entry.ExtractToFile(fullDest, true);
                        done++;
                        if (done % 200 == 0)
                            progress.SetProgress(done, total, entry.Name);
                    }
                }
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

    // 在自身文件中查找标记：返回提取出的临时 zip 路径
    static string FindPayload()
    {
        string self = Assembly.GetExecutingAssembly().Location;
        byte[] selfBytes = File.ReadAllBytes(self);
        int markerLen = PayloadMarker.Length;
        int idx = -1;
        // 从文件中段之后开始找（前段是 .NET 头，正常不含该标记）
        for (int i = 64; i <= selfBytes.Length - markerLen; i++)
        {
            bool match = true;
            for (int j = 0; j < markerLen; j++)
            {
                if (selfBytes[i + j] != PayloadMarker[j]) { match = false; break; }
            }
            if (match) { idx = i; break; }
        }
        if (idx < 0) return null;
        string tempZip = Path.Combine(Path.GetTempPath(), "zhizaoyun-aos-payload-" +
            DateTime.Now.ToString("yyyyMMddHHmmss") + ".zip");
        using (var output = new FileStream(tempZip, FileMode.Create, FileAccess.Write))
        {
            output.Write(selfBytes, idx + markerLen, selfBytes.Length - idx - markerLen);
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
