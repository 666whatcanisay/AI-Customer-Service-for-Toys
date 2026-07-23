@{
    # 留空时依次尝试仓库内 .venv 和系统 PATH。也可以填写绝对路径。
    RagPython = ''
    PlatformPython = ''
    NodeExecutable = ''
    OllamaExecutable = ''

    # Ollama 不可用且 11434 未被占用时，是否由启动脚本运行 `ollama serve`。
    AutoStartOllama = $true

    # 成功启动后是否打开客服页面。自动化测试可向启动脚本传入 -NoBrowser。
    OpenBrowser = $true

    # 首次加载本地嵌入模型可能较慢。
    StartupTimeoutSeconds = 180
}
