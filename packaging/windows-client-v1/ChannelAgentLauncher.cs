using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class ChannelAgentLauncher
{
    private static string QuoteArgument(string value)
    {
        if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0)
        {
            return value;
        }
        var output = new StringBuilder();
        output.Append('"');
        var backslashes = 0;
        foreach (var character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }
            if (character == '"')
            {
                output.Append('\\', backslashes * 2 + 1);
                output.Append('"');
                backslashes = 0;
                continue;
            }
            output.Append('\\', backslashes);
            backslashes = 0;
            output.Append(character);
        }
        output.Append('\\', backslashes * 2);
        output.Append('"');
        return output.ToString();
    }

    public static int Main(string[] args)
    {
        var home = AppDomain.CurrentDomain.BaseDirectory;
        var runtime = Path.Combine(home, "runtime", "python");
        var python = Path.Combine(runtime, "python.exe");
        var application = Path.Combine(home, "app", "channel-agent.pyz");
        if (!File.Exists(python) || !File.Exists(application))
        {
            Console.Error.WriteLine("Channel Agent 安装不完整，请重新安装。");
            return 4;
        }
        var arguments = new List<string> { QuoteArgument(application) };
        foreach (var argument in args)
        {
            arguments.Add(QuoteArgument(argument));
        }
        var start = new ProcessStartInfo
        {
            FileName = python,
            Arguments = string.Join(" ", arguments.ToArray()),
            WorkingDirectory = home,
            UseShellExecute = false,
        };
        start.EnvironmentVariables["PYTHONHOME"] = runtime;
        start.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        using (var process = Process.Start(start))
        {
            if (process == null)
            {
                return 4;
            }
            process.WaitForExit();
            return process.ExitCode;
        }
    }
}
