# Build standard app-icon sizes from SDW's existing crest image.
# The artwork is scaled proportionally, never redrawn or retouched.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$iconsDirectory = Join-Path $PSScriptRoot '..\app\static\icons'
$sourceFile = Join-Path $PSScriptRoot '..\app\static\branding\sdw-logo.jpg'
[System.IO.Directory]::CreateDirectory($iconsDirectory) | Out-Null
$sourceImage = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $sourceFile).Path)
try {
    foreach ($variant in @(
        @{Size=180; Name='apple-touch-icon.png'; Padding=0},
        @{Size=192; Name='icon-192.png'; Padding=0},
        @{Size=512; Name='icon-512.png'; Padding=0},
        @{Size=512; Name='maskable-512.png'; Padding=0.15}
    )) {
        $size = $variant.Size
        $bitmap = New-Object System.Drawing.Bitmap($size,$size)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#142320'))
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $available = $size * (1 - 2 * $variant.Padding)
            $scale = [Math]::Min($available / $sourceImage.Width,$available / $sourceImage.Height)
            $width = [single]($sourceImage.Width * $scale)
            $height = [single]($sourceImage.Height * $scale)
            $rectangle = [System.Drawing.RectangleF]::new([single](($size-$width)/2),[single](($size-$height)/2),$width,$height)
            $graphics.DrawImage($sourceImage,$rectangle)
            $bitmap.Save((Join-Path $iconsDirectory $variant.Name),[System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $graphics.Dispose(); $bitmap.Dispose() }
    }
} finally { $sourceImage.Dispose() }
Write-Output 'SDW crest app icons generated (180, 192, 512 and maskable 512).'
