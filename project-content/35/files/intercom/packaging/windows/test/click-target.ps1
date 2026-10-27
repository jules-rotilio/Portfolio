# A window that counts the clicks it receives and logs where the mouse is,
# every 100 ms, to check auto-click and drift without clicking anything else.
# It stays on top, puts the mouse over itself, and closes after -Seconds.
#   powershell -STA -File click-target.ps1 -Seconds 14 -Out $env:TEMP\click-target.txt
param([int]$Seconds = 14, [string]$Out = "$env:TEMP\click-target.txt")
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Intercom click target'
$form.TopMost = $true
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point(100, 100)
$form.Size = New-Object System.Drawing.Size(1200, 400)

$script:clicks = 0
$form.Add_MouseDown({ $script:clicks++ })
$log = New-Object System.Collections.Generic.List[string]
$start = Get-Date
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 100
$timer.Add_Tick({
    $t = ((Get-Date) - $start).TotalSeconds
    $x = [System.Windows.Forms.Cursor]::Position.X
    $log.Add(('{0} clicks={1} x={2}' -f [math]::Round($t, 1).ToString([cultureinfo]::InvariantCulture), $script:clicks, $x))
    if ($t -ge $Seconds) { $timer.Stop(); $form.Close() }
})
$form.Add_Shown({
    # The mouse goes over the window, near its left side: drift moves it right.
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(300, 300)
    $timer.Start()
})
[System.Windows.Forms.Application]::Run($form)
$log | Set-Content -Encoding UTF8 $Out
