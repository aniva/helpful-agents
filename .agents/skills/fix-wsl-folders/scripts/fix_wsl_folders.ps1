# Fix Antigravity Folder URIs (WSL & Windows Drive Paths)
$projectDir = "C:\Users\me\.gemini\config\projects"
$files = Get-ChildItem -Path $projectDir -Filter "*.json" -ErrorAction SilentlyContinue

$count = 0
foreach ($file in $files) {
    $text = Get-Content $file.FullName -Raw
    $modified = $false

    # 1. Fix malformed WSL URIs: file:///%5C%5Cwsl.localhost... or file:///\\wsl.localhost... or file:///Ubuntu/
    if ($text -match 'file:///(%5C%5C|\\\\)?wsl\.localhost') {
        $text = [regex]::Replace($text, 'file:///(%5C%5C|\\\\)?wsl\.localhost[\\/]([^"]+)', {
            param($m)
            $sub = $m.Groups[2].Value -replace '%5C', '/' -replace '\\', '/'
            return "file://wsl.localhost/$sub"
        })
        $modified = $true
    }
    if ($text -match 'file:///Ubuntu/') {
        $text = $text -replace 'file:///Ubuntu/', 'file://wsl.localhost/Ubuntu/'
        $modified = $true
    }

    # 2. Fix malformed Windows Drive URIs: file:///c%3A%5C or file:///d%3A%5CUsers... (%5C -> /, %3A -> :)
    if ($text -match 'file:///[a-zA-Z](%3A|:)(%5C|/|\\)') {
        $text = [regex]::Replace($text, 'file:///([a-zA-Z])(%3A|:)([^"]*)', {
            param($m)
            $drive = $m.Groups[1].Value.ToLower()
            $path = $m.Groups[3].Value -replace '%5C', '/' -replace '\\', '/'
            return "file:///$drive`:$path"
        })
        $modified = $true
    }

    if ($modified) {
        Set-Content -Path $file.FullName -Value $text -Encoding UTF8
        Write-Host "Fixed Project Config: $($file.Name)"
        $count++
    }
}

# Fix AppData workspaceStorage & globalStorage
$appDataFiles = @(
    "$env:APPDATA\Antigravity IDE\User\globalStorage\storage.json",
    "$env:APPDATA\Antigravity\User\globalStorage\storage.json"
) + (Get-ChildItem -Path "$env:APPDATA\Antigravity*\User\workspaceStorage" -Recurse -Filter "workspace.json" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)

foreach ($f in $appDataFiles) {
    if (Test-Path $f) {
        $t = Get-Content $f -Raw
        $m = $false
        if ($t -match 'file:///Ubuntu/') {
            $t = $t -replace 'file:///Ubuntu/', 'file://wsl.localhost/Ubuntu/'
            $m = $true
        }
        if ($t -match 'file:///[a-zA-Z](%3A|:)(%5C|/|\\)') {
            $t = [regex]::Replace($t, 'file:///([a-zA-Z])(%3A|:)([^"]*)', {
                param($match)
                $drive = $match.Groups[1].Value.ToLower()
                $path = $match.Groups[3].Value -replace '%5C', '/' -replace '\\', '/'
                return "file:///$drive`:$path"
            })
            $m = $true
        }
        if ($m) {
            Set-Content -Path $f -Value $t -Encoding UTF8
            Write-Host "Fixed AppData Config: $f"
            $count++
        }
    }
}

if ($count -eq 0) {
    Write-Host "All Antigravity folder URIs are clean and valid!"
}
