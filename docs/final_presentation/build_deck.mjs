import fs from 'node:fs/promises';

const W=1440,H=810;
const C={navy:'#051E51',blue:'#0766EB',cyan:'#13A2EA',ink:'#183B62',muted:'#587799',border:'#CEE5FA',pale:'#EAF5FF',green:'#08A89A',purple:'#7552EA'};
const transparent={fill:'none',width:0};
const assetRoot=new URL('./assets/',import.meta.url);
const noLine={style:'solid',fill:'none',width:0};
const gradient=(a,b)=>({type:'gradient',gradientKind:'linear',angleDeg:0,stops:[{offset:0,color:a},{offset:100000,color:b}]});

export async function buildDeck(presentation, evidence){
  if(presentation.slides.items.length)presentation.slides.delete(presentation.slides.items.map(s=>s.id));
  presentation.theme.defaultFont='Arial';
  presentation.theme.colorScheme={name:'Twintech Blue',themeColors:{accent1:C.blue,accent2:C.cyan,accent3:C.green,accent4:C.purple,accent5:'#5A9EE8',accent6:'#9CCDF7',bg1:'#FFFFFF',bg2:C.pale,tx1:C.navy,tx2:C.ink,dk1:C.navy,lt1:'#FFFFFF',dk2:C.ink,lt2:C.pale,hlink:C.blue,folHlink:C.purple}};
  const bytes=new Map();
  async function image(s,file,x,y,w,h,alt,link){
    if(!bytes.has(file))bytes.set(file,new Uint8Array(await fs.readFile(new URL(file,assetRoot))));
    return s.images.add({blob:bytes.get(file),contentType:file.endsWith('.jpg')?'image/jpeg':'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h},...(link?{hyperlink:{uri:link,isExternal:true}}:{})});
  }
  function text(s,value,x,y,w,h,size=28,bold=false,color=C.ink,align='left',name=''){
    const q=s.shapes.add({geometry:'textbox',name:name||value.slice(0,45),position:{left:x,top:y,width:w,height:h},fill:'none',line:noLine});
    q.text=value;
    q.text.style={typeface:'Arial',fontSize:size,bold,color,alignment:align,verticalAlignment:'top',insets:0,wrap:'square',autoFit:'none'};
    return q;
  }
  function panel(s,x,y,w,h,fill='#FFFFFF',radius=24){return s.shapes.add({geometry:'roundRect',name:'Content panel',position:{left:x,top:y,width:w,height:h},fill,line:{style:'solid',fill:C.border,width:1.2},borderRadius:radius,shadow:'shadow-sm'});}
  function rule(s,x,y,w,color=C.border,width=1.5){return s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{style:'solid',fill:color,width}});}
  function capsule(s,value,x,y,w,color=C.blue){panel(s,x,y,w,47,gradient(color,'#87C9FF'),23);text(s,value,x+20,y+7,w-40,34,26,true,'#FFFFFF');}
  function foot(s,value){
    const q=panel(s,74,716,1246,52,'#FFFFFF',18);q.name='Evidence note';q.shadow='shadow-none';
    q.text=value;q.text.style={typeface:'Arial',fontSize:18,color:C.muted,verticalAlignment:'middle',insets:{left:14,right:14,top:8,bottom:8},wrap:'square',autoFit:'none'};
  }
  async function base(kicker,title,highlight='',art=null){
    const s=presentation.slides.add({width:W,height:H});
    await image(s,'background.jpg',0,0,W,H,'Blue curved university background');
    const n=presentation.slides.items.length;
    text(s,kicker.toUpperCase(),90,48,1150,31,21,true,C.blue);
    const head=text(s,title,87,91,art?1000:1285,118,58,true,C.navy,'left','Slide title');
    if(highlight)head.text.get(highlight).color=C.blue;
    rule(s,90,202,art?900:1190,'#C5E0FB',1.5);
    if(art)await image(s,art,1122,27,257,153,'Illustration from the supplied university template');
    text(s,String(n).padStart(2,'0'),1338,744,42,28,18,false,'#FFFFFF','right','Slide number');
    return s;
  }
  function notes(s,arabic,sources=''){s.speakerNotes.text=arabic+'\n\n'+sources;}
  function connect(s,a,b,from='right',to='left',color=C.blue){const q=s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{style:'solid',fill:color,width:3},tail:{type:'triangle',width:'sm',length:'sm'}});q.bringToFront();return q;}
  function chart(s,categories,values,pos,opts={}){
    // New Excel chart snapshots use Excel's 15-significant-digit numeric limit.
    // The full source values remain in evidence.json; displayed percentages are unchanged.
    values=values.map(value=>Number(value.toPrecision(15)));
    return s.charts.add('bar',{position:pos,categories,series:[{name:'Category P@1',values,fill:C.blue,points:opts.points||[],valuesFormatCode:opts.format||'0.00%'}],barOptions:{direction:opts.direction||'column',grouping:'clustered',gapWidth:90},hasLegend:false,titlePlacement:'none',chartFill:'none',chartLine:noLine,plotAreaFill:'none',plotAreaLine:noLine,xAxis:{visible:true,textStyle:{typeface:'Arial',fontSize:23,fill:C.ink},line:{style:'solid',fill:'#9AB9D5',width:1},majorGridlines:null},yAxis:{visible:true,min:0,max:1,majorUnit:.25,numberFormatCode:'0%',textStyle:{typeface:'Arial',fontSize:20,fill:C.muted},majorGridlines:{style:'solid',fill:'#DFECF7',width:1},line:{style:'solid',fill:'none',width:0}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:opts.format||'0.00%',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:27,bold:true,fill:C.navy}}});
  }

  // 1. Supplied cover composition with corrected, independently editable wording.
  {
    const s=presentation.slides.add({width:W,height:H});
    await image(s,'cover.jpg',0,0,W,H,'Conceptual visual-search cover adapted from the supplied design');
    await image(s,'university_logo.png',90,57,105,130,'Original IUTT university logo');
    text(s,'INTERNATIONAL UNIVERSITY\nOF TECHNOLOGY TWINTECH',218,75,620,83,27,true,C.navy);
    text(s,'GRADUATION PROJECT',220,167,570,31,20,true,C.blue);
    const title=text(s,'Visual Fashion\nProduct Search',96,268,730,170,66,true,C.navy,'left','Project title');
    title.text.get('Visual Fashion').color=C.blue;
    text(s,'Using Interactive Segmentation',99,443,730,55,33,false,C.navy);
    text(s,'Project members',100,551,340,35,23,true,C.blue);
    text(s,'Nasser Yousef\nNoor Yousef\nNaeem Basalma',100,590,340,108,25,false,C.navy);
    text(s,'Supervised by',478,551,320,35,23,true,C.blue);
    text(s,'Dr. Ayman Alsabri',478,590,350,45,25,true,C.navy);
    text(s,'2026',100,724,220,35,24,true,C.blue);
    notes(s,'نقدم مشروع البحث البصري عن الملابس باستخدام تحديد القطعة تفاعليًا. بدل أن يكتب المستخدم وصفًا طويلًا، يرفع صورة ويختار القطعة المقصودة ثم يستعرض القطع المشابهة. النماذج المستخدمة مسبقة التدريب، ومساهمتنا تشمل التطبيق والتكامل والتجارب وتوضيح حدود النتائج. الصورة على الغلاف توضيحية وليست نتيجة قياس أو لقطة فعلية للتطبيق.','Sources: docs/final_report/config/project.tex; docs/final_report/chapters/chapter1.tex. Cover artwork adapted with image generation from the user-supplied GraduationPPT.pdf.');
  }
  // 2. Agenda added as requested, using the same round panels and blue typography.
  {
    const s=await base('Presentation roadmap','Agenda','Agenda');
    const rows=[['01','Project idea and objectives','The search problem and intended users'],['02','System and dataset','The models, architecture and catalogue'],['03','Evaluation results','Model comparison and garment selection'],['04','Application and verification','Product management and functional checks'],['05','Scope and next steps','What the evidence supports and future work']];
    for(let i=0;i<rows.length;i++){
      const y=244+i*89;
      panel(s,95,y,1240,72,gradient('#FFFFFF','#EAF5FF'),24);
      text(s,rows[i][0],119,y+17,72,38,29,true,C.blue);
      text(s,rows[i][1],218,y+13,525,45,29,true,C.navy);
      text(s,rows[i][2],760,y+20,540,35,23,false,C.muted);
    }
    notes(s,'سنشرح الفكرة والمشكلة والأهداف، ثم آلية النظام والبيانات، وبعدها نعرض النتائج التجريبية. ثم نوضح التطبيق وإدارة المنتجات والتحقق الوظيفي، ونختم بحدود المشروع والتطوير المستقبلي.','Source: presentation structure based on the completed report, Chapters 1-7.');
  }
  // 3. Project idea, following reference page 4.
  {
    const s=await base('Project idea','What our project does','project');
    panel(s,90,234,1250,113,gradient('#F3FAFF','#DEF0FF'),26);
    await image(s,'upload.png',111,249,86,84,'Image upload illustration');
    text(s,'Search for fashion products using an image\ninstead of typing a product name',224,252,1080,88,32,true,C.navy);
    const items=[['Upload an image','A product photo or a scene\ncontaining several garments.','upload.png'],['Choose the garment','Search the full photo or\naccept a SAM2 or manual selection.','select.png'],['Review the results','Inspect visually similar items\nfrom the chosen local catalogue.','results.png']];
    for(let i=0;i<3;i++){
      const x=90+i*425;
      panel(s,x,387,398,238);
      await image(s,items[i][2],x+20,408,103,103,items[i][0]+' illustration');
      text(s,items[i][0],x+130,413,248,77,29,true,C.blue);
      text(s,items[i][1],x+26,528,350,77,25,false,C.ink);
    }
    panel(s,94,653,1243,60,gradient('#F3FAFF','#E2F1FF'),25);
    text(s,'3,068 original gallery images across 10 clothing categories',121,665,1188,43,27,true,C.navy,'center');
    notes(s,'هذا هو مسار الاستخدام الأساسي. لدينا معرض البحث الأصلي المؤلف من 3068 صورة، ولدينا أيضًا كتالوج مستقل للمنتجات التي يضيفها الأدمن. عدد 3068 هو عدد صور وليس عدد منتجات تجارية فريدة موثقة. الاختيار بين الكتالوجين لا يغيّر مبدأ تحديد القطعة.','Sources: docs/final_report/chapters/chapter1.tex; backend/catalog_config.py; backend/demo_catalog.py. Template illustrations cropped unchanged from GraduationPPT.pdf, page 4.');
  }
  // 4. Technical motivation with actual project photographs.
  {
    const s=await base('The problem','Searching by appearance','appearance');
    text(s,'A photo can contain several garments, people and background details.',92,229,1230,52,29,false,C.muted);
    panel(s,90,304,515,374);
    text(s,'The vocabulary gap',120,335,450,48,31,true,C.blue);
    text(s,'A user may recognise a garment\nwithout knowing its name\nor catalogue description.',120,395,450,126,28,false,C.ink);
    text(s,'The target matters',120,548,450,42,29,true,C.blue);
    text(s,'Whole-scene features may reflect\nan unintended garment.',120,601,450,70,26,false,C.ink);
    panel(s,638,304,698,374);
    text(s,'Full query',667,328,340,42,27,true,C.navy);
    text(s,'Accepted cutout',1046,328,264,42,27,true,C.blue);
    await image(s,'composite_query.jpg',663,401,346,182,'Actual jacket-and-dress composite query');
    await image(s,'selected_garment.png',1124,385,98,245,'Actual SAM2 dress cutout with a white background');
    const a=s.shapes.add({geometry:'rightArrow',name:'Selection process arrow',position:{left:1023,top:471,width:71,height:40},fill:C.blue,line:noLine});
    foot(s,'Actual query and cutout. This example illustrates selection, while retrieval quality is measured separately.');
    notes(s,'التحدي ليس فقط العثور على صورة من فئة الملابس الصحيحة، بل فهم أي قطعة يقصدها المستخدم عندما توجد عدة قطع. هنا مثال فعلي من التجربة: جاكيت وفستان في الصورة نفسها. المستخدم ينقر على الفستان ويستطيع إضافة نقاط موجبة أو سالبة ثم يعتمد القصاصة. هذه صورة توضيحية لمسار العمل، ولا نعتبرها تجربة مستقلة لقياس الدقة.','Sources: docs/final_report/chapters/chapter6.tex; docs/poster/example_provenance.json. Actual query and SAM2 cutout are retained project fixtures.');
  }
  // 5. Correct five encoders and objectives, following reference page 2.
  {
    const s=await base('Project goals','Aim & Objectives','Objectives');
    panel(s,90,234,1250,112,gradient('#F5FAFF','#DDEFFF'),26);
    await image(s,'goal.png',109,247,90,88,'Target illustration from the supplied reference');
    text(s,'Build and evaluate an interactive system that retrieves\nvisually similar fashion products from an image',226,252,1077,83,31,true,C.navy);
    const cards=[['01','Model\ncomparison','Compare five encoders:\nResNet50, EfficientNet-B3,\nCLIP, DINOv2 and SigLIP2.','ai.png'],['02','Object\nselection','Compare full-image search\nwith SAM2-guided selection.','select.png'],['03','Working\napplication','Connect search to a browser\nand local product management.','frontend.png']];
    for(let i=0;i<3;i++){
      const x=90+i*425;
      panel(s,x,389,397,270);
      text(s,cards[i][0],x+22,406,70,45,31,true,C.blue);
      await image(s,cards[i][3],x+247,407,129,90,'Objective illustration');
      text(s,cards[i][1],x+22,463,215,83,29,true,C.navy);
      text(s,cards[i][2],x+22,559,353,90,23.5,false,C.ink);
    }
    panel(s,95,664,1239,50,gradient('#F2FAFF','#E2F0FE'),24);
    text(s,'Evaluation distinguishes category relevance from commercial product identity',117,675,1194,35,24,true,C.blue,'center');
    notes(s,'قارنا خمسة نماذج مسبقة التدريب، ثم اخترنا SigLIP2 بناءً على النتائج المسجلة. نستخدم SAM2.1 لعزل القطعة، وليس لإنتاج متجه البحث. التطبيق يتضمن البحث وإدارة المنتجات والحساب المحلي والنسخ الاحتياطي. مصطلح دقة الفئة يعني أن النتيجة من فئة الفستان أو الجاكيت الصحيحة، بينما هوية المنتج التجاري تحتاج معرفات SKU وصورًا مستقلة للمنتج نفسه.','Sources: docs/final_report/chapters/chapter1.tex; evaluation/results/{resnet50,efficientnet_b3,clip,dinov2,siglip2}.json.');
  }
  // 6. Four technology panels corresponding to the supplied stack layout.
  {
    const s=await base('Implementation','System architecture & tech stack','tech stack');
    const items=[['Frontend','HTML, CSS, JavaScript','Image upload\nSelection canvas\nFinal-query preview','frontend.png',C.blue],['Backend','Python and FastAPI','Input validation\nLocal admin\nSQLite stores','backend.png',C.green],['AI models','SigLIP2 and SAM2.1','768-D embeddings\nPoint-guided cutouts','ai.png',C.purple],['Search engine','CPU FAISS IndexFlatIP','Exact ranking of\nnormalised vectors','search.png',C.blue]];
    for(let i=0;i<4;i++){
      const x=65+i*335;
      panel(s,x,257,314,442);
      await image(s,items[i][3],x+40,279,234,140,'Technology illustration');
      capsule(s,items[i][0],x+14,437,286,items[i][4]);
      text(s,items[i][1],x+24,510,268,76,29,true,C.navy);
      text(s,items[i][2],x+24,582,268,108,24,false,C.ink);
    }
    foot(s,'Models run locally with CUDA when available and CPU fallback. Manual region tools operate in the browser.');
    notes(s,'الواجهة مبنية بـHTML وCSS وJavaScript، والخادم FastAPI بلغة Python. SigLIP2 Base يعطي متجهًا طوله 768 بعدًا. SAM2.1 Hiera Base Plus يأخذ نقاطًا موجبة وسالبة ويعيد قناعًا وقصاصة بخلفية بيضاء. المستطيل والمضلع والرسم الحر أدوات يدوية مستقلة في الواجهة، وليست جميعها مدخلات إلى API الخاص بـSAM2. نستخدم نسخة FAISS على CPU، أما النماذج فتدعم CUDA وتعود إلى CPU عند غيابها.','Sources: backend/main.py; backend/segmenter.py; backend/search_engine.py; backend/image_preprocessing.py. SigLIP2: https://arxiv.org/abs/2502.14786. SAM2: https://arxiv.org/abs/2408.00714. FAISS: https://arxiv.org/abs/1702.08734.');
  }
  // 7. Editable architecture. Both search branches reach SigLIP2 before FAISS.
  {
    const s=await base('System design','Implemented system architecture','architecture','header_arch.png');
    const browser=panel(s,65,362,238,220);
    text(s,'Browser',91,390,190,45,32,true,C.blue);
    text(s,'Upload image\nSelect / preview',91,454,190,99,26,false,C.ink);
    const api=panel(s,362,362,240,220);
    text(s,'FastAPI',390,391,185,45,32,true,C.purple);
    text(s,'Validate inputs\nRoute requests',390,454,185,99,26,false,C.ink);
    const sam=panel(s,681,260,314,157,gradient('#F7FFFD','#E8F9F5'));
    text(s,'SAM2.1',703,280,270,41,31,true,C.green);
    text(s,'Points to accepted cutout',703,335,270,67,25,false,C.ink);
    const sig=panel(s,681,488,314,155,gradient('#F7FBFF','#E6F3FF'));
    text(s,'SigLIP2',703,510,270,42,31,true,C.blue);
    text(s,'Normalised 768-D vector',703,564,270,64,25,false,C.ink);
    const rank=panel(s,1080,400,294,200,gradient('#FEFCFF','#F2EEFF'));
    text(s,'Routing and FAISS',1103,424,248,74,30,true,C.purple);
    text(s,'Category control\nSimilarity ranking',1103,514,248,78,25,false,C.ink);
    connect(s,browser,api);connect(s,api,sam);connect(s,api,sig);connect(s,sam,sig,'bottom','top',C.green);connect(s,sig,rank);
    text(s,'selection',606,290,90,31,18,false,C.green);
    text(s,'full image',568,614,120,31,18,false,C.blue);
    panel(s,90,675,1250,53,gradient('#F8FCFF','#E5F3FE'),23);
    text(s,'Original gallery: persistent FAISS index     Added products: independent SQLite records and vectors',109,688,1210,40,23,true,C.navy,'center');
    notes(s,'الصورة الكاملة تتجاوز SAM2 وتصل إلى SigLIP2 مباشرة. عند تحديد القطعة، تنتج SAM2 القصاصة ثم تُشفّر عبر SigLIP2، وبعدها تتم مقارنة المتجهات في FAISS. لا يذهب قناع SAM2 إلى FAISS مباشرة. المعرض الأصلي له فهرس محفوظ، والكتالوج المضاف يخزن الصور والمتجهات في SQLite ويجمع النتائج على مستوى المنتج. هذه مخططات أصلية قابلة للتعديل داخل PowerPoint.','Sources: docs/final_report/chapters/chapter5.tex; backend/main.py; backend/search_engine.py; backend/demo_catalog.py.');
  }
  // 8. Dataset and the actual shared input-preparation contract.
  {
    const s=await base('Dataset and preprocessing','Dataset & preprocessing','preprocessing');
    panel(s,88,258,529,190);
    await image(s,'database.png',106,282,119,121,'Dataset illustration');
    text(s,'Dataset',245,279,335,47,33,true,C.navy);
    text(s,'3,781 images',245,336,340,68,45,true,C.blue);
    text(s,'Clothing dataset small, CC0',245,403,350,39,23,false,C.ink);
    panel(s,650,258,699,190);
    await image(s,'split.png',667,287,111,115,'Dataset split illustration');
    const stats=[['3,068','Train / gallery'],['341','Validation'],['372','Test']];
    for(let i=0;i<3;i++){text(s,stats[i][0],801+i*176,306,170,65,43,true,C.blue,'center');text(s,stats[i][1],801+i*176,382,170,41,23,false,C.ink,'center');}
    panel(s,88,486,529,196);
    await image(s,'classes.png',106,513,119,121,'Clothing-category illustration');
    text(s,'10 categories',244,513,344,57,42,true,C.blue);
    text(s,'Dress, pants, shoes, T-shirt\nand six other clothing classes',244,583,344,87,25,false,C.ink);
    panel(s,650,486,699,196);
    await image(s,'preprocess.png',670,516,110,115,'Shared preparation illustration');
    text(s,'Shared preparation',801,511,520,48,32,true,C.navy);
    text(s,'EXIF orientation, alpha to white,\nRGB conversion and square padding',801,576,520,91,26,false,C.ink);
    foot(s,'Train is the retrieval gallery. The project uses pretrained encoders without neural-model fine-tuning.');
    notes(s,'عدد الصور الكلي 3781، لكن الصور القابلة للبحث في المعرض الأصلي هي 3068 فقط. نستخدم 341 صورة validation للمقارنة والاختيار، و372 صورة test في النتائج النظيفة المسجلة. كلمة train هنا اسم قسم البيانات الذي استخدمناه معرضًا للبحث، ولا تعني أننا دربنا SigLIP2 أو SAM2 من الصفر. الفحص لم يجد نسخًا متطابقة بالبايت أو بالبكسل بين الأقسام، لكن ذلك لا يثبت استقلال المنتجات التجارية عبر الصور المختلفة.','Sources: docs/final_report/tables/dataset.tex; evaluation/results/dataset_identity_audit.json; backend/image_preprocessing.py; https://github.com/alexeygrigorev/clothing-dataset-small.');
  }
  // 9. Rebuilt missing chart with editable native data.
  {
    const s=await base('Model selection','Why we chose SigLIP2','SigLIP2','header_model.png');
    text(s,'Five pretrained encoders on 341 validation queries',95,211,1100,45,28,false,C.muted);
    panel(s,85,276,928,391);
    chart(s,evidence.encoders.map(e=>e.name),evidence.encoders.map(e=>e.p1),{left:102,top:294,width:885,height:349},{points:[{idx:4,fill:C.cyan}]});
    panel(s,1045,276,310,391,gradient('#F7FCFF','#E2F1FD'));
    text(s,'Selected encoder',1068,306,265,48,27,true,C.navy);
    text(s,'SigLIP2 Base',1068,371,265,55,34,true,C.blue);
    text(s,'91.50%',1068,446,265,85,62,true,C.blue);
    text(s,'Validation P@1',1068,532,265,40,25,false,C.ink);
    text(s,'mAP@10  0.8331',1068,601,265,46,25,true,C.navy);
    foot(s,'Category-based relevance on 341 validation queries under the retained encoder-comparison protocol.');
    notes(s,'اختير SigLIP2 لأنه حقق أعلى P@1 في المقارنة المسجلة على صور validation وعددها 341. المقارنة تستخدم نفس معرض البحث وتعريف صلة النتيجة بالفئة، ولكل نموذج معالجته المسبقة المناسبة. لا ننسب هذا الرقم إلى كل صور الزبائن أو إلى تطابق SKU. هذه مقارنة نماذج مسبقة التدريب وليست تجربة تدريب من الصفر.','Sources: evaluation/results/resnet50.json; efficientnet_b3.json; clip.json; dinov2.json; siglip2.json. The damaged reference page 6 is reconstructed from these source files.');
  }
  // 10. Rebuilt results page with visible separation of the two query protocols.
  {
    const s=await base('Evaluation results','The value of garment selection','garment selection');
    panel(s,83,256,827,423);
    text(s,'100 synthetic multi-item test queries',111,279,769,46,30,true,C.navy);
    chart(s,['Full image','SAM2 selection'],[evidence.fullP1,evidence.samP1],{left:110,top:335,width:752,height:290},{format:'0%',points:[{idx:0,fill:'#8EAFE0'},{idx:1,fill:C.blue}]});
    text(s,'+29 percentage points',114,629,755,42,29,true,C.blue,'center');
    panel(s,943,256,410,423,gradient('#F7FBFF','#E8F3FD'));
    text(s,'Separate clean test',971,284,357,48,30,true,C.navy);
    text(s,'372 queries',971,339,357,43,25,false,C.muted);
    text(s,'90.86%',971,406,357,77,60,true,C.blue);
    text(s,'P@1',971,489,357,39,28,true,C.navy);
    text(s,'P@5        88.98%\nmAP@10   0.8254',971,555,357,89,28,false,C.ink);
    foot(s,'Historical category-relevance results from two different query sets. Exact-product accuracy requires verified identities.');
    notes(s,'النتيجة الأساسية على الصور المركبة متعددة القطع هي التحسن من 46 إلى 75 بالمئة في صحة فئة أول نتيجة، بفارق 29 نقطة مئوية على 100 استعلام صناعي. تحسنت 39 حالة وتراجعت 10 وبقيت 51 دون تغيير. النتيجة النظيفة على اليمين تخص 372 صورة test مختلفة، لذلك لا نجمع البروتوكولين. الأرقام لا تعني احتمال أن القطعة التجارية نفسها موجودة. لا نعرض نسب البروشور 98.5% و96.2% على أنها قياسات المشروع.','Source: evaluation/results/FINAL_TEST_RESULTS.json. The damaged reference page 9 is reconstructed using the retained test evidence.');
  }
  // 11. Actual search interaction and results, complementing the measured evaluation.
  {
    const s=await base('Current application','Visual search in the browser','Visual search');
    text(s,'Choose the catalogue, select the intended garment and inspect the ranked products',95,218,1250,65,28,false,C.muted);
    panel(s,82,306,628,350);panel(s,733,306,628,350);
    await image(s,'ui_sam_selection.png',97,320,598,322,'Actual browser interface selecting the dress in a two-garment query');
    await image(s,'ui_selected_search.png',748,320,598,322,'Actual ranked dress results from the selected query');
    text(s,'Point-guided garment selection',102,669,596,40,27,true,C.blue);
    text(s,'Visually similar catalogue items',754,669,600,40,27,true,C.blue);
    foot(s,'Similarity scores rank visual appearance. They are not calibrated probabilities of an exact commercial-product match.');
    notes(s,'هذه لقطات فعلية من البحث في المتصفح: نختار الفستان من صورة تضم جاكيتًا وفستانًا، ثم تظهر نتائج من فئة الفساتين مرتبة بالتشابه البصري. يستطيع المستخدم البحث بالصورة الكاملة أيضًا وتبديل كتالوج البحث. الواجهة تعرض درجة تشابه؛ لا نفسر 83 بالمئة مثلًا على أنها احتمال 83 بالمئة أن المنتج التجاري نفسه موجود. تُستكمل هذه اللقطات بعرض تشغيل مباشر إذا رغبت اللجنة.','Sources: docs/final_report/chapters/chapter6.tex; retained browser-verification screenshots from the isolated application copy.');
  }
  // 12. Actual administration screens for the current application, not a mockup.
  {
    const s=await base('Current application','Local product management','product management');
    text(s,'A local administrator manages products that guests can search from the main page',95,218,1250,65,28,false,C.muted);
    panel(s,82,306,628,342);panel(s,733,306,628,342);
    await image(s,'ui_admin.png',98,320,595,308,'Actual local product-management screen from the isolated verification copy');
    await image(s,'ui_product_editor.png',749,320,595,308,'Actual product editor showing product details and photographs');
    text(s,'Add, edit and delete products',102,668,596,42,27,true,C.blue);
    text(s,'1-5 photos, price and availability',754,668,600,42,27,true,C.blue);
    foot(s,'Protected administration includes backup, restore preview and automatic recovery copies. Guest search needs no account.');
    notes(s,'توجد إدارة منتجات فعلية وليست واجهة شكلية. الأدمن المحلي يضيف المنتج مع صورة إلى خمس صور، ويحدد الاسم والفئة والسعر الاختياري والعملة والتوفر، ويستطيع تعديل الصور وترتيبها واختيار الصورة الرئيسية أو حذف المنتج. يستطيع الزائر البحث في المنتجات المضافة من الصفحة الرئيسية بالصورة الكاملة أو بالتحديد. التصدير والاسترجاع يشملان المنتجات المضافة وصورها ومتجهاتها، ولا يشملان حساب الأدمن أو المعرض الأصلي. الصور المعروضة من نسخة اختبار مستقلة، ولا تعرض بيانات الفريق الشخصية.','Sources: docs/final_report/chapters/chapter6.tex; backend/demo_catalog.py; backend/demo_catalog_api.py; backend/admin_auth.py; backend/catalog_backup.py.');
  }
  // 12. Verification counts are functional checks, never an accuracy denominator.
  {
    const s=await base('Implementation verification','Current system verification','verification');
    text(s,'Recorded on 12 November 2026 for application v1.2.0-rc.9',94,216,1220,48,27,false,C.muted);
    const stats=[['197','Python tests'],['43','JavaScript tests'],['55','Evidence checks']];
    for(let i=0;i<3;i++){
      const x=88+i*427;panel(s,x,293,398,188,gradient('#FFFFFF','#EDF7FF'));
      text(s,stats[i][0],x+23,319,352,94,71,true,C.blue,'center');
      text(s,stats[i][1],x+23,422,352,42,29,true,C.navy,'center');
    }
    panel(s,89,515,609,153);panel(s,729,515,609,153);
    text(s,'32',116,547,107,77,58,true,C.blue);
    text(s,'HTTP integration checks\nActual models on an isolated copy',241,545,425,92,26,false,C.ink);
    text(s,'15',759,547,107,77,58,true,C.blue);
    text(s,'Administration checks\nAccess, edit, backup and restore',884,545,424,92,26,false,C.ink);
    foot(s,'Browser checks exercised upload, selection, search and administration. These are functional checks, not search-accuracy results.');
    notes(s,'هذه أعداد فحوص وظيفية، ولا يجوز تحويل مجموعها إلى دقة بحث. نجحت 197 حالة Python و43 JavaScript، و55 فحصًا للأدلة والبيانات. جربنا أيضًا 32 فحص HTTP و15 تحققًا للإدارة على نسخة معزولة بالنماذج الفعلية على CPU. المتصفح اختبر الرفع والتحديد واعتماد القصاصة والبحث والدخول للإدارة. ذلك لا يضمن جودة كل قناع أو ترتيب كل استعلام، ولا يمثل دراسة استخدام واسعة.','Source: docs/final_report/VERIFICATION_SUBMISSION.json, application verification dated 12 November 2026.');
  }
  // 13. The reference benefits layout now states actual capabilities and scope.
  {
    const s=await base('Scope and future work','Current value & next steps','next steps');
    panel(s,82,263,615,382);panel(s,731,263,615,382);
    await image(s,'customer.png',104,282,85,81,'User illustration from the supplied template');
    text(s,'For the user',205,290,455,47,33,true,C.blue);
    text(s,'Search using an image\nSelect the intended garment\nCorrect the category\nInspect visually similar products',116,395,548,206,29,false,C.ink);
    await image(s,'shop.png',753,282,85,81,'Store administration illustration from the supplied template');
    text(s,'For a local catalogue',852,290,453,47,33,true,C.blue);
    text(s,'Maintain product photos and details\nControl product availability\nProtect local administration\nExport and restore product backups',765,395,548,206,29,false,C.ink);
    panel(s,96,669,1235,59,gradient('#F3FAFF','#E1F0FF'),26);
    text(s,'Next: verified product identities, independent query views and broader user evaluation',120,680,1187,42,26,true,C.navy,'center');
    notes(s,'هذه القيمة تصف الوظائف المنفذة، ولا تدعي زيادة مبيعات أو توصيات شخصية مثبتة. لدينا أدمن محلي واحد، وليس نظام سوق متعدد المتاجر. درجة التشابه ليست احتمال هوية معايرًا. تجربة سبع مجموعات هوية مراجعة عينة تمهيدية صغيرة، وفي الاتجاه العكسي تعادلت الصورة الكاملة وSAM2 عند 7 من 7، لذلك لا نستنتج دقة عامة 100%. أبقينا الفهرس الأصلي لأن قص الكتالوج لم يثبت فائدة كافية. أولوية البحث القادمة هي صور استعلام مستقلة وهوية منتجات موثقة، ثم تقييم أي تحسين للترتيب.','Sources: docs/final_report/chapters/chapter7.tex; evaluation/results/reviewed_identity_pilot.json; reviewed_reverse_sam_pilot.json; safe_crop_catalog_ab.json.');
  }
  // 14. Closing composition and the real public source link.
  {
    const s=presentation.slides.add({width:W,height:H});
    await image(s,'closing.jpg',0,0,W,H,'University closing illustration adapted from the supplied reference');
    await image(s,'university_logo.png',105,61,108,132,'Original IUTT logo');
    text(s,'INTERNATIONAL UNIVERSITY\nOF TECHNOLOGY TWINTECH',244,79,650,85,28,true,C.navy);
    const q=text(s,'Thank You',98,294,760,139,105,true,C.navy);
    q.text.get('You').color=C.blue;
    text(s,'Questions & Discussion',107,443,741,58,35,false,C.navy);
    await image(s,'github_qr.png',111,542,147,147,'QR code opening the public project repository','https://github.com/nasserco09/Graduation_AI');
    const link=text(s,'github.com/nasserco09/Graduation_AI',287,563,568,45,25,true,C.blue);
    link.hyperlink={uri:'https://github.com/nasserco09/Graduation_AI',isExternal:true};
    text(s,'Source code, editable documentation\nand runtime resources',287,618,544,76,25,false,C.ink);
    notes(s,'هذا رابط المستودع الصحيح، وهو متاح للجمهور. اكتمل نشر حزمة التشغيل التي تحتوي النموذجين المستخدمين وصور المعرض والفهرس في 28 جزءًا وخمسة ملفات مساعدة. تنزيل كود Git وحده لا يكفي لتشغيل النماذج؛ تعليمات التجميع والإعداد موضحة في README. يمكن الآن عرض التطبيق محليًا والإجابة عن الأسئلة. مشهد الجامعة في خلفية الختام توضيحي مستمد من التصميم المرسل.','Sources: https://github.com/nasserco09/Graduation_AI; runtime/VERIFICATION_PUBLICATION_20261114.json. Closing artwork adapted with image generation from the supplied PDF.');
  }
  // Two hidden evidence slides remain available for committee questions.
  {
    const s=await base('Additional evidence','Automatic category routing','category routing');s.hidden=true;
    panel(s,86,261,813,410);chart(s,['All categories','Automatic category'],[evidence.routingAll,evidence.routingAuto],{left:115,top:294,width:746,height:335},{points:[{idx:0,fill:'#8EAFE0'},{idx:1,fill:C.blue}]});
    panel(s,931,261,423,410,gradient('#F8FCFF','#E7F3FF'));
    text(s,'372 clean test queries',959,290,371,70,31,true,C.navy);
    text(s,'+4.03 pp',959,383,371,95,61,true,C.blue);
    text(s,'21 improved, 6 worsened\n95% CI: +1.34 to +6.72 pp\nMcNemar p = 0.005925',959,505,371,132,27,false,C.ink);
    foot(s,'Separate application-aligned category study. Its preprocessing and protocol differ from the historical baseline.');
    notes(s,'هذا سلايد احتياطي مخفي في العرض المعتاد. دراسة توجيه الفئة منفصلة عن مقارنة 46 و75 وعن الخط الأساسي التاريخي 90.86. نتائجها 92.20 إلى 96.24 على 372 صورة نظيفة، بفارق محسوب من القيم غير المقربة 4.03 نقطة. لا نجمع النسب أو ننسب النتيجة إلى تحسن هوية المنتج التجاري.','Source: evaluation/results/category_routing_comparison.json.');
  }
  {
    const s=await base('Additional evidence','Why the original index remains active','original index');s.hidden=true;
    const values=[['Query set','n','Original','Safe crop','Hybrid'],['Clean test','372','92.20%','92.74%','91.94%'],['Full composite','100','48.00%','43.00%','49.00%'],['Selected composite','100','76.00%','78.00%','76.00%']];
    const tb=s.tables.add({rows:4,columns:5,left:100,top:284,width:1238,height:294,columnWidths:[426,112,232,232,236],values});
    for(let r=0;r<4;r++)for(let col=0;col<5;col++){
      const cell=tb.getCell(r,col);cell.fill=r===0?C.blue:r%2===1?'#F2F8FE':'#FFFFFF';
      cell.text.style={typeface:'Arial',fontSize:r===0?28:29,bold:r===0,color:r===0?'#FFFFFF':C.ink,alignment:col===0?'left':'center',verticalAlignment:'middle',insets:15};
    }
    tb.borders.assign({style:'solid',fill:C.border,width:1});
    text(s,'Cropping did not show a sufficient consistent gain across query sets.',111,612,1212,78,32,true,C.blue,'center');
    foot(s,'Category Top-1 within this separate comparison. The selected-composite baseline here follows its own application protocol.');
    notes(s,'هذا جدول احتياطي. تجربة قص صور الكتالوج تختلف في تجهيز المدخلات عن الاختبار التاريخي الذي سجل 75 بالمئة. لا يعني ظهور 76 هنا أن نتيجة SAM2 التاريخية تغيرت. على الصور النظيفة التحسن صغير وغير حاسم، وعلى الصورة المركبة الكاملة تراجعت النتائج، ولذلك ظل الفهرس الأصلي فعالًا. الهجين في التجربة يستخدم 90 بالمئة من التمثيل الأصلي و10 بالمئة من القص، ولم يدخل الإنتاج.','Source: evaluation/results/safe_crop_catalog_ab.json.');
  }
  return {slides:presentation.slides.items.length,visibleSlides:15,hiddenSlides:2,nativeChartSlides:[9,10,16],nativeTableSlides:[17]};
}
