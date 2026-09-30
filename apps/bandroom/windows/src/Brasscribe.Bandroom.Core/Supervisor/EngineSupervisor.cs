using System.Text.Json;
using Brasscribe.Bandroom.Core.Engine;

namespace Brasscribe.Bandroom.Core.Supervisor;

public enum EngineState
{
    /// <summary>Not running, by choice (or never started).</summary>
    Stopped,
    /// <summary>The process is starting, or waiting to be restarted after it exited.</summary>
    Starting,
    /// <summary>/v1/health answers on the chosen port.</summary>
    Running,
    Stopping,
    /// <summary>It kept stopping: three unexpected exits within five minutes.</summary>
    Error,
}

public enum EngineProblem
{
    None,
    /// <summary>Every port from 8765 to 8775 is taken.</summary>
    NoFreePort,
}

public sealed record SupervisorOptions
{
    public int FirstPort { get; init; } = 8765;
    public int LastPort { get; init; } = 8775;
    public TimeSpan HealthInterval { get; init; } = TimeSpan.FromMilliseconds(500);
    /// <summary>How long Starting may take before the attempt counts as a failure (first start imports torch).</summary>
    public TimeSpan StartTimeout { get; init; } = TimeSpan.FromMinutes(3);
    public TimeSpan StopTimeout { get; init; } = TimeSpan.FromSeconds(10);
    /// <summary>How often a running engine is asked whether it still answers.</summary>
    public TimeSpan LivenessInterval { get; init; } = TimeSpan.FromSeconds(30);
    /// <summary>
    /// Unanswered checks in a row before a running engine counts as stuck and is restarted. Generous: an engine busy
    /// with a score may answer slowly.
    /// </summary>
    public int LivenessFailures { get; init; } = 4;
    public int MaxFailures { get; init; } = 3;
    public TimeSpan FailureWindow { get; init; } = TimeSpan.FromMinutes(5);
    public TimeSpan FirstBackoff { get; init; } = TimeSpan.FromSeconds(2);
    public TimeSpan MaxBackoff { get; init; } = TimeSpan.FromSeconds(30);
    /// <summary>engine.json for Play on the same computer: port, pid, server id and version. Never the admin token.</summary>
    public string? StatusFilePath { get; init; }
}

/// <summary>
/// Starts the engine as a child process and keeps it running: picks the first free port, waits for
/// /v1/health, asks it again every <see cref="SupervisorOptions.LivenessInterval"/> while it runs, restarts it with a
/// growing back-off when it exits unexpectedly or stops answering, and gives up (Error)
/// after <see cref="SupervisorOptions.MaxFailures"/> failures within <see cref="SupervisorOptions.FailureWindow"/>.
/// An exit while starting because the port was taken moves to the next port and is not a failure.
/// </summary>
public sealed class EngineSupervisor : IAsyncDisposable
{
    private readonly IProcessLauncher _launcher;
    private readonly IPortProbe _ports;
    private readonly Func<int, CancellationToken, Task<HealthInfo?>> _health;
    private readonly Func<int, ProcessSpec> _spec;
    private readonly TimeProvider _time;
    private readonly EngineLog _log;
    private readonly SupervisorOptions _o;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly List<DateTimeOffset> _failures = [];
    private IEngineProcess? _process;
    private int _generation;
    private CancellationTokenSource _cts = new();

    public EngineSupervisor(
        IProcessLauncher launcher,
        IPortProbe ports,
        Func<int, CancellationToken, Task<HealthInfo?>> health,
        Func<int, ProcessSpec> spec,
        EngineLog log,
        TimeProvider? time = null,
        SupervisorOptions? options = null)
    {
        _launcher = launcher;
        _ports = ports;
        _health = health;
        _spec = spec;
        _log = log;
        _time = time ?? TimeProvider.System;
        _o = options ?? new SupervisorOptions();
    }

    public EngineState State { get; private set; } = EngineState.Stopped;
    public EngineProblem Problem { get; private set; }
    public int? Port { get; private set; }
    public int? ProcessId { get; private set; }
    public HealthInfo? Health { get; private set; }
    public int? LastExitCode { get; private set; }
    public int RecentFailures { get { lock (_failures) return _failures.Count; } }

    /// <summary>Raised on every change of state, port or health, on a thread-pool thread.</summary>
    public event Action? Changed;

    private void Raise() => Changed?.Invoke();

    /// <summary>Start (or Try again after Error). Starting a running engine does nothing.</summary>
    public async Task StartAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (State is EngineState.Starting or EngineState.Running) return;
            lock (_failures) _failures.Clear();
            LaunchLocked(_o.FirstPort);
        }
        finally { _gate.Release(); }
    }

    /// <summary>Stop on purpose: no restart follows.</summary>
    public async Task StopAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try { await StopLockedAsync().ConfigureAwait(false); }
        finally { _gate.Release(); }
    }

    public async Task RestartAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            await StopLockedAsync().ConfigureAwait(false);
            lock (_failures) _failures.Clear();
            LaunchLocked(_o.FirstPort);
        }
        finally { _gate.Release(); }
    }

    private async Task StopLockedAsync()
    {
        _generation++; // monitors and pending restarts of the old process stand down
        _cts.Cancel();
        _cts = new CancellationTokenSource();
        var p = _process;
        _process = null;
        if (p is not null)
        {
            State = EngineState.Stopping;
            Raise();
            _log.Write("bandroom: stopping the engine");
            p.Kill();
            var exit = p.WaitForExitAsync();
            await Task.WhenAny(exit, Task.Delay(_o.StopTimeout, _time)).ConfigureAwait(false);
            p.Dispose();
        }
        State = EngineState.Stopped;
        Problem = EngineProblem.None;
        Port = null;
        ProcessId = null;
        Health = null;
        DeleteStatusFile();
        Raise();
    }

    private void LaunchLocked(int fromPort)
    {
        int? port = null;
        for (int p = fromPort; p <= _o.LastPort; p++)
            if (_ports.IsFree(p)) { port = p; break; }
        if (port is null)
        {
            _log.Write($"bandroom: ports {_o.FirstPort}-{_o.LastPort} are all in use");
            State = EngineState.Stopped;
            Problem = EngineProblem.NoFreePort;
            Port = null;
            Raise();
            return;
        }

        int gen = ++_generation;
        var spec = _spec(port.Value);
        _log.Write($"bandroom: starting the engine on port {port}: {spec.FileName} {string.Join(' ', spec.Arguments)}");
        IEngineProcess proc;
        try
        {
            proc = _launcher.Start(spec, _log.Write);
        }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or IOException or InvalidOperationException)
        {
            _log.Write($"bandroom: could not start the engine: {e.Message}");
            State = EngineState.Starting;
            Problem = EngineProblem.None;
            Raise();
            _ = Task.Run(() => OnExitedAsync(gen, port.Value, -1, wasStarting: true));
            return;
        }
        _process = proc;
        State = EngineState.Starting;
        Problem = EngineProblem.None;
        Port = port;
        ProcessId = proc.Id;
        Health = null;
        Raise();
        var ct = _cts.Token;
        _ = Task.Run(() => MonitorAsync(proc, gen, port.Value, ct));
    }

    private async Task MonitorAsync(IEngineProcess proc, int gen, int port, CancellationToken ct)
    {
        var exit = proc.WaitForExitAsync();
        var deadline = _time.GetUtcNow() + _o.StartTimeout;
        bool reachedRunning = false;
        int misses = 0;
        while (!exit.IsCompleted && !ct.IsCancellationRequested)
        {
            HealthInfo? h = null;
            try { h = await _health(port, ct).ConfigureAwait(false); }
            catch (Exception e) when (e is HttpRequestException or TaskCanceledException or OperationCanceledException or EngineHttpException or JsonException) { }
            if (reachedRunning)
            {
                // Running: a process that is there but no longer answers (stuck) is restarted like one that exited.
                if (h is not null) misses = 0;
                else if (!ct.IsCancellationRequested && ++misses >= _o.LivenessFailures)
                {
                    _log.Write($"bandroom: the engine stopped answering ({misses} checks in a row), restarting it");
                    proc.Kill();
                    break;
                }
            }
            else if (h is not null)
            {
                await _gate.WaitAsync(CancellationToken.None).ConfigureAwait(false);
                try
                {
                    if (gen != _generation) return;
                    WriteStatusFile(port, proc.Id, h.ServerId, h.Version);
                    Health = h;
                    reachedRunning = true;
                    State = EngineState.Running;
                    _log.Write($"bandroom: the engine is running on port {port} (version {h.Version}, {h.Device})");
                }
                finally { _gate.Release(); }
                Raise();
            }
            else if (_time.GetUtcNow() > deadline)
            {
                _log.Write($"bandroom: the engine did not answer within {_o.StartTimeout.TotalSeconds:0} s");
                proc.Kill();
                break;
            }
            try { await Task.WhenAny(exit, Task.Delay(reachedRunning ? _o.LivenessInterval : _o.HealthInterval, _time, ct)).ConfigureAwait(false); }
            catch (OperationCanceledException) { }
        }
        int code;
        try { code = await exit.ConfigureAwait(false); }
        catch (InvalidOperationException) { code = -1; }
        await OnExitedAsync(gen, port, code, wasStarting: !reachedRunning).ConfigureAwait(false);
    }

    private async Task OnExitedAsync(int gen, int port, int code, bool wasStarting)
    {
        TimeSpan delay;
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (gen != _generation) return; // stopped or restarted on purpose
            _process?.Dispose();
            _process = null;
            LastExitCode = code;
            ProcessId = null;
            Health = null;
            DeleteStatusFile();
            _log.Write($"bandroom: the engine exited with code {code}");

            // Someone else took the port between the probe and the bind: try the next one, not a failure.
            if (wasStarting && port < _o.LastPort && !_ports.IsFree(port))
            {
                _log.Write($"bandroom: port {port} is taken, trying the next one");
                LaunchLocked(port + 1);
                return;
            }

            var now = _time.GetUtcNow();
            int failures;
            lock (_failures)
            {
                _failures.Add(now);
                _failures.RemoveAll(t => now - t > _o.FailureWindow);
                failures = _failures.Count;
            }
            if (failures >= _o.MaxFailures)
            {
                _log.Write($"bandroom: {failures} failures within {_o.FailureWindow.TotalMinutes:0} min, not restarting");
                State = EngineState.Error;
                Port = null;
                Raise();
                return;
            }
            delay = Backoff(failures);
            State = EngineState.Starting;
            Raise();
            _log.Write($"bandroom: restarting in {delay.TotalSeconds:0} s");
        }
        finally { _gate.Release(); }

        var ct = _cts.Token;
        try { await Task.Delay(delay, _time, ct).ConfigureAwait(false); }
        catch (OperationCanceledException) { return; }

        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (gen != _generation || State != EngineState.Starting) return;
            LaunchLocked(_o.FirstPort);
        }
        finally { _gate.Release(); }
    }

    /// <summary>2 s, 4 s, 8 s … up to <see cref="SupervisorOptions.MaxBackoff"/>, by failures in the window.</summary>
    public TimeSpan Backoff(int failures)
    {
        double s = _o.FirstBackoff.TotalSeconds * Math.Pow(2, Math.Max(0, failures - 1));
        return TimeSpan.FromSeconds(Math.Min(s, _o.MaxBackoff.TotalSeconds));
    }

    private void WriteStatusFile(int port, int pid, string? serverId, string version)
    {
        if (_o.StatusFilePath is not { } path) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(new { port, pid, server_id = serverId, version }));
            File.Move(tmp, path, overwrite: true);
        }
        catch (IOException e) { _log.Write($"bandroom: could not write {path}: {e.Message}"); }
        catch (UnauthorizedAccessException e) { _log.Write($"bandroom: could not write {path}: {e.Message}"); }
    }

    private void DeleteStatusFile()
    {
        if (_o.StatusFilePath is not { } path) return;
        try { File.Delete(path); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync().ConfigureAwait(false);
        _gate.Dispose();
        _cts.Dispose();
    }
}
