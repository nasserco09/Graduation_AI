"""Editable 1:1 university research poster. Rebuild with ReportLab and Pillow.

The SVG retains live text and vector geometry; the PDF embeds its fonts.
Original screenshots and photographs are embedded without generated replacements.
"""
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
import base64
import hashlib
import json
import math
import mimetypes

from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.graphics.barcode.qr import QrCodeWidget

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'output/poster' if (ROOT/'app.py').is_file() else HERE/'output'
OUT.mkdir(parents=True,exist_ok=True)
ASSETS=HERE/'assets'
CONTENT=json.loads((HERE/'content.json').read_text(encoding='utf-8'))
W,H=2500,1400
MM=72/25.4
STEM='Visual_Fashion_Search_Poster_250x140cm'
NAVY='#073C68'
BLUE='#066BB5'
CYAN='#069DCD'
INK='#173A55'
MUTED='#506B80'
PALE='#EFF7FC'
BORDER='#C5DFEF'
WHITE='#FFFFFF'

FONTDIR=Path(CONTENT.get('font_directory','C:/Windows/Fonts'))
for name,file in [('Poster','arial.ttf'),('Poster-Bold','arialbd.ttf'),('Poster-Italic','ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONTDIR/file)))


class Drawing:
    def __init__(self):
        self.pdf=canvas.Canvas(str(OUT/(STEM+'.pdf')),pagesize=(W*MM,H*MM),pageCompression=1,pdfVersion=(1,4),initialFontName='Poster')
        self.pdf.setTitle('Visual Fashion Product Search - Graduation Project Poster')
        self.pdf.setAuthor('Nasser Yousef; Noor Yousef; Naeem Basalma')
        self.pdf.setSubject('2500 x 1400 mm research poster; SigLIP2, SAM2.1, FAISS and FastAPI')
        self.pdf.setCreator('Graduation_AI editable poster builder')
        self.pdf.setTrimBox((0,0,W*MM,H*MM))
        self.svg=[f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
                  '<title>Visual Fashion Product Search - Graduation Project</title>',
                  '<desc>Editable 2500 by 1400 millimetre poster. Text, charts, shapes and QR code are vectors.</desc>']
        self.placements=[]
        self.texts=[]

    def rect(self,x,y,w,h,fill=WHITE,stroke=None,r=0,lw=.8):
        c=self.pdf
        c.setFillColor(HexColor(fill or WHITE))
        c.setStrokeColor(HexColor(stroke or fill or WHITE))
        c.setLineWidth(lw*MM)
        if r:c.roundRect(x*MM,(H-y-h)*MM,w*MM,h*MM,r*MM,fill=bool(fill),stroke=bool(stroke))
        else:c.rect(x*MM,(H-y-h)*MM,w*MM,h*MM,fill=bool(fill),stroke=bool(stroke))
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{lw}"/>')

    def line(self,x1,y1,x2,y2,color=BLUE,lw=1):
        c=self.pdf;c.setStrokeColor(HexColor(color));c.setLineWidth(lw*MM)
        c.line(x1*MM,(H-y1)*MM,x2*MM,(H-y2)*MM)
        self.svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{lw}"/>')

    def path(self,commands,fill=None,stroke=None,lw=1):
        p=self.pdf.beginPath();s=[]
        for cmd,*v in commands:
            if cmd=='M':p.moveTo(v[0]*MM,(H-v[1])*MM)
            elif cmd=='L':p.lineTo(v[0]*MM,(H-v[1])*MM)
            elif cmd=='C':p.curveTo(v[0]*MM,(H-v[1])*MM,v[2]*MM,(H-v[3])*MM,v[4]*MM,(H-v[5])*MM)
            elif cmd=='Z':p.close()
            s.append(cmd+' '.join(str(round(a,3)) for a in v))
        self.pdf.setFillColor(HexColor(fill or WHITE));self.pdf.setStrokeColor(HexColor(stroke or WHITE));self.pdf.setLineWidth(lw*MM)
        self.pdf.drawPath(p,fill=bool(fill),stroke=bool(stroke))
        self.svg.append(f'<path d="{" ".join(s)}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{lw}"/>')

    def circle(self,x,y,r,fill=BLUE,stroke=None,lw=1):
        c=self.pdf;c.setFillColor(HexColor(fill or WHITE));c.setStrokeColor(HexColor(stroke or fill or WHITE));c.setLineWidth(lw*MM)
        c.circle(x*MM,(H-y)*MM,r*MM,fill=bool(fill),stroke=bool(stroke))
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{lw}"/>')

    def text(self,value,x,y,size=16,bold=False,color=INK,anchor='start',italic=False):
        font='Poster-Bold' if bold else 'Poster-Italic' if italic else 'Poster'
        width=pdfmetrics.stringWidth(value,font,size)
        left=x-width/2 if anchor=='middle' else x-width if anchor=='end' else x
        baseline=y+pdfmetrics.getAscent(font)*size/1000
        assert left>=-0.1 and left+width<=W+.1,(value,left,width)
        assert y>=0 and baseline<=H,(value,y)
        self.pdf.setFont(font,size*MM);self.pdf.setFillColor(HexColor(color))
        self.pdf.drawString(left*MM,(H-baseline)*MM,value)
        self.svg.append(f'<text x="{x}" y="{baseline:.4f}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{"700" if bold else "400"}" font-style="{"italic" if italic else "normal"}" text-anchor="{anchor}" fill="{color}">{escape(value)}</text>')
        self.texts.append({'text':value,'x':left,'y':y,'width':width,'size_mm':size})
        return y+size*1.15

    def para(self,value,x,y,width,size=16,leading=22,bold=False,color=INK,max_bottom=None):
        font='Poster-Bold' if bold else 'Poster'
        lines=[]
        for paragraph in value.split('\n'):
            line=''
            for word in paragraph.split():
                trial=(line+' '+word).strip()
                if pdfmetrics.stringWidth(trial,font,size)>width and line:
                    lines.append(line);line=word
                else:line=trial
            lines.append(line)
        for value in lines:
            self.text(value,x,y,size,bold,color);y+=leading
        if max_bottom is not None:assert y<=max_bottom,('Text exceeds card',value,y,max_bottom)
        return y

    def image(self,name,x,y,w,h):
        path=ASSETS/name
        im=Image.open(path)
        iw,ih=im.size
        scale=min(w/iw,h/ih)
        rw,rh=iw*scale,ih*scale
        rx,ry=x+(w-rw)/2,y+(h-rh)/2
        self.pdf.drawImage(str(path),rx*MM,(H-ry-rh)*MM,rw*MM,rh*MM,mask='auto')
        mime=mimetypes.guess_type(path.name)[0] or 'image/png'
        data=base64.b64encode(path.read_bytes()).decode('ascii')
        self.svg.append(f'<image x="{rx:.4f}" y="{ry:.4f}" width="{rw:.4f}" height="{rh:.4f}" xlink:href="data:{mime};base64,{data}"/>')
        self.placements.append({'file':name,'pixel_dimensions':[iw,ih],'x_mm':rx,'y_mm':ry,'width_mm':rw,'height_mm':rh,'effective_dpi':round(iw/(rw/25.4),1)})

    def arrow(self,x1,y,x2):
        self.line(x1,y,x2-6,y,BLUE,1.7)
        self.path([('M',x2-9,y-5),('L',x2,y),('L',x2-9,y+5)],stroke=BLUE,lw=1.7)

    def panel(self,x,y,w,h,title,number=None):
        self.rect(x,y+3,w,h,'#E4EFF6',r=13)
        self.rect(x,y,w,h,WHITE,BORDER,13,1)
        self.rect(x+20,y+23,5,26,BLUE,r=2)
        self.text(title,x+39,y+20,24,True,NAVY)
        self.line(x+25,y+65,x+w-25,y+65,BORDER,.7)

    def bullet(self,value,x,y,width,size=16,leading=22):
        self.circle(x+5,y+8,4,BLUE)
        return self.para(value,x+20,y,width-20,size,leading)+11

    def qr(self,url,x,y,size):
        code=QrCodeWidget(url,barLevel='H')
        code.qr.make()
        matrix=code.qr.modules
        quiet=4
        module=size/(len(matrix)+2*quiet)
        self.rect(x,y,size,size,WHITE)
        self.svg.append('<g id="github-qr" aria-label="'+escape(url)+'">')
        for row,line in enumerate(matrix):
            start=None
            for col,black in enumerate(line+[False]):
                if black and start is None:start=col
                elif not black and start is not None:
                    self.rect(x+(quiet+start)*module,y+(quiet+row)*module,(col-start)*module,module,'#000000')
                    start=None
        self.svg.append('</g>')
        self.pdf.linkURL(url,(x*MM,(H-y-size)*MM,(x+size)*MM,(H-y)*MM),relative=0,thickness=0)
        return {'target':url,'x_mm':x,'y_mm':y,'size_mm':size,'matrix_modules':len(matrix),'quiet_zone_modules':quiet}

    def finish(self):
        self.pdf.showPage();self.pdf.save()
        self.svg.append('</svg>')
        (OUT/(STEM+'_Editable.svg')).write_text('\n'.join(self.svg)+'\n',encoding='utf-8')


def main():
    d=Drawing()
    d.rect(0,0,W,H,'#F5FAFD')
    # Quiet geometric university-blue corners and a full-width light header.
    d.path([('M',0,0),('L',360,0),('L',0,225),('Z',)],fill=NAVY)
    d.path([('M',0,0),('L',285,0),('L',0,175),('Z',)],fill=BLUE)
    d.path([('M',0,0),('L',170,0),('L',0,105),('Z',)],fill=CYAN)
    d.rect(285,28,1400,95,WHITE,r=15)
    d.image('logo_academic.png',310,20,130,155)
    d.text('INTERNATIONAL UNIVERSITY',465,40,25,True,NAVY)
    d.text('OF TECHNOLOGY TWINTECH',465,72,25,True,NAVY)
    d.text('GRADUATION PROJECT  |  2026',465,110,15,True,BLUE)
    d.text('Visual Fashion Product Search',295,165,65,True,NAVY)
    d.text('Using Interactive Segmentation',300,242,28,False,BLUE)
    d.text('Find what you love. Visually.',1175,250,18,False,MUTED)

    d.rect(1735,35,720,238,WHITE,BORDER,15,1)
    d.text('PROJECT TEAM',1767,58,18,True,BLUE)
    for i,name in enumerate(CONTENT['team']):d.text(name,1767,95+i*39,25,True,NAVY)
    d.line(2155,66,2155,240,BORDER,1)
    d.text('SUPERVISED BY',2185,94,17,True,BLUE)
    d.para(CONTENT['supervisor'],2185,137,235,25,34,True,NAVY,max_bottom=235)

    # Left column: motivation, objectives, exact implementation technologies.
    d.panel(45,310,585,315,'Project overview')
    y=d.para(CONTENT['overview'],75,395,525,17,24,max_bottom=505)
    d.text('The problem it solves',75,y+11,20,True,BLUE)
    d.para(CONTENT['problem'],75,y+46,525,16.5,23,max_bottom=610)
    d.panel(45,650,585,280,'Project objectives')
    y=730
    for line in CONTENT['objectives']:y=d.bullet(line,75,y,525,16.5,23)
    assert y<925,('Objectives overflow',y)
    d.panel(45,955,585,355,'Technologies used')
    tech=CONTENT['technologies']
    for i,(title,detail) in enumerate(tech):
        col,row=i%2,i//2
        x,y=75+col*275,1045+row*82
        d.rect(x,y,250,69,PALE,r=8)
        d.text(title,x+14,y+9,20,True,BLUE)
        d.para(detail,x+14,y+38,225,13,16,max_bottom=y+69)

    # Centre column: actual query and five deterministic pipeline stages.
    d.panel(660,310,1045,330,'How the system works')
    card_y,card_w,gap=395,183,17
    for i,step in enumerate(CONTENT['pipeline']):
        x=685+i*(card_w+gap)
        d.rect(x,card_y,card_w,220,PALE,BORDER,9,.7)
        d.circle(x+23,card_y+24,12,BLUE)
        d.text(str(i+1),x+23,card_y+15,17,True,WHITE,'middle')
        d.para(step['title'],x+45,card_y+14,130,17,21,True,NAVY,max_bottom=card_y+62)
        if i==0:d.image('composite_query.jpg',x+13,card_y+66,157,84)
        elif i==1:d.image('selected_garment.png',x+50,card_y+61,83,105)
        elif i==2:
            for b,height in enumerate([30,60,43,78,54,88,36]):
                d.rect(x+27+b*19,card_y+157-height,12,height,BLUE if b%2 else CYAN,r=2)
        elif i==3:
            for row in [0,1,2]:
                d.rect(x+42,card_y+75+row*24,100,21,BLUE if row!=1 else CYAN,r=9)
                d.line(x+49,card_y+78+row*24,x+135,card_y+78+row*24,'#80BFE8',1)
        else:
            for col in range(3):
                d.rect(x+12+col*54,card_y+68,49,96,WHITE,BORDER,5,.5)
                d.image(f'result_{col+1}.jpg',x+15+col*54,card_y+73,43,80)
        d.para(step['detail'],x+12,card_y+177,card_w-24,13,17,max_bottom=card_y+220)
        if i<4:d.arrow(x+card_w+2,card_y+125,x+card_w+gap-2)

    # Original, unmodified, observed browser screens.
    d.panel(660,665,1045,645,'Website interface & interactive search')
    d.text('1  Refine the intended garment',687,748,20,True,BLUE)
    d.text('2  Review visually similar results',1200,748,20,True,BLUE)
    d.rect(685,788,493,295,'#E8F2F9',r=10)
    d.rect(1192,788,488,295,'#E8F2F9',r=10)
    d.image('ui_sam_selection.png',691,795,481,276)
    d.image('ui_selected_search.png',1198,795,476,276)
    features=[('Flexible selection','Full image, rectangle, polygon or freehand.'),
              ('Interactive SAM2','Add positive and negative points; accept the cutout.'),
              ('Product management','Local admin, 1-5 photos, edit, delete, backup and restore.')]
    for i,(title,detail) in enumerate(features):
        x=686+i*336
        d.rect(x,1112,317,143,PALE,r=9)
        d.text(title,x+17,1128,20,True,NAVY)
        d.para(detail,x+17,1164,280,16,23,max_bottom=1248)
    d.text('Actual application screens. Interface verification is separate from retrieval accuracy.',687,1275,13,False,MUTED)

    # Right column: supported experimental result and an actual qualitative case.
    d.panel(1735,310,720,350,'Key research result')
    d.text('Category-correct first result',1767,391,21,True,INK)
    for x,value,label,fill in [(1767,'46%','Full image','#E8EFF4'),(2089,'75%','SAM2 selection','#E2F3FD')]:
        d.rect(x,435,293,125,fill,r=10)
        d.text(value,x+146.5,449,53,True,BLUE if label.startswith('SAM2') else NAVY,'middle')
        d.text(label,x+146.5,516,19,True,INK,'middle')
    d.text('+29 percentage points',1767,580,22,True,BLUE)
    d.para('Historical test: 100 synthetic two-item queries. Category relevance, not exact-product identity.',1767,617,645,14,18,max_bottom=658)

    d.panel(1735,685,720,335,'Example search results')
    d.text('Selected query',1767,768,16,True,BLUE)
    d.text('Top similar catalogue images',1953,768,17,True,BLUE)
    d.image('selected_garment.png',1770,811,95,135)
    d.arrow(1871,873,1922)
    for i in range(3):
        x=1943+i*154
        d.rect(x,808,141,155,PALE,BORDER,8,.7)
        d.image(f'result_{i+1}.jpg',x+8,814,125,122)
        d.text(f'Rank {i+1}',x+70.5,940,13,True,NAVY,'middle')
    d.para('Actual ranked results for the pictured cutout. Visual similarity does not guarantee the same commercial item.',1767,983,645,13,17,max_bottom=1018)

    d.panel(1735,1045,720,265,'Project on GitHub')
    d.para('Source code, editable documentation and runtime downloads.',1767,1130,443,19,27,max_bottom=1218)
    d.text('github.com/nasserco09/Graduation_AI',1767,1248,15,True,BLUE)
    qr=d.qr(CONTENT['github_url'],2251,1120,165)

    # Footer keeps the image count visible and avoids an invented timing claim.
    d.path([('M',0,1339),('C',440,1307,730,1345,1170,1341),('C',1650,1330,2020,1317,2500,1340),('L',2500,1400),('L',0,1400),('Z',)],fill=NAVY)
    d.path([('M',2180,1400),('L',2500,1332),('L',2500,1360),('L',2294,1400),('Z',)],fill=BLUE)
    d.path([('M',2370,1400),('L',2500,1363),('L',2500,1380),('L',2428,1400),('Z',)],fill=CYAN)
    d.text('3,068 original catalogue images',120,1365,22,True,WHITE)
    d.text('SigLIP2  /  SAM2.1  /  FAISS  /  FastAPI',1250,1367,21,False,WHITE,'middle')
    d.text('SELECT  >  SEARCH  >  DISCOVER',2205,1368,15,True,WHITE,'end')
    d.finish()
    result={
        'physical_size_mm':{'width':W,'height':H},'scale':'1:1','print_at':'100%, actual size; do not fit to page',
        'pdf':STEM+'.pdf','svg':STEM+'_Editable.svg','github_qr':qr,
        'body_font_minimum_mm':16,'small_caption_minimum_mm':13,
        'font_family':'Arial, embedded subsets in PDF; editable live text in SVG',
        'text_items':d.texts,'raster_placements':d.placements,
        'assets_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ASSETS.iterdir() if p.is_file()},
    }
    (OUT/'poster_build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pdf':str(OUT/(STEM+'.pdf')),'svg':str(OUT/(STEM+'_Editable.svg')),'physical_size_mm':[W,H]},indent=2))


if __name__=='__main__':main()
