// App-local conversion entry for Hub members. No shell, global profile or PATH
// inheritance is needed; the full payload sits inside Hub's read-only venv root.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class OfficeWrapper
{
    static string Quote(string value)
    {
        var text = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            text.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            text.Append(c); slashes = 0;
        }
        text.Append('\\', slashes * 2); text.Append('"');
        return text.ToString();
    }

    static int Main(string[] args)
    {
        string profile = null;
        try {
            string scripts = AppDomain.CurrentDomain.BaseDirectory;
            string executable = Path.GetFullPath(Path.Combine(scripts, "..", "aios-libreoffice", "program", "soffice.com"));
            if (!File.Exists(executable)) throw new IOException("Bundled Hub LibreOffice is missing; run setup-hub.ps1.");
            string workspace = Environment.GetEnvironmentVariable("QWENPAW_WORKING_DIR");
            string temporary = string.IsNullOrEmpty(workspace) ? Path.GetTempPath() : Path.Combine(workspace, "tmp");
            profile = Path.Combine(Path.GetFullPath(temporary), "aios-office-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(profile);
            var command = new StringBuilder(Quote("-env:UserInstallation=" + new Uri(profile).AbsoluteUri));
            foreach (string arg in args) {
                // Every invocation owns a new profile, including concurrent jobs.
                if (arg.StartsWith("-env:UserInstallation=", StringComparison.OrdinalIgnoreCase)) continue;
                command.Append(' ').Append(Quote(arg));
            }
            using (var child = Process.Start(new ProcessStartInfo(executable, command.ToString()) { UseShellExecute = false, CreateNoWindow = true })) {
                child.WaitForExit(); return child.ExitCode;
            }
        } catch (Exception error) { Console.Error.WriteLine(error.Message); return 125; }
        finally {
            if (profile != null && Directory.Exists(profile)) {
                try { Directory.Delete(profile, true); } catch { /* private temporary profile only */ }
            }
        }
    }
}
