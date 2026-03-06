Output docs/assets/demo-flow.gif

Require python3

Set Shell "bash"
Set FontFamily "SF Mono"
Set FontSize 22
Set Width 1600
Set Height 920
Set Theme "GitHub Dark"
Set Padding 24
Set Margin 0
Set BorderRadius 16
Set WindowBar Colorful
Set TypingSpeed 35ms
Set Framerate 30
Set PlaybackSpeed 1.0

Type "python3 -m duecheck.cli demo --out-dir ./demo"
Enter
Sleep 1.2s

Type "python3 -m duecheck.cli verify --out-dir ./demo --json"
Enter
Sleep 1.2s

Type "python3 -m duecheck.cli report --html --out-dir ./demo"
Enter
Sleep 1.5s
