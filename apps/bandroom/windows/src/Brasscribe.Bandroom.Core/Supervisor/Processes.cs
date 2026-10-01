namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>What to run: the executable, its arguments, working directory and extra environment.</summary>
public sealed record ProcessSpec(
    string FileName,
    IReadOnlyList<string> Arguments,
    string WorkingDirectory,
    IReadOnlyDictionary<string, string> Environment)
{
    /// <summary>Variables of this process the child must not inherit (it gets the rest, plus <see cref="Environment"/>).</summary>
    public IReadOnlyList<string> Unset { get; init; } = [];
}

/// <summary>A started child process. <see cref="Kill"/> ends the whole tree (pixi starts python).</summary>
public interface IEngineProcess : IDisposable
{
    int Id { get; }
    Task<int> WaitForExitAsync();
    void Kill();
}

/// <summary>Starts child processes; every output line (stdout and stderr) goes to the output callback.</summary>
public interface IProcessLauncher
{
    IEngineProcess Start(ProcessSpec spec, Action<string> output);
}

/// <summary>Whether a loopback TCP port can be listened on.</summary>
public interface IPortProbe
{
    bool IsFree(int port);
}

/// <summary>Tries to bind the port on 0.0.0.0, which the engine does with --lan.</summary>
public sealed class TcpPortProbe : IPortProbe
{
    public bool IsFree(int port)
    {
        try
        {
            var l = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Any, port);
            l.Start();
            l.Stop();
            return true;
        }
        catch (System.Net.Sockets.SocketException)
        {
            return false;
        }
    }
}

/// <summary>
/// Plain System.Diagnostics launcher. On Windows the app wraps it so the tree lives in a job object
/// (see JobObjectLauncher in the app); <see cref="IEngineProcess.Kill"/> here kills the process tree.
/// </summary>
public sealed class SystemProcessLauncher : IProcessLauncher
{
    public IEngineProcess Start(ProcessSpec spec, Action<string> output)
    {
        var psi = new System.Diagnostics.ProcessStartInfo(spec.FileName)
        {
            WorkingDirectory = spec.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8,
            StandardErrorEncoding = System.Text.Encoding.UTF8,
        };
        foreach (var a in spec.Arguments) psi.ArgumentList.Add(a);
        foreach (var k in spec.Unset) psi.Environment.Remove(k);
        foreach (var (k, v) in spec.Environment) psi.Environment[k] = v;
        var p = new System.Diagnostics.Process { StartInfo = psi, EnableRaisingEvents = true };
        p.OutputDataReceived += (_, e) => { if (e.Data is not null) output(e.Data); };
        p.ErrorDataReceived += (_, e) => { if (e.Data is not null) output(e.Data); };
        p.Start();
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        return new SystemProcess(p);
    }

    private sealed class SystemProcess(System.Diagnostics.Process p) : IEngineProcess
    {
        public int Id { get; } = p.Id;

        public async Task<int> WaitForExitAsync()
        {
            await p.WaitForExitAsync().ConfigureAwait(false);
            return p.ExitCode;
        }

        public void Kill()
        {
            try { p.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) { } // already exited
            catch (System.ComponentModel.Win32Exception) { }
        }

        public void Dispose() => p.Dispose();
    }
}
