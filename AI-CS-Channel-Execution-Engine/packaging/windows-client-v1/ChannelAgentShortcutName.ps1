function ConvertFrom-ChannelAgentUnicodeCodePoints {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][int[]]$CodePoints)

    $builder = [System.Text.StringBuilder]::new()
    foreach ($codePoint in $CodePoints) {
        [void]$builder.Append([char]::ConvertFromUtf32($codePoint))
    }
    return $builder.ToString()
}

function Get-ChannelAgentShortcutName {
    [CmdletBinding()]
    param()

    $customerAssistant = ConvertFrom-ChannelAgentUnicodeCodePoints @(
        0x5BA2, # customer
        0x670D, # service
        0x52A9, # assist
        0x624B  # helper
    )
    return "AI-CS $customerAssistant.lnk"
}

function Get-ChannelAgentKnownMojibakeShortcutNames {
    [CmdletBinding()]
    param()

    $knownMojibake = ConvertFrom-ChannelAgentUnicodeCodePoints @(
        0x7039,
        0x3221,
        0x6E47,
        0x9354,
        0x2542,
        0x589C
    )
    return @("AI-CS $knownMojibake.lnk")
}
