// LibreOfficeKit runs inside the Hub member's existing AppContainer.
// Stable ABI: upstream include/LibreOfficeKit/LibreOfficeKit.h.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

class OfficeWrapper
{
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr LoadLibraryEx(string path, IntPtr reserved, uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi, ExactSpelling=true)]
    static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int kind,IntPtr buffer,int length,out int required);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool ConvertSidToStringSid(IntPtr sid,out IntPtr text);
    [DllImport("userenv.dll", CharSet=CharSet.Unicode)] static extern int GetAppContainerFolderPath(string sid,out IntPtr path);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent,IntPtr after,string className,string title);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern uint RegisterWindowMessage(string name);
    [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW",SetLastError=true)] static extern IntPtr GetWindowLongPtr(IntPtr window,int index);
    [DllImport("user32.dll",EntryPoint="SetWindowLongPtrW",SetLastError=true)] static extern IntPtr SetWindowLongPtr(IntPtr window,int index,IntPtr value);
    [DllImport("user32.dll",EntryPoint="CallWindowProcW")] static extern IntPtr CallWindowProc(IntPtr previous,IntPtr window,uint message,UIntPtr wp,IntPtr lp);
    [DllImport("user32.dll",EntryPoint="SendMessageW")] static extern IntPtr SendMessage(IntPtr window,uint message,UIntPtr wp,IntPtr lp);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)] delegate IntPtr WindowProcedure(IntPtr window,uint message,UIntPtr wp,IntPtr lp);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Hook(byte[] program, byte[] profile);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr kit, byte[] url);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Save(IntPtr document, byte[] url, byte[] format, IntPtr options);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Destroy(IntPtr instance);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr GetText(IntPtr kit);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void FreeText(IntPtr text);

    static byte[] Utf8(string value) { return Encoding.UTF8.GetBytes(value+"\0"); }
    static string FileUri(string value) { return new Uri(Path.GetFullPath(value)).AbsoluteUri; }
    static string ContainerStorage() {
        IntPtr token=IntPtr.Zero,buffer=IntPtr.Zero,sidText=IntPtr.Zero,path=IntPtr.Zero;
        try {
            if(!OpenProcessToken(new IntPtr(-1),8,out token)) throw new IOException("无法读取办公转换进程身份。");
            int size;
            GetTokenInformation(token,31,IntPtr.Zero,0,out size);
            if(size<=0) return null;
            buffer=Marshal.AllocHGlobal(size);
            if(!GetTokenInformation(token,31,buffer,size,out size)) throw new IOException("无法确认办公转换隔离身份。");
            IntPtr sid=Marshal.ReadIntPtr(buffer);
            if(sid==IntPtr.Zero) return null;
            if(!ConvertSidToStringSid(sid,out sidText) || GetAppContainerFolderPath(Marshal.PtrToStringUni(sidText),out path)!=0)
                throw new IOException("无法读取当前隔离用户的专属缓存目录。");
            return Marshal.PtrToStringUni(path);
        } finally {
            if(path!=IntPtr.Zero) Marshal.FreeCoTaskMem(path);
            if(sidText!=IntPtr.Zero) LocalFree(sidText);
            if(buffer!=IntPtr.Zero) Marshal.FreeHGlobal(buffer);
            if(token!=IntPtr.Zero) CloseHandle(token);
        }
    }
    static T Method<T>(IntPtr instance, int index) where T:class {
        IntPtr table=Marshal.ReadIntPtr(instance);
        if (Marshal.ReadIntPtr(table).ToInt64() < (index+1)*IntPtr.Size) throw new IOException("LibreOffice 接口版本不兼容。");
        return (T)(object)Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(table,index*IntPtr.Size),typeof(T));
    }
    static string Text(IntPtr kit,int index) {
        IntPtr pointer=Method<GetText>(kit,index)(kit);
        if (pointer==IntPtr.Zero) return "";
        try {
            var bytes=new List<byte>();
            for(int i=0;i<16384;i++) { byte value=Marshal.ReadByte(pointer,i); if(value==0) break; bytes.Add(value); }
            return Encoding.UTF8.GetString(bytes.ToArray());
        } finally { Method<FreeText>(kit,5)(pointer); }
    }
    static void OnOfficeThread(Action action) {
        // Windows Impress imports send synchronous native window messages. A
        // foreign caller holding SolarMutex deadlocks against the VCL thread.
        // Dispatch only onto this process's own pinned Office window; never
        // attach to another application or change the member's isolation.
        IntPtr window=IntPtr.Zero;uint ownerThread=0;
        uint ownProcess=(uint)Process.GetCurrentProcess().Id;
        foreach(IntPtr parent in new[]{IntPtr.Zero,new IntPtr(-3)}) {
            IntPtr after=IntPtr.Zero;
            for(int i=0;i<1024;i++) {
                after=FindWindowEx(parent,after,"SALCOMWND",null);
                if(after==IntPtr.Zero) break;
                uint process;uint thread=GetWindowThreadProcessId(after,out process);
                if(process==ownProcess) { window=after;ownerThread=thread;break; }
            }
            if(window!=IntPtr.Zero) break;
        }
        if(window==IntPtr.Zero) throw new IOException("找不到当前办公组件的文档处理线程。");
        if(ownerThread==GetCurrentThreadId()) { action();return; }
        uint request=RegisterWindowMessage("AIOS.Office.Convert."+Guid.NewGuid().ToString("N"));
        IntPtr previous=GetWindowLongPtr(window,-4);
        if(request==0 || previous==IntPtr.Zero) throw new IOException("无法准备办公组件线程调用。");
        Exception failure=null;
        WindowProcedure callback=delegate(IntPtr target,uint message,UIntPtr wp,IntPtr lp) {
            if(message!=request) return CallWindowProc(previous,target,message,wp,lp);
            try { action();return new IntPtr(1); }
            catch(Exception error) { failure=error;return IntPtr.Zero; }
        };
        if(SetWindowLongPtr(window,-4,Marshal.GetFunctionPointerForDelegate(callback))==IntPtr.Zero)
            throw new IOException("无法连接当前办公组件的文档处理线程。");
        try {
            IntPtr result=SendMessage(window,request,UIntPtr.Zero,IntPtr.Zero);
            if(failure!=null) throw failure;
            if(result!=new IntPtr(1)) throw new IOException("办公组件线程未完成文档转换。");
        } finally {
            SetWindowLongPtr(window,-4,previous);
            GC.KeepAlive(callback);
        }
    }

    static string Quote(string value) {
        var text=new StringBuilder("\"");int slashes=0;
        foreach(char c in value) {
            if(c=='\\') { slashes++;continue; }
            text.Append('\\',c=='"'?slashes*2+1:slashes);text.Append(c);slashes=0;
        }
        text.Append('\\',slashes*2);text.Append('"');return text.ToString();
    }
    [STAThread]
    static int Main(string[] args) {
        Console.OutputEncoding=new UTF8Encoding(false);
        string root=ContainerStorage() ?? Path.GetTempPath();
        if(args.Length>=2 && args[0]=="--aios-worker") {
            string path=Path.GetFullPath(args[1]);
            string name=Path.GetFileName(path);
            if(!string.Equals(Path.GetDirectoryName(path),Path.GetFullPath(root).TrimEnd('\\'),StringComparison.OrdinalIgnoreCase) || !System.Text.RegularExpressions.Regex.IsMatch(name,"^lo-[0-9a-f]{16}$") || !Directory.Exists(path))
                return 125;
            var forwarded=new string[args.Length-2];Array.Copy(args,2,forwarded,0,forwarded.Length);
            int result=Worker(forwarded,path);
            if(result==0) File.WriteAllText(Path.Combine(path,"conversion-complete.ok"),"complete",new UTF8Encoding(false));
            return result;
        }
        string profile=Path.Combine(Path.GetFullPath(root),"lo-"+Guid.NewGuid().ToString("N").Substring(0,16));
        int code=125;
        try {
            Directory.CreateDirectory(profile);
            var command=new StringBuilder("--aios-worker "+Quote(profile));
            foreach(string arg in args) command.Append(' ').Append(Quote(arg));
            using(var worker=new Process()) {
                worker.StartInfo=new ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location,command.ToString()) {
                    UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,
                    StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
                };
                // Seed before process creation so Win32 and the C runtime see
                // the same Office-only environment from their first read.
                worker.StartInfo.EnvironmentVariables.Remove("PYTHONPATH");
                worker.StartInfo.EnvironmentVariables.Remove("PYTHONHOME");
                worker.StartInfo.EnvironmentVariables.Remove("SAL_LOK_OPTIONS");
                worker.StartInfo.EnvironmentVariables["SAL_DISABLE_OPENCL"]="1";
                worker.StartInfo.EnvironmentVariables["SAL_DISABLEGL"]="1";
                worker.StartInfo.EnvironmentVariables["SAL_DISABLESKIA"]="1";
                worker.OutputDataReceived+=delegate(object sender,DataReceivedEventArgs e) { if(e.Data!=null) Console.Out.WriteLine(e.Data); };
                worker.ErrorDataReceived+=delegate(object sender,DataReceivedEventArgs e) { if(e.Data!=null) Console.Error.WriteLine(e.Data); };
                worker.Start();worker.BeginOutputReadLine();worker.BeginErrorReadLine();
                if(!worker.WaitForExit(110000)) { worker.Kill();worker.WaitForExit();code=124;Console.Error.WriteLine("办公转换超时。"); }
                else {
                    worker.WaitForExit();code=worker.ExitCode;
                    if(code==0 && !File.Exists(Path.Combine(profile,"conversion-complete.ok"))) {
                        Console.Error.WriteLine("办公组件已退出，但未确认转换完成。");code=125;
                    }
                }
            }
        } catch(Exception error) { Console.Error.WriteLine(error.Message);code=125; }
        finally {
            // Native libraries may retain extension-cache handles until exit.
            // The supervisor has not loaded Office, so cleanup happens afterward.
            try { if(Directory.Exists(profile)) Directory.Delete(profile,true); }
            catch(Exception error) { Console.Error.WriteLine("办公临时缓存清理失败："+error.Message);code=126; }
        }
        return code;
    }
    static int Worker(string[] args,string profile) {
        IntPtr kit=IntPtr.Zero;
        try {
            string program=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","aios-libreoffice","program"));
            string library=Path.Combine(program,"mergedlo.dll");
            if(!File.Exists(library)) throw new IOException("缺少内置 Hub 办公组件，请运行 setup-hub.ps1 修复。");
            bool version=false;
            string format=null,output=Directory.GetCurrentDirectory();
            var sources=new List<string>();
            for(int i=0;i<args.Length;i++) {
                string arg=args[i];
                if(arg=="--version") version=true;
                else if(arg=="--convert-to" || arg=="--outdir") {
                    if(++i>=args.Length) throw new ArgumentException("缺少转换参数。");
                    if(arg=="--convert-to") format=args[i]; else output=args[i];
                } else if(arg=="--headless" || arg=="--invisible" || arg=="--nologo" || arg=="--norestore" || arg=="--nofirststartwizard" || arg=="--nolockcheck") { }
                // Every invocation owns its private profile, also for concurrent jobs.
                else if(arg.StartsWith("-env:UserInstallation=",StringComparison.OrdinalIgnoreCase)) { }
                else if(arg.StartsWith("-")) throw new ArgumentException("不支持的转换参数："+arg);
                else sources.Add(Path.GetFullPath(arg));
            }
            if(!version) {
                if(string.IsNullOrEmpty(format) || sources.Count==0) throw new ArgumentException("用法：soffice --headless --convert-to pdf --outdir 输出目录 输入文件");
                if(format.IndexOf(':')>=0 || format.IndexOfAny(Path.GetInvalidFileNameChars())>=0 || format.Contains(".") || format.Length>16)
                    throw new ArgumentException("转换格式请使用扩展名，例如 pdf、xlsx、docx 或 pptx；此入口不支持自定义筛选器。");
                foreach(string source in sources) if(!File.Exists(source)) throw new FileNotFoundException("找不到输入文件。",source);
                Directory.CreateDirectory(output);
            }
            // Hub injects its Python 3.12 site-packages. LibreOffice embeds its
            // own Python version; do not load the agent's modules into it.
            Environment.SetEnvironmentVariable("PYTHONPATH",null);
            Environment.SetEnvironmentVariable("PYTHONHOME",null);
            Environment.SetEnvironmentVariable("SAL_USE_VCLPLUGIN","svp");
            Environment.SetEnvironmentVariable("SAL_DISABLE_OPENCL","1");
            Environment.SetEnvironmentVariable("SAL_DISABLEGL","1");
            Environment.SetEnvironmentVariable("SAL_DISABLESKIA","1");
            if(!SetDllDirectory(program)) throw new IOException("无法配置内置办公组件搜索目录。");
            IntPtr module=LoadLibraryEx(library,IntPtr.Zero,8);
            if(module==IntPtr.Zero) throw new IOException("无法加载内置办公组件，错误码 "+Marshal.GetLastWin32Error());
            IntPtr entry=GetProcAddress(module,"libreofficekit_hook_2");
            if(entry==IntPtr.Zero) throw new IOException("内置办公组件缺少文档转换接口。");
            var initialize=(Hook)Marshal.GetDelegateForFunctionPointer(entry,typeof(Hook));
            kit=initialize(Utf8(program),Utf8(FileUri(profile)));
            if(kit==IntPtr.Zero) throw new IOException("办公文档转换接口初始化失败。");
            Console.Error.WriteLine("办公组件已就绪。");
            if(version) { Console.WriteLine("LibreOffice "+Text(kit,10)); return 0; }
            OnOfficeThread(delegate { foreach(string source in sources) {
                string target=Path.GetFullPath(Path.Combine(output,Path.GetFileNameWithoutExtension(source)+"."+format));
                if(string.Equals(source,target,StringComparison.OrdinalIgnoreCase)) throw new IOException("输出不能覆盖输入原件，请使用不同的输出目录。");
                IntPtr document=Method<Load>(kit,2)(kit,Utf8(FileUri(source)));
                if(document==IntPtr.Zero) throw new IOException("文档打开失败："+Text(kit,3));
                Console.Error.WriteLine("文档已打开，正在导出。");
                try {
                    if(Method<Save>(document,2)(document,Utf8(FileUri(target)),Utf8(format),IntPtr.Zero)==0 || !File.Exists(target))
                        throw new IOException("文档转换失败："+Text(kit,3));
                } finally { Method<Destroy>(document,1)(document); }
                Console.WriteLine("转换完成："+target);
            } });
            return 0;
        } catch(Exception error) { Console.Error.WriteLine(error.Message); return 125; }
        finally {
            if(kit!=IntPtr.Zero) Method<Destroy>(kit,1)(kit);
        }
    }
}
