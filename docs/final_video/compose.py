"""Rebuild the English narrated video from real capture clips and editable text.

Usage: python compose.py --work PATH --ffmpeg PATH
Work contains assets/, audio/, raw/timings.json and raw/*.webm.
"""
import argparse,json,subprocess,textwrap,wave,shutil,re,math
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--work',type=Path,required=True)
parser.add_argument('--ffmpeg',type=Path,required=True)
args=parser.parse_args()
work=args.work.resolve(); ffmpeg=str(args.ffmpeg.resolve())
spec=json.loads((Path(__file__).parent/'script.json').read_text())
timings=json.loads((work/'raw/timings.json').read_text())
(work/'render').mkdir(exist_ok=True)
shutil.copyfile('C:/Windows/Fonts/arialbd.ttf',work/'render/title-font.ttf')
timeline=[];clock=0;segments=[]

def call(arguments):
    p=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y',*arguments],cwd=work/'render',capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr[-6000:])

for scene in spec['scenes']:
    audio=[]; scene_caps=[]; offset=.65
    for i,sentence in enumerate(scene['sentences']):
        with wave.open(str(work/'audio'/f"{scene['id']}_{i:02}.wav"),'rb') as wav:
            params=wav.getparams(); content=wav.readframes(wav.getnframes()); duration=wav.getnframes()/wav.getframerate()
        if not audio:audio.append(bytes(int(.65*params.framerate)*params.sampwidth*params.nchannels))
        audio.append(content)
        words=sentence.split(); groups=[];pending=''
        for clause in re.split(r'(?<=[,;])\s+',sentence):
            if pending and len((pending+' '+clause).split())>16:groups.append(pending);pending=''
            parts=clause.split();count=math.ceil(len(parts)/16);size=math.ceil(len(parts)/count)
            if count>1:
                if pending:groups.append(pending);pending=''
                groups.extend(' '.join(parts[n:n+size]) for n in range(0,len(parts),size))
            else:pending=(pending+' '+clause).strip()
        if pending:groups.append(pending)
        consumed=0
        for group in groups:
            share=len(group.split())/len(words)
            caption=group
            for spoken,written in [('Sam two point one','SAM2.1'),('Sig lip two','SigLIP2'),('Fast A P I','FastAPI'),('F A I S S','FAISS'),('C P U','CPU')]:caption=caption.replace(spoken,written)
            scene_caps.append({'start':clock+offset+duration*consumed,'end':clock+offset+duration*(consumed+share),'text':caption})
            consumed+=share
        audio.append(bytes(int(.32*params.framerate)*params.sampwidth*params.nchannels));offset+=duration+.32
    audio.append(bytes(int(.8*params.framerate)*params.sampwidth*params.nchannels))
    length=offset+.8
    if 'clip' in scene:length=max(length,timings[scene['clip']+'_end']-timings[scene['clip']+'_start'])
    scene_audio=work/'render'/f"{scene['id']}.wav"
    with wave.open(str(scene_audio),'wb') as wav:
        wav.setparams(params);wav.writeframes(b''.join(audio))
    inputs=['-loop','1','-i',str(work/'assets/background.jpg')]
    if 'slide' in scene:inputs+=['-loop','1','-i',str(work/'assets'/f"slide_{scene['slide']:02}.png")]
    else:
        source_video=Path(timings['video'])
        if not source_video.is_absolute():source_video=work/source_video
        inputs+=['-ss',str(timings[scene['clip']+'_start']),'-t',str(timings[scene['clip']+'_end']-timings[scene['clip']+'_start']),'-i',str(source_video)]
    inputs+=['-loop','1','-i',str(work/'assets/university_logo.png'),'-i',str(scene_audio)]
    title_file=work/'render'/f"{scene['id']}.txt";title_file.write_text(scene['title'],encoding='utf-8')
    pacing=''
    note=''
    if 'clip' in scene:
        factor=length/(timings[scene['clip']+'_end']-timings[scene['clip']+'_start'])
        pacing=f'setpts={factor}*(PTS-STARTPTS),'
        note=",drawtext=fontfile=title-font.ttf:text='Demo playback paced for narration':fontcolor=0x587799:fontsize=22:x=1250:y=34"
    filters=f"[0:v]scale=1920:1080,setsar=1[bg];[1:v]{pacing}scale=1536:864,setsar=1,fps=30,tpad=stop_mode=clone:stop_duration={length}[content];[2:v]scale=-1:68[logo];[bg][content]overlay=192:78[frame];[frame][logo]overlay=1788:8,drawtext=fontfile=title-font.ttf:textfile={title_file.name}:fontcolor=0x051E51:fontsize=34:x=192:y=25{note},fade=t=in:st=0:d=0.3:color=white,fade=t=out:st={length-.3}:d=0.3:color=white[v];[3:a]apad,atrim=duration={length}[a]"
    target=work/'render'/f"{scene['id']}.mp4"
    call([*inputs,'-filter_complex',filters,'-map','[v]','-map','[a]','-t',str(length),'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ar','48000',str(target)])
    segments.append(target);timeline.extend(scene_caps);scene['start_seconds']=round(clock,3);scene['duration_seconds']=round(length,3);clock+=length
    print('Composed',scene['id'],round(length,2),flush=True)

def timestamp(t,sep=','):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}{sep}{ms%1000:03}'
srt='\n\n'.join(f"{i}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n"+'\n'.join(textwrap.wrap(c['text'],68)) for i,c in enumerate(timeline,1))+'\n'
(work/'render/captions.srt').write_text(srt,encoding='utf-8')
(work/'render/concat.txt').write_text('\n'.join("file '"+p.name+"'" for p in segments),encoding='utf-8')
call(['-f','concat','-safe','0','-i','concat.txt','-c','copy','joined.mp4'])
target=work/'Visual_Fashion_Search_Project_Video_EN_v1.mp4'
call(['-i','joined.mp4','-vf',"subtitles=captions.srt:force_style='FontName=Arial,FontSize=14,PrimaryColour=&HFFFFFF,OutlineColour=&H512005,BorderStyle=3,Outline=4,Shadow=0,MarginV=12,Alignment=2'",'-af','loudnorm=I=-16:TP=-1.5:LRA=7','-c:v','libx264','-crf','20','-preset','veryfast','-c:a','aac','-b:a','160k','-movflags','+faststart',str(target)])
call(['-i','joined.mp4','-vn','-ar','48000','-c:a','pcm_s16le',str(work/'narration.wav')])
shutil.copyfile(work/'render/captions.srt',work/'captions.srt')
(work/'timeline.json').write_text(json.dumps(spec,indent=2)+'\n')
print('FINAL',target,'seconds',clock,flush=True)
