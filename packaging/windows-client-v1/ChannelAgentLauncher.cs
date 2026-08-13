using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

internal static class ChannelAgentLauncher
{
    [DllImport("kernel32.dll")]
    private static extern bool AttachConsole(int processId);

    private const int AttachParentProcess = -1;

    [STAThread]
    public static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] != "--background" && args[0] != "tray")
        {
            AttachConsole(AttachParentProcess);
            return RunPython(args, true);
        }

        bool created;
        using (var mutex = new Mutex(true, "Local\\AI-CS-ChannelAgent-Tray-v1", out created))
        {
            if (!created)
            {
                SignalOpenAssistant();
                return 0;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var context = new TrayApplicationContext())
            {
                Application.Run(context);
            }
        }
        return 0;
    }

    internal static string Home
    {
        get { return AppDomain.CurrentDomain.BaseDirectory; }
    }

    internal static string DataRoot
    {
        get
        {
            var configured = Environment.GetEnvironmentVariable("AI_CS_CHANNEL_AGENT_DATA_ROOT");
            if (!String.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "AI-CS", "ChannelAgent");
        }
    }

    internal static int RunPython(IEnumerable<string> args, bool wait)
    {
        var runtime = Path.Combine(Home, "runtime", "python");
        var python = Path.Combine(runtime, "python.exe");
        var application = Path.Combine(Home, "app", "channel-agent.pyz");
        if (!File.Exists(python) || !File.Exists(application))
        {
            if (Environment.UserInteractive)
            {
                MessageBox.Show(
                    "Channel Agent 安装不完整，请重新安装。",
                    "AI-CS Channel Agent",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            return 4;
        }
        var arguments = new List<string> { Quote(application) };
        foreach (var argument in args) arguments.Add(Quote(argument));
        var start = new ProcessStartInfo
        {
            FileName = python,
            Arguments = String.Join(" ", arguments.ToArray()),
            WorkingDirectory = Home,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        start.EnvironmentVariables["PYTHONHOME"] = runtime;
        start.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        start.EnvironmentVariables["AI_CS_CHANNEL_AGENT_HOME"] = Home;
        var process = Process.Start(start);
        if (process == null) return 4;
        if (!wait) return 0;
        using (process)
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    internal static string Quote(string value)
    {
        if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0)
            return value;
        var output = new StringBuilder();
        output.Append('"');
        var backslashes = 0;
        foreach (var character in value)
        {
            if (character == '\\') { backslashes++; continue; }
            if (character == '"')
            {
                output.Append('\\', backslashes * 2 + 1).Append('"');
                backslashes = 0;
                continue;
            }
            output.Append('\\', backslashes);
            backslashes = 0;
            output.Append(character);
        }
        output.Append('\\', backslashes * 2).Append('"');
        return output.ToString();
    }

    internal static void SignalOpenAssistant()
    {
        try
        {
            Directory.CreateDirectory(Path.Combine(DataRoot, "runtime"));
            File.WriteAllText(Path.Combine(DataRoot, "runtime", "open-assistant.request"), "open\n");
        }
        catch { }
    }
}

internal sealed class TrayApplicationContext : ApplicationContext
{
    private readonly NotifyIcon tray;
    private readonly System.Windows.Forms.Timer timer;
    private readonly ToolStripMenuItem statusItem;
    private readonly ToolStripMenuItem autostartItem;
    private readonly Dictionary<string, Icon> brandIcons;
    private bool exiting;
    private bool syncingAutostart;
    private bool openWhenReady = true;
    private bool agentStartRequested;
    private bool restartPending;
    private bool waitingForAssistantRecovery;
    private DateTime assistantRecoveryDeadlineUtc = DateTime.MinValue;

    internal TrayApplicationContext()
    {
        brandIcons = LoadBrandIcons();
        statusItem = new ToolStripMenuItem("Agent 状态：正在启动") { Enabled = false };
        autostartItem = new ToolStripMenuItem("开机自动启动") { CheckOnClick = true };
        autostartItem.CheckedChanged += delegate
        {
            if (!syncingAutostart) SetAutostart(autostartItem.Checked);
        };

        var menu = new ContextMenuStrip();
        menu.Items.Add(statusItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("打开 AI 客服助手", null, delegate { OpenAssistant(false); });
        menu.Items.Add("打开 PDD 客服工作台", null, delegate { OpenPdd(); });
        menu.Items.Add("检查并恢复连接", null, delegate { Recover(); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(autostartItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("安全停止并退出", null, delegate { SafeExit(); });

        tray = new NotifyIcon
        {
            Icon = BrandIcon("warning", SystemIcons.Warning),
            Text = "AI-CS Channel Agent - 正在启动",
            Visible = true,
            ContextMenuStrip = menu,
        };
        tray.DoubleClick += delegate { OpenAssistant(false); };
        tray.BalloonTipTitle = "AI-CS Channel Agent";
        tray.BalloonTipText = "Agent 已在后台启动。双击托盘图标打开客服助手。";
        tray.ShowBalloonTip(3000);

        var preserveOnLaunch = Path.Combine(
            ChannelAgentLauncher.DataRoot,
            "runtime",
            "preserve-assistant-on-launch.request");
        if (File.Exists(preserveOnLaunch))
        {
            try { File.Delete(preserveOnLaunch); } catch { }
            openWhenReady = false;
        }

        if (ConfigurationExists())
        {
            StartAgent();
        }
        else
        {
            statusItem.Text = "Agent 状态：等待首次连接配置";
            tray.BalloonTipText = "请在首次连接向导中选择主机、输入连接码并人工确认。";
            tray.ShowBalloonTip(4000);
            ChannelAgentLauncher.RunPython(
                new[] { "setup", "--data-root", ChannelAgentLauncher.DataRoot }, false);
        }
        if (!ReadAutostartStatus())
        {
            ChannelAgentLauncher.RunPython(
                new[]
                {
                    "autostart",
                    "enable",
                    "--data-root",
                    ChannelAgentLauncher.DataRoot,
                },
                true);
        }
        syncingAutostart = true;
        autostartItem.Checked = ReadAutostartStatus();
        syncingAutostart = false;

        timer = new System.Windows.Forms.Timer { Interval = 2000 };
        timer.Tick += delegate { RefreshStatus(); };
        timer.Start();
        RefreshStatus();
    }

    private void RefreshStatus()
    {
        if (!agentStartRequested && ConfigurationExists()) StartAgent();
        var state = ReadText(Path.Combine(
            ChannelAgentLauncher.DataRoot, "runtime", "channel-agent-state.json"));
        var status = JsonValue(state, "process_status") ?? "STARTING";
        var experience = JsonValue(state, "experience_status") ?? "INSTALLED";
        var pdd = JsonValue(state, "pdd_login_state") ?? "NOT_OBSERVED";
        statusItem.Text = "客服端：" + ExperienceLabel(experience) + " / PDD：" + PddLabel(pdd);
        tray.Text = TrimTooltip(
            "AI-CS 客服端 - " + ExperienceLabel(experience) + " - PDD " + PddLabel(pdd));
        tray.Icon = status == "RUNNING" ? BrandIcon("normal", SystemIcons.Information)
            : status == "DEGRADED" || status == "STARTING"
                ? BrandIcon("warning", SystemIcons.Warning)
            : status == "FAILED" ? BrandIcon("error", SystemIcons.Error)
            : BrandIcon("offline", SystemIcons.Application);

        var restartRequest = Path.Combine(
            ChannelAgentLauncher.DataRoot, "runtime", "restart-agent.request");
        if (File.Exists(restartRequest))
        {
            var restartInstruction = ReadText(restartRequest);
            var preserveAssistant = restartInstruction.IndexOf(
                "preserve-assistant", StringComparison.OrdinalIgnoreCase) >= 0;
            try { File.Delete(restartRequest); } catch { }
            restartPending = true;
            openWhenReady = !preserveAssistant;
            waitingForAssistantRecovery = preserveAssistant;
            assistantRecoveryDeadlineUtc = DateTime.MinValue;
            if (preserveAssistant)
            {
                var staleMarker = Path.Combine(
                    ChannelAgentLauncher.DataRoot,
                    "runtime",
                    "desktop-bootstrap-handoff-consumed.json");
                try { File.Delete(staleMarker); } catch { }
            }
        }
        if (restartPending
            && (status == "STOPPED" || status == "FAILED")
            && !DesktopAssistantAvailable())
        {
            agentStartRequested = false;
            restartPending = false;
            if (waitingForAssistantRecovery)
            {
                assistantRecoveryDeadlineUtc = DateTime.UtcNow.AddSeconds(15);
            }
            StartAgent();
            return;
        }

        if (waitingForAssistantRecovery
            && !restartPending
            && DesktopAssistantAvailable())
        {
            var recoveryMarker = Path.Combine(
                ChannelAgentLauncher.DataRoot,
                "runtime",
                "desktop-bootstrap-handoff-consumed.json");
            if (File.Exists(recoveryMarker))
            {
                try { File.Delete(recoveryMarker); } catch { }
                waitingForAssistantRecovery = false;
                openWhenReady = false;
            }
            else if (assistantRecoveryDeadlineUtc != DateTime.MinValue
                && DateTime.UtcNow >= assistantRecoveryDeadlineUtc)
            {
                waitingForAssistantRecovery = false;
                OpenAssistant(true);
            }
            if (waitingForAssistantRecovery) return;
        }

        var request = Path.Combine(
            ChannelAgentLauncher.DataRoot, "runtime", "open-assistant.request");
        if (File.Exists(request))
        {
            try { File.Delete(request); } catch { }
            OpenAssistant(false);
        }
        else if (openWhenReady && DesktopAssistantAvailable())
        {
            OpenAssistant(true);
        }
    }

    private void OpenAssistant(bool silentWhenStarting)
    {
        var runtime = ReadText(Path.Combine(
            ChannelAgentLauncher.DataRoot, "runtime", "desktop-assistant.json"));
        var url = RequestFreshWorkspaceUrl(runtime);
        if (String.IsNullOrWhiteSpace(url))
        {
            if (!silentWhenStarting)
            {
                MessageBox.Show(
                    "客服助手的本地服务没有响应。\n\n"
                    + "请在右下角托盘中右键 ChannelAgent，选择“检查并恢复连接”，"
                    + "等待约 5 秒后再打开。",
                    "AI-CS Channel Agent",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
            }
            return;
        }
        var edge = FindEdge();
        if (edge == null)
        {
            openWhenReady = false;
            MessageBox.Show(
                "未找到 Microsoft Edge，无法打开客服助手。",
                "AI-CS Channel Agent",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }
        var profile = Path.Combine(
            ChannelAgentLauncher.DataRoot, "browser", "assistant-ui");
        Directory.CreateDirectory(profile);
        Process.Start(new ProcessStartInfo
        {
            FileName = edge,
            Arguments = "--app=" + ChannelAgentLauncher.Quote(url)
                + " --user-data-dir=" + ChannelAgentLauncher.Quote(profile)
                + " --no-first-run --no-default-browser-check",
            UseShellExecute = false,
        });
        openWhenReady = false;
    }

    private static string RequestFreshWorkspaceUrl(string runtime)
    {
        var launcherUrl = JsonValue(runtime, "launcher_url");
        var capability = JsonValue(runtime, "launcher_capability");
        if (String.IsNullOrWhiteSpace(launcherUrl)
            || String.IsNullOrWhiteSpace(capability))
        {
            // One RC compatibility window for an older local runtime.  New
            // runtimes always use the one-time launcher handoff below.
            return JsonValue(runtime, "workspace_url");
        }
        Uri endpoint;
        if (!Uri.TryCreate(launcherUrl, UriKind.Absolute, out endpoint)
            || endpoint.Scheme != Uri.UriSchemeHttp
            || (endpoint.Host != "127.0.0.1" && endpoint.Host != "localhost")
            || endpoint.AbsolutePath != "/launcher-api/v1/open")
        {
            return null;
        }
        try
        {
            var request = (HttpWebRequest)WebRequest.Create(endpoint);
            request.Method = "POST";
            request.Proxy = null;
            request.Timeout = 2000;
            request.ReadWriteTimeout = 2000;
            request.ContentLength = 0;
            request.Headers["X-Channel-Agent-Launcher"] = capability;
            using (var response = (HttpWebResponse)request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
            {
                if (response.StatusCode != HttpStatusCode.OK) return null;
                var fresh = JsonValue(reader.ReadToEnd(), "workspace_url");
                Uri workspace;
                if (!Uri.TryCreate(fresh, UriKind.Absolute, out workspace)
                    || workspace.Scheme != Uri.UriSchemeHttp
                    || (workspace.Host != "127.0.0.1" && workspace.Host != "localhost"))
                {
                    return null;
                }
                return fresh;
            }
        }
        catch
        {
            return null;
        }
    }

    private static bool DesktopAssistantAvailable()
    {
        var runtime = ReadText(Path.Combine(
            ChannelAgentLauncher.DataRoot, "runtime", "desktop-assistant.json"));
        return !String.IsNullOrWhiteSpace(JsonValue(runtime, "workspace_url"));
    }

    private void OpenPdd()
    {
        var runtime = ReadText(Path.Combine(
            ChannelAgentLauncher.DataRoot, "runtime", "desktop-assistant.json"));
        if (!RequestPddWorkspaceOpen(runtime))
        {
            tray.BalloonTipText = "PDD 客服工作台暂时无法打开，请检查 Agent 配置。";
            tray.ShowBalloonTip(3000);
        }
    }

    private static bool RequestPddWorkspaceOpen(string runtime)
    {
        var launcherUrl = JsonValue(runtime, "launcher_url");
        var capability = JsonValue(runtime, "launcher_capability");
        Uri launcherEndpoint;
        if (String.IsNullOrWhiteSpace(capability)
            || !Uri.TryCreate(launcherUrl, UriKind.Absolute, out launcherEndpoint)
            || launcherEndpoint.Scheme != Uri.UriSchemeHttp
            || (launcherEndpoint.Host != "127.0.0.1" && launcherEndpoint.Host != "localhost")
            || launcherEndpoint.AbsolutePath != "/launcher-api/v1/open")
        {
            return false;
        }
        var endpoint = new Uri(launcherEndpoint, "/launcher-api/v1/pdd/open");
        try
        {
            var request = (HttpWebRequest)WebRequest.Create(endpoint);
            request.Method = "POST";
            request.Proxy = null;
            request.Timeout = 2000;
            request.ReadWriteTimeout = 2000;
            request.ContentLength = 0;
            request.Headers["X-Channel-Agent-Launcher"] = capability;
            request.Headers["X-Channel-Agent-Intent"] = "HUMAN_REQUESTED_PDD_WINDOW";
            using (var response = (HttpWebResponse)request.GetResponse())
            {
                return response.StatusCode == HttpStatusCode.Accepted;
            }
        }
        catch
        {
            return false;
        }
    }

    private void Recover()
    {
        if (!ConfigurationExists())
        {
            ChannelAgentLauncher.RunPython(
                new[] { "setup", "--data-root", ChannelAgentLauncher.DataRoot }, false);
            return;
        }
        agentStartRequested = false;
        StartAgent();
        // Recovery repairs the local Agent service only.  PDD remains an
        // explicit human action and must never be opened as a side effect of
        // diagnosing or restarting the desktop assistant.
        openWhenReady = true;
        RefreshStatus();
    }

    private void StartAgent()
    {
        if (agentStartRequested) return;
        agentStartRequested = true;
        ChannelAgentLauncher.RunPython(
            new[] { "start", "--data-root", ChannelAgentLauncher.DataRoot }, false);
    }

    private static bool ConfigurationExists()
    {
        return File.Exists(Path.Combine(
            ChannelAgentLauncher.DataRoot, "config", "agent.json"));
    }

    private void SetAutostart(bool enabled)
    {
        if (exiting) return;
        var code = ChannelAgentLauncher.RunPython(
            new[]
            {
                "autostart",
                enabled ? "enable" : "disable",
                "--data-root",
                ChannelAgentLauncher.DataRoot,
            },
            true);
        if (code != 0)
        {
            syncingAutostart = true;
            autostartItem.Checked = !enabled;
            syncingAutostart = false;
            MessageBox.Show(
                "开机启动设置失败，请检查当前 Windows 用户权限。",
                "AI-CS Channel Agent",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
    }

    private bool ReadAutostartStatus()
    {
        var startup = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Startup),
            "AI-CS-Channel-Agent.cmd");
        return File.Exists(startup);
    }

    private void SafeExit()
    {
        var answer = MessageBox.Show(
            "这会停止消息观察和受控发送，并保存运行状态。PDD 登录 Profile 不会被删除。是否继续？",
            "安全停止 Channel Agent",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning);
        if (answer != DialogResult.Yes) return;
        exiting = true;
        timer.Stop();
        ChannelAgentLauncher.RunPython(
            new[]
            {
                "stop",
                "--data-root",
                ChannelAgentLauncher.DataRoot,
                "--wait-seconds",
                "8",
            },
            true);
        tray.Visible = false;
        ExitThread();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            timer.Dispose();
            tray.Dispose();
            foreach (var icon in brandIcons.Values) icon.Dispose();
        }
        base.Dispose(disposing);
    }

    private Icon BrandIcon(string status, Icon fallback)
    {
        Icon icon;
        return brandIcons.TryGetValue(status, out icon) ? icon : fallback;
    }

    private static Dictionary<string, Icon> LoadBrandIcons()
    {
        var icons = new Dictionary<string, Icon>(StringComparer.OrdinalIgnoreCase);
        foreach (var status in new[] { "normal", "warning", "error", "offline" })
        {
            var path = Path.Combine(
                ChannelAgentLauncher.Home,
                "assets",
                "branding",
                "channel-agent-tray-" + status + ".ico");
            if (!File.Exists(path)) continue;
            try
            {
                using (var source = new Icon(path))
                {
                    icons[status] = (Icon)source.Clone();
                }
            }
            catch
            {
                // Branding must never prevent the runtime from starting. The
                // release gate validates official assets; runtime falls back
                // to the appropriate Windows system icon.
            }
        }
        return icons;
    }

    private static string ReadText(string path)
    {
        try { return File.Exists(path) ? File.ReadAllText(path, Encoding.UTF8) : ""; }
        catch { return ""; }
    }

    private static string JsonValue(string json, string name)
    {
        var pattern = "\\\"" + Regex.Escape(name)
            + "\\\"\\s*:\\s*(?:\\\"([^\\\"]*)\\\"|null)";
        var match = Regex.Match(json ?? "", pattern);
        return match.Success && match.Groups[1].Success ? match.Groups[1].Value : null;
    }

    private static string StatusLabel(string value)
    {
        if (value == "RUNNING") return "在线";
        if (value == "DEGRADED") return "部分异常";
        if (value == "FAILED") return "启动失败";
        if (value == "STOPPED") return "已停止";
        return "正在启动";
    }

    private static string ExperienceLabel(string value)
    {
        if (value == "ASSISTANT_READY") return "客服助手已就绪";
        if (value == "PDD_READY") return "PDD 已就绪";
        if (value == "STORE_SELECTED") return "已选择工作店铺";
        if (value == "BOUND") return "已绑定，待选店铺";
        if (value == "CONNECTED") return "已连接主机";
        if (value == "DEGRADED") return "需要检查";
        return "等待首次配置";
    }

    private static string PddLabel(string value)
    {
        if (value == "CUSTOMER_SERVICE_READY") return "客服在线";
        if (value == "PDD_LOGIN_SUCCESS" || value == "OPENING_CUSTOMER_SERVICE")
            return "正在进入客服";
        if (value == "WAITING_QR_SCAN" || value == "PDD_LOGIN_PAGE") return "等待扫码";
        if (value == "LOGIN_FAILED") return "登录异常";
        return "待检测";
    }

    private static string TrimTooltip(string value)
    {
        return value.Length <= 63 ? value : value.Substring(0, 63);
    }

    private static string FindEdge()
    {
        var candidates = new[]
        {
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Microsoft", "Edge", "Application", "msedge.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Microsoft", "Edge", "Application", "msedge.exe"),
        };
        foreach (var candidate in candidates)
        {
            if (File.Exists(candidate)) return candidate;
        }
        return null;
    }
}
