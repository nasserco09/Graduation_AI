param([string]$OutputDirectory)
$videoSpecification = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'script.json') | ConvertFrom-Json
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$videoSpeaker = New-Object -ComObject SAPI.SpVoice
$videoSpeaker.Voice = @($videoSpeaker.GetVoices() | Where-Object { $_.GetDescription() -like '*David*' })[0]
$videoSpeaker.Rate = 0
$videoSpeaker.Volume = 100
foreach ($videoScene in $videoSpecification.scenes) {
    for ($videoSentenceIndex = 0; $videoSentenceIndex -lt $videoScene.sentences.Count; $videoSentenceIndex++) {
        $videoAudioFile = Join-Path $OutputDirectory ('{0}_{1:D2}.wav' -f $videoScene.id, $videoSentenceIndex)
        $videoStream = New-Object -ComObject SAPI.SpFileStream
        $videoFormat = New-Object -ComObject SAPI.SpAudioFormat
        $videoFormat.Type = 22
        $videoStream.Format = $videoFormat
        $videoStream.Open($videoAudioFile, 3, $false)
        $videoSpeaker.AudioOutputStream = $videoStream
        [void]$videoSpeaker.Speak($videoScene.sentences[$videoSentenceIndex])
        $videoStream.Close()
    }
    Write-Output ('Narrated ' + $videoScene.id)
}
