"""Assemble approved local delivery files; never delete or overwrite different files."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,zipfile,html
from tools.verify_delivery import sha256,verify

ROOT=Path(__file__).resolve().parent.parent
RUNTIME_NAME='Graduation_AI_Runtime_rc9_v1.zip'
RUNTIME_SHA='dd713d933cb3395e754ce607ef33bfd0fabdc7105c92cc4d846b4c4075975f0c'
REPO='https://github.com/nasserco09/LibaasLens'

def copy_checked(source,target):
    source=Path(source);target=Path(target)
    if not source.is_file():raise FileNotFoundError(source)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if not target.is_file() or sha256(source)!=sha256(target):raise FileExistsError(target)
    else:shutil.copyfile(source,target)
    if sha256(source)!=sha256(target):raise ValueError('Copy hash mismatch: '+str(target))

def payload(root):
    return [{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha256(p)} for p in sorted(root.rglob('*')) if p.is_file() and p.name not in {'DELIVERY_MANIFEST.json','SHA256SUMS.txt'}]

def metadata(files,commit,profile,omitted=None):
    return {'schema_version':1,'prepared_date':'2026-11-14','project':'LibaasLens | عدسة لباس','academic_title':'Visual Fashion Product Search Using Interactive Segmentation','team':['Nasser Yousef','Noor Yousef','Naeem Basalma'],'supervisor':'Dr. Ayman Alsabri','repository':REPO,'source_commit':commit,'source_tag':'submission-2026-v1','application_reference':'v1.2.0-rc.9','profile':profile,'omitted':omitted or [],'files':files,'integrity_scope':'SHA-256 detects file changes; this manifest is not a digital signature or legal registration.','formal_signatures':'Not generated; obtain genuine university approvals.'}

def write_manifest(root,record):
    (root/'DELIVERY_MANIFEST.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (root/'SHA256SUMS.txt').write_text('\n'.join(f"{p['sha256']}  {p['path']}" for p in record['files'])+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--materials-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--light-zip',type=Path,required=True)
    a=p.parse_args();materials=a.materials_dir.resolve();out=a.output.resolve();light=a.light_zip.resolve()
    if out==ROOT or out.is_relative_to(ROOT):raise ValueError('Keep the delivery folder outside the source checkout')
    if light.exists():raise FileExistsError(light)
    out.mkdir(parents=True,exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    forbidden=[n for n in tracked if n and (n.lower().endswith(('.db','.db-wal','.db-shm','.safetensors')) or n.startswith(('models/','.venv/','data/demo_store/')))]
    if forbidden:raise ValueError('Personal/heavy runtime files are tracked: '+str(forbidden))
    groups={
      '01_Report':['AI_Visual_Product_Search_Submission_2026.pdf','AI_Visual_Product_Search_LaTeX_Submission_2026.zip'],
      '02_Presentation':['Visual_Fashion_Search_Defense_2026_v3.pptx','Visual_Fashion_Search_Defense_2026_v3.pdf'],
      '03_Poster':['Visual_Fashion_Search_Poster_250x140cm.pdf','Visual_Fashion_Search_Poster_250x140cm_Editable.svg','Visual_Fashion_Search_Poster_Editable_Source.zip'],
      '04_Video':['Visual_Fashion_Search_Project_Video_EN_v1.mp4','Visual_Fashion_Search_Video_Editable_Source_v1.zip'],
      '07_Team_Study':['Visual_Fashion_Search_Defense_Study_Guide_AR_v1.pdf']}
    for folder,names in groups.items():
        for name in names:copy_checked(materials/name,out/folder/name)
    copy_checked(ROOT/'docs/final_video/captions.srt',out/'04_Video/captions.srt')
    runtime=ROOT/'output/runtime'/RUNTIME_NAME
    if sha256(runtime)!=RUNTIME_SHA:raise ValueError('Runtime archive differs from the verified publication')
    copy_checked(runtime,out/'06_Runtime'/RUNTIME_NAME)
    copy_checked(ROOT/'output/runtime/runtime_manifest.json',out/'06_Runtime/runtime_manifest.json')
    copy_checked(ROOT/'RUNTIME_README_AR.md',out/'06_Runtime/RUNTIME_README_AR.md')
    (out/'06_Runtime/DOWNLOAD_LINK.txt').write_text(REPO+'/releases/tag/runtime-rc9-v1\nThe ZIP name inside this folder predates the branding. Its bytes and published checksum are unchanged.\n',encoding='utf-8')
    for name in ['AUTHORS.md','LICENSE','COPYRIGHT_AR.md','CITATION.cff','THIRD_PARTY_NOTICES.md']:
        copy_checked(ROOT/name,out/'08_Rights'/name)
    copy_checked(ROOT/'runtime/THIRD_PARTY_NOTICES.md',out/'08_Rights/runtime/THIRD_PARTY_NOTICES.md')
    copy_checked(ROOT/'docs/submission/TEAM_ACCEPTANCE_20261114.json',out/'08_Rights/TEAM_ACCEPTANCE_20261114.json')
    copy_checked(ROOT/'docs/final_presentation/DELIVERY.json',out/'08_Rights/PRESENTATION_VERIFICATION.json')
    copy_checked(ROOT/'docs/final_video/DELIVERY.json',out/'08_Rights/VIDEO_VERIFICATION.json')
    for sub in ['runtime/licenses','frontend/assets/vendor/fonts','frontend/assets/vendor/fontawesome']:
        for file in (ROOT/sub).rglob('*'):
            if file.is_file() and (file.name.endswith('-OFL.txt') or file.name=='LICENSE.txt' or sub=='runtime/licenses'):
                copy_checked(file,out/'08_Rights'/sub/file.relative_to(ROOT/sub))
    source=out/'05_Project_Source/LibaasLens_Source_submission-2026-v1.zip';source.parent.mkdir(exist_ok=True)
    if source.exists():raise FileExistsError(source)
    subprocess.run(['git','archive','--format=zip','--prefix=LibaasLens/','--output='+str(source),'HEAD'],cwd=ROOT,check=True)
    (source.parent/'SOURCE_COMMIT.txt').write_text(commit+'\n'+REPO+'/tree/'+commit+'\nTag: submission-2026-v1\n',encoding='utf-8')
    with zipfile.ZipFile(source) as z:
        if z.testzip():raise ValueError('Source archive failed CRC')
        assert 'LibaasLens/LICENSE' in z.namelist()
    copy_checked(ROOT/'tools/verify_delivery.py',out/'verify_delivery.py')
    intro=f'''# ابدأ هنا\n\nLibaasLens | عدسة لباس\n\nالفريق: Nasser Yousef / Noor Yousef / Naeem Basalma. المشرف: Dr. Ayman Alsabri.\n\nافتح START_HERE_AR.html لفهرس الملفات. وثيقة التسليم في 01_Report، والعرض المعتمد في 02_Presentation، والبوستر في 03_Poster، والفيديو في 04_Video. مصادر التعديل بجانب كل مادة. دليل الفريق في 07_Team_Study.\n\nنسخة الكود مأخوذة من commit {commit} وتاق submission-2026-v1. حزمة التشغيل الكاملة في 06_Runtime، وبصمتها الأصلية {RUNTIME_SHA}. فكها إلى مجلد جديد واتبع RUNTIME_README_AR.md؛ لا تنقل ملفاتها فوق مشروعك أو قاعدة بياناتك.\n\nالاسم المختصر جديد؛ العناوين الأكاديمية والملفات المعتمدة لم تُعاد صياغتها. العرض والفيديو والموقع معتمدة من الفريق. التوقيعات والختم الحقيقي تؤخذ من أصحابها. البروشور خارج نطاق هذا التجميع بطلب الفريق.\n\nالحقوق والنسبة في 08_Rights؛ حقوق الموارد الخارجية مستقلة. البصمات وسجل Git وسيلة تتبع وسلامة ملفات وليست تسجيلًا قانونيًا أو ضمانًا لمنع النسخ.\n\nللتحقق شغّل python -B verify_delivery.py من هذا المجلد أو مرّر مساره. يحتاج Python فقط ولا يشغل النماذج.\n\nإن وجدت LIGHT_PACKAGE_NOTICE_AR.txt فهذه النسخة الخفيفة، ولا تحتوي أرشيف التشغيل الكبير؛ راجع رابط التنزيل المذكور فيها.\n'''
    (out/'START_HERE_AR.md').write_text(intro,encoding='utf-8')
    listed=[(folder,list((out/folder).glob('*'))) for folder in [*groups.keys(),'05_Project_Source','06_Runtime','08_Rights']]
    blocks=[]
    for folder,items in sorted(listed):
        links=''.join(f'<li><a href="{html.escape(f.relative_to(out).as_posix())}">{html.escape(f.name)}</a></li>' for f in items if f.is_file())
        blocks.append(f'<section><h2>{folder}</h2><ul>{links}</ul></section>')
    page='''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>LibaasLens ملفات التسليم</title><style>body{font:18px/1.8 Arial;background:#f2f6fb;color:#142b4b;max-width:1100px;margin:auto;padding:35px}h1{font-size:38px}section{background:white;padding:18px 25px;margin:18px 0;border:1px solid #d3e0ef;border-radius:12px}h2{direction:ltr;text-align:right;font-size:23px}a{color:#165da2;overflow-wrap:anywhere}li{margin:7px 0}p{max-width:950px}footer{font-size:14px}</style><h1>LibaasLens | عدسة لباس</h1><p><strong>مجمع تسليم مشروع التخرج 2026</strong><br>Nasser Yousef / Noor Yousef / Naeem Basalma<br>Supervised by Dr. Ayman Alsabri</p><p>العرض والفيديو والموقع معتمدة من الفريق. ملفات القراءة والتشغيل ومصادر التعديل منظمة أدناه. راجع START_HERE_AR.md للتعليمات و08_Rights للنسبة والحقوق. التوقيعات والختم الحقيقي تؤخذ من أصحابها.</p>'''+''.join(blocks)+f'<footer>Source commit: <bdi>{commit}</bdi><br><a href="{REPO}">المستودع</a> · <a href="DELIVERY_MANIFEST.json">بيان التسليم</a> · <a href="SHA256SUMS.txt">البصمات</a><p>النسخة الخفيفة تستثني أرشيف التشغيل الكبير فقط، وتحتوي LIGHT_PACKAGE_NOTICE_AR.txt.</p></footer></html>'
    (out/'START_HERE_AR.html').write_text(page,encoding='utf-8')
    full_files=payload(out);full=metadata(full_files,commit,'complete-local-handover');write_manifest(out,full)
    checked=verify(out)
    if not checked['passed']:raise ValueError(checked)
    omitted=[f for f in full_files if f['path']=='06_Runtime/'+RUNTIME_NAME]
    light_files=[dict(f) for f in full_files if f not in omitted]
    light_html=page.replace('href="06_Runtime/'+RUNTIME_NAME+'"','href="'+REPO+'/releases/tag/runtime-rc9-v1"').encode('utf-8')
    html_record=next(f for f in light_files if f['path']=='START_HERE_AR.html')
    html_record.update(bytes=len(light_html),sha256=hashlib.sha256(light_html).hexdigest())
    notice=('هذه نسخة التسليم الخفيفة. كل المواد ومصادرها موجودة، باستثناء ZIP التشغيل الكبير فقط.\nالأرشيف موجود في المجلد الكامل على سطح المكتب، ويمكن تنزيله أيضًا من:\n'+REPO+'/releases/tag/runtime-rc9-v1\nالبصمة الأصلية: '+RUNTIME_SHA+'\n').encode('utf-8')
    light_files.append({'path':'LIGHT_PACKAGE_NOTICE_AR.txt','bytes':len(notice),'sha256':hashlib.sha256(notice).hexdigest()})
    light_files.sort(key=lambda f:f['path'])
    light_record=metadata(light_files,commit,'materials-and-source-excluding-runtime-archive',[{**omitted[0],'download':REPO+'/releases/tag/runtime-rc9-v1'}])
    light.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(light,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in light_files:
            if file['path']=='START_HERE_AR.html':z.writestr(file['path'],light_html)
            elif file['path']=='LIGHT_PACKAGE_NOTICE_AR.txt':z.writestr(file['path'],notice)
            else:z.write(out/file['path'],file['path'])
        z.writestr('DELIVERY_MANIFEST.json',json.dumps(light_record,ensure_ascii=False,indent=2)+'\n')
        z.writestr('SHA256SUMS.txt','\n'.join(f"{f['sha256']}  {f['path']}" for f in light_files)+'\n')
    with zipfile.ZipFile(light) as z:
        if z.testzip():raise ValueError('Light archive failed CRC')
        for file in light_files:
            if hashlib.sha256(z.read(file['path'])).hexdigest()!=file['sha256']:raise ValueError('Light payload differs')
    print(json.dumps({'complete_folder':str(out),'files':len(full_files),'total_bytes':sum(f['bytes'] for f in full_files),'source_commit':commit,'light_zip':str(light),'light_bytes':light.stat().st_size,'light_sha256':sha256(light),'full_verification':checked},ensure_ascii=True,indent=2))

if __name__=='__main__':main()
