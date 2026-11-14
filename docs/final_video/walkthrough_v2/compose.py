"""Rebuild the silent application walkthrough. No slide or audio inputs are used.

python compose.py --ffmpeg C:/path/to/ffmpeg.exe --work PATH --output PATH
Work is docs/final_video or an extracted editable source folder with raw/ and assets/.
"""
from pathlib import Path
import argparse,json,subprocess,textwrap

def stamp(seconds,ass=False):
    ms=round(seconds*1000)
    if ass:return f'{ms//3600000}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000//10:02}'
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg',required=True,type=Path)
    p.add_argument('--work',type=Path,default=Path(__file__).resolve().parent.parent)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();work=a.work.resolve();edit=work/'walkthrough_v2';target=a.output.resolve()
    spec=json.loads((edit/'timeline.json').read_text(encoding='utf-8'))
    if target.exists():raise FileExistsError(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    events=[{'seconds':0,'text':'Search for fashion using a photo'},*spec['events']]
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1440
PlayResY: 900
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Guide,Arial,24,&H00FFFFFF,&H00FFFFFF,&H005E3810,&H005E3810,-1,0,0,0,100,100,0,0,1,0,0,2,30,30,22,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[];srt=[]
    for i,event in enumerate(events):
        end=events[i+1]['seconds'] if i+1<len(events) else spec['duration_seconds']
        text=event['text'].replace('{','').replace('}','').replace('\\','')
        lines.append(f"Dialogue: 0,{stamp(event['seconds'],True)},{stamp(end,True)},Guide,,0,0,0,,{text}")
        srt.append(f"{i+1}\n{stamp(event['seconds'])} --> {stamp(end)}\n"+'\n'.join(textwrap.wrap(text,75)))
    (edit/'captions.ass').write_text(header+'\n'.join(lines)+'\n',encoding='utf-8')
    (edit/'captions.srt').write_text('\n\n'.join(srt)+'\n',encoding='utf-8')
    # Repaint the guidance bars after capture so modal backdrops cannot blur them.
    # Arial is used from the local Windows installation, not redistributed.
    font='C\\:/Windows/Fonts/arialbd.ttf'
    filters=(f"[0:v]drawbox=x=0:y=0:w=iw:h=65:color=white:t=fill,"
       f"drawbox=x=0:y=824:w=iw:h=76:color=0x10385e:t=fill,"
       f"drawtext=fontfile='{font}':text='LibaasLens':x=94:y=20:fontsize=22:fontcolor=0x123a61,"
       f"drawtext=fontfile='{font}':text='How to use the application':x=w-tw-30:y=24:fontsize=17:fontcolor=0x123a61[screen];"
       "[1:v]scale=-1:55[logo];[screen][logo]overlay=30:5,"
       "subtitles=walkthrough_v2/captions.ass,scale=1728:1080:flags=lanczos,"
       "pad=1920:1080:96:0:color=white,setsar=1,fps=30[v]")
    command=[str(a.ffmpeg.resolve()),'-hide_banner','-loglevel','error','-n','-i',str(work/'raw/demo_walkthrough_v2.webm'),'-i',str(work/'assets/university_logo.png'),'-filter_complex',filters,'-map','[v]','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart','-metadata','title=LibaasLens - Application Walkthrough','-metadata','artist=Nasser Yousef; Noor Yousef; Naeem Basalma','-metadata','comment=Silent real-application walkthrough; no presentation slides. Editing pace is not a response-time benchmark.',str(target)]
    result=subprocess.run(command,cwd=work,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr[-6000:])
    print(target)

if __name__=='__main__':main()
