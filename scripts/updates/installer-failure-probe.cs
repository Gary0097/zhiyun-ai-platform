// Invokes actual installer methods against isolated test fixtures, never a live installation.
using System;
using System.IO;
class InstallerFailureProbe
{
    static int Main(string[] args)
    {
        try {
            if (args[0] == "extract") { Installer.ExtractTo(args[2], args[1], null); return 0; }
            if (args[0] == "runtime") return Installer.RunRuntimeSetup(args[1], Path.Combine(args[1], "fixture-setup.log"));
            return 99;
        } catch (IOException) { return 17; }
        catch (UnauthorizedAccessException) { return 17; }
    }
}
