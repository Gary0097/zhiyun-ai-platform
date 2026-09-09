using System;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

class InstallerTests
{
    static void Check(bool value, string message) { if (!value) throw new Exception(message); Console.WriteLine("PASS " + message); }
    [STAThread]
    static int Main(string[] args)
    {
        var output = Path.GetFullPath(args[0]); Directory.CreateDirectory(output);
        string temp = Path.Combine(Path.GetTempPath(), "aios-installer-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try {
            var target = Path.Combine(temp, "中文 user's workspace"); Directory.CreateDirectory(target);
            File.WriteAllText(Path.Combine(target, "hub.yaml"), "custom-admin-settings");
            string data = Path.Combine(target, "apps", "zhizaoyunAIOS", "workspace"); Directory.CreateDirectory(data);
            File.WriteAllText(Path.Combine(data, "sentinel.txt"), "existing-user-data");
            string zip = Path.Combine(temp, "upgrade.zip");
            using (var a = ZipFile.Open(zip, ZipArchiveMode.Create)) {
                foreach (var name in new[] {"hub.yaml", "apps/zhizaoyunAIOS/workspace/sentinel.txt", "program.txt"})
                    using (var w = new StreamWriter(a.CreateEntry(name).Open())) w.Write("new-program");
            }
            Installer.ExtractTo(zip, target, null);
            Check(File.ReadAllText(Path.Combine(target, "hub.yaml")) == "custom-admin-settings", "upgrade preserves Hub settings");
            Check(File.ReadAllText(Path.Combine(data, "sentinel.txt")) == "existing-user-data", "upgrade preserves user data");
            Check(File.ReadAllText(Path.Combine(target, "program.txt")) == "new-program", "Unicode, spaces and apostrophe paths extract");
            string bad = Path.Combine(temp, "bad.zip");
            using (var a = ZipFile.Open(bad, ZipArchiveMode.Create)) using (var w = new StreamWriter(a.CreateEntry("../escape.txt").Open())) w.Write("bad");
            bool rejected = false; try { Installer.ExtractTo(bad, target, null); } catch (InvalidDataException) { rejected = true; }
            Check(rejected && !File.Exists(Path.Combine(temp, "escape.txt")), "zip traversal rejected");
            string lateBad = Path.Combine(temp, "late-bad.zip");
            using (var a = ZipFile.Open(lateBad, ZipArchiveMode.Create)) {
                foreach (var name in new[] {"program.txt", "../escape.txt"})
                    using (var w = new StreamWriter(a.CreateEntry(name).Open())) w.Write("must-not-write");
            }
            rejected = false; try { Installer.ExtractTo(lateBad, target, null); } catch (InvalidDataException) { rejected = true; }
            Check(rejected && File.ReadAllText(Path.Combine(target, "program.txt")) == "new-program", "invalid late entry rejected before overwriting installed files");
            string alias = Path.Combine(temp, "alias.zip");
            using (var a = ZipFile.Open(alias, ZipArchiveMode.Create))
                using (var w = new StreamWriter(a.CreateEntry("apps/zhizaoyunAIOS/other/../workspace/sentinel.txt").Open())) w.Write("must-not-write");
            Installer.ExtractTo(alias, target, null);
            Check(File.ReadAllText(Path.Combine(data, "sentinel.txt")) == "existing-user-data", "normalized archive aliases preserve workspace data");
            Check(Installer.HasNodeAvailable(target), "actual installed Node accepted");
            File.WriteAllText(Path.Combine(target, "setup-ai-os.ps1"), "param([switch]$Offline,[string]$CacheDir)\nWrite-Output 'setup stdout'\n[Console]::Error.WriteLine('setup stderr')\nexit 7\n");
            string log = Path.Combine(target, "setup-test.log");
            Check(Installer.RunRuntimeSetup(target, log) == 7, "runtime setup failure exit code preserved on special paths");
            Check(File.ReadAllText(log).Contains("setup stdout") && File.ReadAllText(log).Contains("setup stderr"), "both setup output streams captured");
            string generatedRuntime = Path.Combine(target, "apps", "zhizaoyunAIOS", "runtime", "zhizaoyunAIOS", "venv");
            Directory.CreateDirectory(generatedRuntime);
            File.WriteAllText(Path.Combine(generatedRuntime, "runtime-sentinel.txt"), "generated-runtime");
            File.WriteAllText(Path.Combine(target, "setup-ai-os.ps1"), "param([switch]$Offline,[string]$CacheDir)\nexit 0\n");
            Check(Installer.RunRuntimeSetup(target, log) == 0, "successful setup records generated runtime files");
            File.WriteAllText(Path.Combine(target, "user-note.txt"), "keep-me");
            string manifest = Path.Combine(target, Uninstaller.Manifest);
            string safeManifest = File.ReadAllText(manifest);
            File.AppendAllText(manifest, "../escape.txt\n");
            rejected = false; try { Uninstaller.RemoveFiles(target); } catch (IOException) { rejected = true; }
            Check(rejected && File.Exists(Path.Combine(target, "program.txt")), "uninstall rejects entire invalid manifest before deleting files");
            File.WriteAllText(manifest, safeManifest);
            Uninstaller.RemoveFiles(target);
            Check(!File.Exists(Path.Combine(target, "program.txt")), "uninstall removes installed program files");
            Check(!File.Exists(Path.Combine(generatedRuntime, "runtime-sentinel.txt")), "uninstall removes recorded generated runtime files");
            Check(File.ReadAllText(Path.Combine(target, "user-note.txt")) == "keep-me" && File.ReadAllText(Path.Combine(data, "sentinel.txt")) == "existing-user-data" && File.ReadAllText(Path.Combine(target, "hub.yaml")) == "custom-admin-settings", "uninstall preserves unknown files, workspace and Hub settings");
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            using (var f = new UninstallForm(target)) {
                f.Show(); Application.DoEvents();
                using (var bitmap = new Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bitmap, new Rectangle(0,0,f.Width,f.Height)); bitmap.Save(Path.Combine(output, "uninstaller-ready.png")); }
                f.Close();
            }
            using (var f = new WizardForm(zip)) {
                f.Show(); Application.DoEvents();
                using (var bitmap = new Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bitmap, new Rectangle(0,0,f.Width,f.Height)); bitmap.Save(Path.Combine(output, "installer-ready.png")); }
                typeof(WizardForm).GetMethod("Complete", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(f, new object[] { "测试：运行环境配置失败，请查看日志后重试。" });
                Application.DoEvents();
                using (var bitmap = new Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bitmap, new Rectangle(0,0,f.Width,f.Height)); bitmap.Save(Path.Combine(output, "installer-error.png")); }
                f.Close();
            }
            return 0;
        } finally { Directory.Delete(temp, true); }
    }
}
