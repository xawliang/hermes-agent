Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$img = [System.Windows.Forms.Clipboard]::GetImage()
if ($img -ne $null) {
    $ms = New-Object System.IO.MemoryStream
    $img.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $ms.ToArray()
    $ms.Close()
    [System.Console]::OutputEncoding = [System.Text.Encoding]::ASCII
    Write-Host ([System.Convert]::ToBase64String($bytes))
    exit 0
}
exit 1
