# فيديو استخدام LibaasLens — النسخة الصامتة v2

الفيديو الحالي: [LibaasLens_Application_Walkthrough_Silent_v2.mp4](exports/LibaasLens_Application_Walkthrough_Silent_v2.mp4).

أُعيد تسجيل البرنامج بطلب الفريق في 14 نوفمبر 2026: **49 ثانية، 1920×1080، H.264، دون أي مسار صوتي ودون سلايدات PowerPoint**. يظهر شعار الجامعة مع إرشادات إنجليزية قصيرة، والواجهة الفعلية بالعربية. لا توجد موسيقى أو تعليق صوتي.

يعرض رفع صورة، البحث بالصورة الكاملة، تحديد فستان بواسطة SAM2، مراجعة القصاصة واعتمادها ثم البحث بها، إضافة منتج وتعديل سعره، والبحث ضمن المنتجات المضافة من الواجهة الرئيسية. التسجيل من نسخة معزولة على المنفذ 8020 بالنماذج الفعلية؛ المنتجات والأسعار الظاهرة بيانات عرض محلية وليست بيانات الفريق الشخصية. لم تتغير شيفرة التطبيق. الوقفات مقصودة للشرح وليست مقياسًا لسرعة النماذج.

اكتمل فك ترميز الفيديو كاملًا، وتحقق عدم وجود صوت، وراجعت إطارات الرفع والتحديد والنتائج والإضافة والتعديل. انتهى التسجيل بلا أخطاء JavaScript. التفاصيل والبصمة في [DELIVERY.json](DELIVERY.json). هذا يوثق تنفيذ التعديل المطلوب، ولا يدعي أن الفريق راجع النسخة الجديدة بعد إنشائها.

## مصادر التعديل

- [التسجيل الأصلي](raw/demo_walkthrough_v2.webm).
- [النصوص والتوقيت](walkthrough_v2/timeline.json)، و[ترجمة SRT](walkthrough_v2/captions.srt)، و[تصميم ASS](walkthrough_v2/captions.ass).
- [compose.py](walkthrough_v2/compose.py) يعيد إخراج الفيديو من التسجيل؛ لا يحتاج تشغيل النماذج. شغّله باستخدام `python compose.py --work PATH_TO_FINAL_VIDEO --ffmpeg C:/path/to/ffmpeg.exe --output C:/path/to/new_video.mp4`.
- [record_walkthrough_v2.mjs](record_walkthrough_v2.mjs) يعيد تسجيل الخطوات عند الحاجة، على نسخة عرض معزولة. يحتاج Playwright وChrome وإعداد `LIBAAS_VIDEO_DEMO_PASSWORD` لحساب العرض `videoadmin`، و`LIBAAS_PLAYWRIGHT` لمسار المكتبة إذا اختلف. عند الحاجة اضبط `PLAYWRIGHT_BROWSERS_PATH` لمجلد FFmpeg الخاص بـPlaywright. لا تستخدم حسابات أو بيانات المستخدم الحقيقية للتصوير.

يتضمن المصدر شعار الجامعة المستخدم سابقًا، دون توزيع خط Arial أو ملف FFmpeg التنفيذي. FFmpeg متوفر في [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg). ملف ZIP القابل للتعديل يحافظ على بنية `docs/` اللازمة للسكربتات. [حقوق المشروع والموارد الخارجية](../../THIRD_PARTY_NOTICES.md).

النسخة السابقة ذات التعليق الصوتي والسلايدات محفوظة في [ملف v1](exports/Visual_Fashion_Search_Project_Video_EN_v1.mp4)، مع [وصفها التاريخي](README_v1_AR.md) و[تحققها](DELIVERY_v1.json)، ولا تستخدم بدل فيديو التسليم الحالي.
