# TradeFlow - UI/UX Specification

> **وضعیت سند — همگام‌شده با Baseline Hardened (001 + 002) و ADR-056 تا ADR-063.**
>
> این سند «مدل هدف UI» را شرح می‌دهد؛ بسیاری از صفحات و فیلدهای آن Phase 2 یا Future هستند. **برای MVP، `MVP_SCOPE.md` تعیین‌کننده است** (بخش ۴: صفحه‌ها) و در تعارض، آن سند و Baseline برنده‌اند. بخش‌های «MVP UI Scope» (۱۰۳) و «MVP Screen List» (۷۳) باید با آن سند یکی باشند.
>
> **قواعد MVP که روی کل سند اثر دارند:**
> 1. **Login:** سه فیلد: کد سازمان، نام کاربری، رمز عبور (ADR-059). هر کاربر یک سازمان دارد؛ انتخاب/تعویض سازمان در MVP وجود ندارد.
> 2. **پول (ADR-058):** واحد ریال، فقط عدد صحیح؛ جداکننده هزارگان نمایش داده می‌شود، ولی هیچ اعشاری ذخیره یا ارسال نمی‌شود. «دقت قابل تنظیم» و تغییر ارز در MVP نیست. نمایش به تومان (اگر خواسته شود) فقط نمایشی است و مقدار ذخیره‌شده را تغییر نمی‌دهد. UI می‌تواند مجموع‌ها را نمایش دهد، اما مقدار نهایی را سرور تعیین می‌کند.
> 3. **وضعیت درخواست:** فقط `DRAFT`، `SUBMITTED`، `CANCELLED`. در حالت `SUBMITTED` و `CANCELLED` فرم و ردیف‌ها فقط‌خواندنی هستند؛ خطای `409` سرور باید با پیام قابل فهم نمایش داده شود. حذف فقط برای پیش‌نویس است.
> 4. **شماره درخواست** را سرور می‌دهد؛ UI آن را ورودی نمی‌گیرد.
> 5. **تاریخ تحویل مورد درخواست** یک تاریخ تقویمی (بدون ساعت) است و نمی‌تواند قبل از روز درخواست باشد.
> 6. **مشخصات ردیف** هنگام ذخیرهٔ ردیف به‌صورت Snapshot ثبت می‌شود و با تغییر بعدی مشخصات محصول عوض نمی‌شود. اعتبارسنجی نوع مقدار (عدد اعشاری، صحیح، بله/خیر، تاریخ، گزینه، متن) در UI و دوباره در Service انجام می‌شود.
> 7. **فیلدهایی که در Baseline ذخیره نمی‌شوند** و بنابراین در MVP نباید در فرم باشند: شرایط پرداخت، مقصد و حمل، اطلاعات خودرو/راننده، پیوست فایل، تخفیف درصدی/حجمی (فقط `discount_amount` مبلغی)، منبع قیمت/قیمت توافقی، مالیات‌شناسی، کرایه. این موارد Phase 2 هستند.
> 8. **پیش‌فاکتور:** تصمیم پذیرفته‌شده برای MVP+1 (ADR-060)، نه Slice اول. Backend آن (Stage 4) نوشته شده ولی هنوز توسط نویسنده اجرا نشده است؛ **صفحه و دکمهٔ UI هنوز ساخته نشده‌اند** (§ 22).

## 1. هدف سند

این سند ساختار رابط کاربری و تجربه کاربری TradeFlow را مشخص می‌کند.

هدف UI/UX:

- ساده کردن فرآیندهای پیچیده تجاری
- کاهش ورود اطلاعات تکراری
- کاهش خطاهای انسانی
- نمایش شفاف وضعیت هر معامله
- دسترسی سریع به اطلاعات مهم
- پشتیبانی کامل از زبان فارسی و RTL
- پشتیبانی از موبایل، دسکتاپ و تبلت
- امکان کار در حالت Offline
- جلوگیری از وابستگی رابط کاربری به یک صنعت خاص
- حفظ قابلیت توسعه برای صنایع مختلف

رابط کاربری نباید منطق کسب‌وکار را تعیین کند.

Business Rules باید در لایه Application/Domain و Backend enforce شوند.

---

# 2. اصول اصلی UX

## 2.1 سادگی

کاربر نباید برای انجام یک عملیات معمول، از چندین صفحه غیرضروری عبور کند.

## 2.2 شفافیت

در هر معامله کاربر باید بتواند به سرعت ببیند:

- مشتری چه کسی است؟
- چه محصولی خریداری شده؟
- مقدار چقدر است؟
- قیمت چقدر است؟
- وضعیت پرداخت چیست؟
- کالا آماده است یا خیر؟
- حواله صادر شده یا خیر؟
- بارگیری انجام شده یا خیر؟
- مجوز خروج صادر شده یا خیر؟
- کالا تحویل شده یا خیر؟
- اختلاف وزن وجود دارد یا خیر؟
- اختلاف یا شکایت باز وجود دارد یا خیر؟

## 2.3 کاهش ورود دستی

اطلاعاتی که قبلاً ثبت شده‌اند باید در عملیات بعدی قابل انتخاب باشند.

نمونه:

- مشتری
- محصول
- راننده
- خودرو
- آدرس
- اطلاعات تماس

## 2.4 جلوگیری از خطای مالی

قیمت، تخفیف، مبلغ پرداختی و مانده باید واضح و قابل کنترل باشند.

## 2.5 جلوگیری از حذف اطلاعات تاریخی

اطلاعات ثبت‌شده معاملات نباید بدون ردپای حسابرسی حذف شوند.

## 2.6 نمایش وضعیت واقعی

Status باید از رنگ، متن و نشانه بصری مناسب استفاده کند.

نمونه:

- پیش‌نویس
- در انتظار تأیید
- در انتظار پرداخت
- پرداخت ناقص
- پرداخت کامل
- در انتظار کالا
- آماده بارگیری
- در حال بارگیری
- آزاد شده
- تحویل شده
- اختلاف
- لغو شده
- تکمیل شده

---

# 3. زبان و جهت رابط کاربری

زبان اصلی:

Persian

Direction:

RTL

تمام صفحات اصلی باید برای RTL طراحی شوند.

موارد زیر باید فارسی‌سازی شوند:

- عنوان‌ها
- دکمه‌ها
- پیام‌ها
- خطاها
- فرم‌ها
- منوها
- گزارش‌ها
- وضعیت‌ها

تاریخ در رابط کاربری:

شمسی

زمان:

24 ساعته

اعداد:

پشتیبانی از نمایش فارسی و لاتین بر اساس تنظیمات.

---

# 4. تاریخ و زمان

تاریخ در UI به صورت شمسی نمایش داده شود.

نمونه:

1405/06/25

زمان:

14:35

اما تاریخ و زمان در Backend و Database باید طبق API Specification به صورت استاندارد ذخیره شوند.

UI مسئول تبدیل نمایش تاریخ به شمسی است.

---

# 5. ساختار کلی برنامه

ساختار اصلی:

- ورود
- داشبورد
- معاملات
- مشتریان
- محصولات
- حمل و نقل
- پرداخت‌ها
- اسناد
- گزارش‌ها
- اعلان‌ها
- تنظیمات

منوی اصلی باید بر اساس Role کاربر قابل تغییر باشد.

کاربر نباید منوهایی را که Permission آنها را ندارد مشاهده یا استفاده کند.

---

# 6. صفحه ورود

## عناصر

- کد سازمان
- نام کاربری (در MVP؛ ورود با شماره موبایل در Baseline پشتیبانی نمی‌شود)
- رمز عبور
- ورود
- فراموشی رمز عبور
- انتخاب زبان در صورت فعال بودن
- وضعیت اتصال

## رفتار

در صورت Offline بودن:

- اگر نشست معتبر قبلی وجود داشته باشد، قابلیت‌های مجاز Offline ارائه شود.
- در غیر این صورت ورود جدید نیازمند ارتباط با Server است.

---

# 7. داشبورد

داشبورد باید متناسب با Role کاربر نمایش داده شود.

## اطلاعات اصلی

کارت‌های خلاصه:

- معاملات امروز
- فروش امروز
- پرداخت‌های امروز
- مطالبات
- معاملات در انتظار تأیید
- معاملات در انتظار پرداخت
- معاملات آماده بارگیری
- بارهای در حال حمل
- اختلاف وزن
- شکایات باز

## هشدارها

بخش Alert:

- پرداخت ناقص
- معامله در انتظار تأیید
- کالا آماده نشده
- حواله بدون بارگیری
- اختلاف وزن
- سند ناقص
- شکایت باز
- سررسید اعتبار
- خطای همگام‌سازی

## عملیات سریع

Quick Actions:

- معامله جدید
- مشتری جدید
- محصول جدید
- ثبت پرداخت
- ثبت خودرو
- ثبت وزن
- مشاهده گزارش‌ها

---

# 8. صفحه معاملات

صفحه معاملات باید فهرست تمام معاملات مجاز برای کاربر را نمایش دهد.

## اطلاعات هر ردیف

- شماره معامله
- تاریخ
- مشتری
- مبلغ
- مقدار
- وضعیت معامله
- وضعیت پرداخت
- وضعیت کالا
- وضعیت بارگیری
- وضعیت تحویل

## امکانات

- جستجو
- فیلتر
- مرتب‌سازی
- مشاهده جزئیات
- ویرایش در صورت مجاز بودن
- لغو در صورت مجاز بودن
- چاپ
- PDF
- اشتراک‌گذاری

---

# 9. صفحه جزئیات معامله

این صفحه یکی از مهم‌ترین صفحات TradeFlow است.

اطلاعات باید به صورت Timeline و Section نمایش داده شوند.

## Header

- شماره معامله
- تاریخ
- مشتری
- وضعیت اصلی

## بخش وضعیت‌ها

نمایش مستقل:

- Order Status
- Approval Status
- Payment Status
- Availability Status
- Voucher Status
- Loading Status
- Weighing Status
- Release Status
- Delivery Status
- Settlement Status
- Dispute Status

این وضعیت‌ها نباید با یک Status واحد جایگزین شوند.

---

# 10. Timeline معامله

Timeline باید رویدادهای اصلی معامله را نمایش دهد.

نمونه:

ثبت درخواست
↓
تأیید قیمت
↓
صدور پیش‌فاکتور
↓
تأیید مدیریت
↓
پرداخت
↓
صدور حواله
↓
آماده‌سازی کالا
↓
ورود خودرو
↓
وزن خالی
↓
بارگیری
↓
وزن پر
↓
مجوز خروج
↓
خروج
↓
تحویل
↓
وزن مقصد
↓
تسویه
↓
صدور فاکتور
↓
تکمیل

هر رویداد باید شامل:

- عنوان
- تاریخ
- ساعت
- کاربر
- توضیح
- اسناد مرتبط

باشد.

---

# 11. فرم درخواست خرید

فرم درخواست خرید باید بر اساس FormTemplate قابل تنظیم باشد.

فرم نباید به محصولات یا صنعت خاص Hard-code شود.

## اطلاعات درخواست

- شماره درخواست
- تاریخ
- ساعت
- مشتری
- شرکت
- اطلاعات تماس
- آدرس
- اطلاعات مالیاتی در صورت نیاز

شماره درخواست باید توسط Server تولید شود (شمارندهٔ هر سازمان، ADR-057).

تاریخ تحویل مورد درخواست فقط تاریخ است (بدون ساعت) و از روز درخواست زودتر نمی‌شود؛ همان روز مجاز است.

---

# 12. انتخاب مشتری

Customer Selector باید قابلیت:

- جستجو با نام
- جستجو با شماره موبایل
- جستجو با شناسه
- انتخاب مشتری موجود
- ایجاد مشتری جدید

را داشته باشد.

اطلاعات مشتری انتخاب‌شده نباید دوباره به صورت دستی وارد شوند مگر برای اصلاح یا اطلاعات تکمیلی.

---

# 13. انتخاب محصول

محصول باید از Product Catalog انتخاب شود.

ورود نام محصول به صورت Free Text نباید روش اصلی باشد.

## فرآیند

انتخاب دسته‌بندی
→
انتخاب محصول
→
نمایش مشخصات
→
ورود مقدار
→
ورود واحد
→
ورود بسته/باندل در صورت وجود
→
ورود قیمت
→
ثبت آیتم

---

# 14. مشخصات محصول

مشخصات محصول باید Dynamic باشند.

مثلاً در صنعت لوله:

- قطر
- ضخامت
- طول
- استاندارد
- گرید

اما در صنعت دیگر می‌تواند شامل:

- برند
- مدل
- سال
- کد فنی

باشد.

UI نباید این فیلدها را به صورت ثابت در Core تعریف کند.

---

# 15. آیتم‌های معامله

کاربر بتواند چندین محصول به یک معامله اضافه کند.

هر Item شامل:

- محصول
- مشخصات
- تعداد
- واحد
- تعداد بسته
- وزن تخمینی
- قیمت واحد
- تخفیف
- مبلغ نهایی
- توضیحات

باشد.

## محاسبات

UI باید:

- جمع مقدار
- جمع وزن تخمینی
- مبلغ ناخالص
- تخفیف
- مبلغ نهایی

را نمایش دهد.

محاسبات نهایی باید در Server نیز مجدداً Validation شوند.

---

# 16. قیمت

قیمت باید واضح نمایش داده شود.

اطلاعات قابل نمایش:

- قیمت پایه
- قیمت توافقی
- تخفیف
- مبلغ نهایی
- مالیات در صورت وجود
- مبلغ قابل پرداخت

در صورت قیمت خاص یا پایین‌تر از قیمت مجاز، UI باید وضعیت Approval را نمایش دهد.

---

# 17. تخفیف

تخفیف می‌تواند:

- درصدی
- مبلغی
- حجمی
- مشتری خاص
- قیمت ویژه

باشد.

اگر نیاز به تأیید داشته باشد:

نمایش:

«در انتظار تأیید»

و کاربر بدون Permission نباید بتواند معامله را نهایی کند.

---

# 18. شرایط پرداخت

UI باید گزینه‌های قابل تنظیم داشته باشد:

- نقدی
- پیش‌پرداخت
- پرداخت کامل
- پرداخت جزئی
- وزن و پول
- اعتباری
- چک
- ترکیبی

در حالت Credit:

- مدت اعتبار
- تاریخ سررسید
- ضمانت
- چک
- قرارداد
- وثیقه
- تأییدکننده

نمایش داده شود.

---

# 19. مقصد و حمل

اطلاعات:

- آدرس بارگیری
- آدرس تحویل
- شهر
- استان
- کد پستی
- گیرنده
- تلفن هماهنگی
- نوع حمل
- کرایه
- پرداخت‌کننده کرایه

باید قابل ثبت باشد.

کرایه توافقی و کرایه واقعی باید جداگانه نگهداری و نمایش داده شوند.

---

# 20. اطلاعات خودرو و راننده

اطلاعات راننده:

- نام
- کد ملی
- تلفن

اطلاعات خودرو:

- شماره پلاک
- نوع خودرو
- ظرفیت
- مالک

اسناد:

- تصویر کارت ملی
- مدارک خودرو
- سایر اسناد

باید امکان بارگذاری داشته باشند.

---

# 21. پیوست‌ها

Attachment باید در تمام مراحل قابل استفاده باشد.

نمونه:

- تصویر درخواست امضا شده
- مهر شرکت
- کارت ملی
- مدارک خودرو
- رسید پرداخت
- چک
- قرارداد
- پیش‌فاکتور
- حواله
- باسکول
- عکس بار
- عکس عیب
- سند مرجوعی

برای هر فایل:

- نوع سند
- تاریخ
- ثبت‌کننده
- ارتباط با معامله
- وضعیت

ثبت شود.

---

# 22. پیش‌فاکتور

صفحه پیش‌فاکتور باید شامل:

- مشخصات فروشنده
- مشخصات خریدار
- اقلام
- مقدار
- وزن تخمینی
- قیمت
- تخفیف
- مبلغ
- مالیات
- کرایه
- شرایط پرداخت
- مقصد
- توضیحات
- تأییدها

باشد.

## عملیات

- ذخیره
- تأیید
- رد
- ایجاد نسخه جدید
- PDF
- چاپ
- اشتراک‌گذاری

پیش‌فاکتور تأییدشده نباید بدون ایجاد Version جدید تغییر کند.

> **وضعیت (ADR-060، Stage 4):** Backend پیش‌فاکتور نوشته شده است (Migration `004`، هفت Endpoint، قرارداد § 26 در `SLICE_01_CONTRACT.md`) و هنوز توسط نویسنده اجرا نشده است. **UI ساخته نشده است.** فهرست بالا هدف بلندمدت صفحه است؛ آنچه Backend پشتیبانی می‌کند و UI باید به آن محدود باشد:
>
> - **پیاده‌شده (Backend):** ایجاد پیش‌نویس از درخواست `SUBMITTED`؛ صدور (شماره و نسخه فقط در لحظهٔ صدور)؛ لغو (پیش‌نویس: علت اختیاری؛ صادرشده: علت الزامی)؛ تولید و دانلود PDF با وضعیت مستقل `pending/ready/failed`؛ فهرست و جزئیات.
> - **سیاست MVP (نه قانون دائمی):** پیش‌نویس قابل ویرایش نیست (لغو و ایجاد پیش‌نویس جدید)؛ اصلاح پیش‌فاکتور صادرشده = **درخواست خرید جدید** (`SUBMITTED`) و پیش‌فاکتوری که جایگزین قبلی می‌شود؛ قبلی فقط پس از صدور موفق جایگزین `SUPERSEDED` می‌شود؛ درخواستی که پیش‌فاکتور `ISSUED` دارد از مسیر عادی لغو نمی‌شود.
> - **دسترسی:** فروش فقط پیش‌فاکتورهای درخواست‌های خودش؛ حسابداری مشاهده/صدور/لغو صادرشده/تولید PDF؛ مدیر همه.
> - **UI باید خطاها را جدا نشان دهد:** شکست PDF (`PDF_GENERATION_FAILED`، وضعیت `failed`، با امکان تلاش مجدد پس از ۶۰ ثانیه، حداکثر ۳ تلاش مجدد در ۱۵ دقیقه) هرگز به‌معنای شکست صدور نیست.
> - **در Backend وجود ندارد و در UI نباید وانمود شود:** تأیید/رد مدیریتی، «ایجاد نسخه جدید» درجا، کرایه، شرایط پرداخت، مقصد، مدت اعتبار (مثلاً ۲۴ ساعت)، پیش‌پرداخت، چاپ و اشتراک‌گذاری. این‌ها Future هستند و قابل‌پیکربندی نیستند.
> - **مانع باز:** کتابخانهٔ PDF و قلم فارسی هنوز تصویب نشده؛ تا آن زمان تولید PDF با `PDF_RENDERER_UNAVAILABLE` شکست می‌خورد.

---

# 23. تأیید مدیریت

در صورت نیاز به تأیید:

صفحه باید نمایش دهد:

- دلیل نیاز به تأیید
- قیمت
- تخفیف
- شرایط اعتبار
- مبلغ
- مشتری
- توضیحات فروش

عملیات:

- تأیید
- رد
- درخواست اصلاح

همراه با:

- کاربر
- تاریخ
- ساعت
- توضیح

ثبت شود.

---

# 24. پرداخت

صفحه پرداخت باید اطلاعات زیر را نمایش دهد:

- مبلغ معامله
- مبلغ پرداخت‌شده
- مانده
- وضعیت پرداخت

ثبت پرداخت:

- مبلغ
- تاریخ
- روش پرداخت
- بانک
- شماره پیگیری
- توضیحات
- پیوست رسید

## پرداخت جزئی

Progress نمایش داده شود.

مثلاً:

پرداخت شده: 700 میلیون
مانده: 300 میلیون

پرداخت کامل به صورت خودکار وضعیت Payment را تغییر می‌دهد، ولی به معنی Release نیست.

---

# 25. حواله

پس از شرایط لازم:

- شماره حواله
- تاریخ
- معامله
- مشتری
- مبلغ
- وضعیت
- صادرکننده

نمایش داده شود.

حواله می‌تواند:

- صادر شده
- استفاده نشده
- در حال بارگیری
- استفاده شده
- باطل شده

باشد.

---

# 26. آماده‌سازی کالا

صفحه باید وضعیت کالا را نشان دهد:

- آماده نیست
- در حال تولید
- آماده
- ناقص
- بخشی آماده
- رزرو شده

اگر کالا آماده نباشد، علت باید قابل مشاهده باشد.

---

# 27. بارگیری

صفحه بارگیری شامل:

- معامله
- مشتری
- محصول
- مقدار
- خودرو
- راننده
- وضعیت پرداخت
- حواله
- وضعیت کالا
- مجوز بارگیری

باشد.

قبل از بارگیری Validation انجام شود.

---

# 28. باسکول مبدأ

اطلاعات:

## وزن خالی

- وزن
- تاریخ
- ساعت
- باسکول
- اپراتور
- شماره رسید

## وزن پر

- وزن
- تاریخ
- ساعت
- باسکول
- اپراتور
- شماره رسید

## وزن خالص

Net Weight:

وزن پر - وزن خالی

وزن واقعی باید جدا از وزن تخمینی نگهداری شود.

---

# 29. مجوز خروج

مجوز خروج باید یک بخش مستقل باشد.

نمایش:

- وضعیت پرداخت
- وضعیت حواله
- وضعیت بارگیری
- خودرو
- راننده
- وزن
- اسناد
- تأییدهای لازم

عملیات:

- تأیید خروج
- عدم تأیید
- مسدود کردن

ثبت:

- تأییدکننده
- تاریخ
- ساعت
- دلیل

بدون Permission مناسب، کاربر نباید قادر به صدور مجوز خروج باشد.

---

# 30. تحویل

صفحه Delivery:

- معامله
- خودرو
- راننده
- مقصد
- گیرنده
- زمان حرکت
- زمان تحویل
- وضعیت تحویل
- اسناد

وضعیت:

- در مسیر
- تحویل شده
- تحویل ناقص
- تحویل با اختلاف
- برگشتی

---

# 31. باسکول مقصد

در صورت استفاده:

- وزن پر مقصد
- وزن خالی مقصد
- وزن خالص مقصد
- شماره رسید
- تاریخ
- ساعت

ثبت شود.

سیستم باید وزن مبدأ و مقصد را مقایسه کند.

---

# 32. اختلاف وزن

در صورت عبور از Threshold تنظیم‌شده:

Alert نمایش داده شود.

نمایش:

- وزن مبدأ
- وزن مقصد
- اختلاف
- درصد اختلاف
- حد مجاز
- وضعیت بررسی

کاربر مجاز بتواند:

- تأیید اختلاف
- ارجاع برای بررسی
- ثبت توضیح
- ثبت سند

انجام دهد.

---

# 33. معامله مشکل‌دار

برای بار مشکل‌دار:

- ثبت مشکل
- انتخاب نوع مشکل
- توضیح
- عکس
- سند
- مسئول بررسی
- تصمیم

## انواع نمونه

- کسری
- اضافه
- اشتباه محصول
- کیفیت
- جوش
- زنگ‌زدگی
- بسته‌بندی
- اختلاف وزن
- مغایرت سفارش

نوع مشکل باید قابل توسعه باشد.

---

# 34. تخفیف بعد از مشکل

اگر برای حل اختلاف تخفیف داده شود:

- مبلغ قبل
- مبلغ تخفیف
- مبلغ بعد
- علت
- تأییدکننده

ثبت شود.

تغییر قیمت تاریخی بدون ثبت رویداد ممنوع است.

---

# 35. مرجوعی

صفحه Return:

- معامله اصلی
- آیتم
- مقدار
- دلیل
- عکس
- وضعیت
- تصمیم
- مبلغ برگشتی
- تأییدکننده

باشد.

مرجوعی نباید معامله اصلی را پاک کند.

---

# 36. اسناد

صفحه Documents باید امکان فیلتر بر اساس:

- معامله
- مشتری
- نوع سند
- تاریخ
- ثبت‌کننده
- وضعیت

را داشته باشد.

عملیات:

- مشاهده
- دانلود
- چاپ
- اشتراک‌گذاری
- افزودن سند

---

# 37. PDF

PDF باید یک Document واقعی و رسمی باشد.

نباید Screenshot از صفحه باشد.

PDF باید شامل:

- سربرگ
- اطلاعات شرکت
- اطلاعات معامله
- جدول اقلام
- مبالغ
- شرایط
- امضا
- تاریخ
- شماره سند

باشد.

قالب PDF باید قابل تنظیم توسط Organization باشد.

---

# 38. چاپ

Print باید برای فرم‌های رسمی فعال باشد.

صفحات مهم:

- درخواست خرید
- پیش‌فاکتور
- حواله
- رسید
- گزارش
- اسناد باسکول

---

# 39. اشتراک‌گذاری

Share باید از سیستم‌عامل استفاده کند.

مسیر:

Document
→
Generate PDF
→
Share
→
انتخاب برنامه

TradeFlow نباید به WhatsApp یا Bale وابسته باشد.

هر Messenger یا Share Target باید از طریق قابلیت استاندارد سیستم‌عامل استفاده شود.

---

# 40. جستجو

Search باید در صفحات اصلی فعال باشد.

نمونه:

جستجوی معامله با:

- شماره معامله
- نام مشتری
- شماره تلفن
- شناسه
- شماره حواله
- شماره خودرو
- راننده

جستجوی محصول با:

- نام
- کد
- دسته‌بندی
- مشخصات

---

# 41. فیلترها

فیلترها باید قابل ترکیب باشند.

نمونه:

تاریخ
+
مشتری
+
محصول
+
وضعیت پرداخت
+
وضعیت تحویل

---

# 42. اعلان‌ها

Notification Center:

- تأیید مورد نیاز
- پرداخت جدید
- پرداخت ناقص
- حواله صادر شد
- کالا آماده شد
- خودرو وارد شد
- اختلاف وزن
- شکایت جدید
- سررسید اعتبار
- خطای Sync

اعلان‌ها باید بر اساس Permission و Role کنترل شوند.

---

# 43. حالت Offline

در صورت قطع اینترنت:

UI باید وضعیت Offline را به صورت واضح نمایش دهد.

نمونه:

«آفلاین - تغییرات روی دستگاه ذخیره می‌شوند»

اطلاعات قابل انجام Offline باید از قبل تعریف شده باشند.

هر رکورد Sync نشده باید وضعیت مشخص داشته باشد.

نمونه:

- در انتظار همگام‌سازی
- همگام‌سازی شد
- خطای همگام‌سازی
- نیازمند بررسی

---

# 44. Conflict

در صورت تغییر یک رکورد در دو محل:

UI نباید اطلاعات را silently overwrite کند.

در صورت Conflict:

- اطلاعات Server
- اطلاعات Local
- زمان تغییر
- کاربر تغییر‌دهنده

نمایش داده شود.

تصمیم‌گیری بر اساس Business Rule انجام شود.

---

# 45. Loading State

در زمان دریافت اطلاعات:

- Skeleton
- Progress Indicator
- Loading message

استفاده شود.

کاربر نباید تصور کند برنامه هنگ کرده است.

---

# 46. Empty State

اگر داده‌ای وجود ندارد، پیام واضح نمایش داده شود.

نمونه:

«هنوز معامله‌ای ثبت نشده است.»

و در صورت امکان:

دکمه عملیات مرتبط نمایش داده شود.

---

# 47. Error State

پیام خطا باید قابل فهم باشد.

به جای:

Error 500

نمایش داده شود:

«ارتباط با سرور برقرار نشد. اطلاعات شما حذف نشده است.»

خطای فنی برای Log ثبت شود، ولی کاربر پیام قابل فهم دریافت کند.

---

# 48. Confirmation

عملیات حساس نیازمند تأیید هستند.

نمونه:

- حذف Draft
- لغو معامله
- لغو حواله
- مجوز خروج
- مرجوعی
- تأیید تخفیف خاص
- تغییر شرایط اعتبار

پیام باید دقیقاً بگوید چه اتفاقی خواهد افتاد.

---

# 49. Delete Policy

Draft:

قابل حذف با تأیید.

Transaction ثبت‌شده:

حذف فیزیکی ممنوع.

به جای Delete:

- Cancel
- Archive
- Soft Delete

بر اساس Business Rule استفاده شود.

---

# 50. نقش‌ها و UI

UI باید Permission-aware باشد.

نمونه:

Sales:

- ثبت درخواست
- قیمت‌گذاری
- مشاهده مشتری
- مشاهده معاملات

Finance:

- پرداخت
- تأیید پرداخت
- حواله

Manager:

- تأیید قیمت
- تخفیف
- اعتبار

Warehouse:

- آماده‌سازی
- بارگیری

Weighbridge:

- ثبت وزن

Release Authority:

- مجوز خروج

Admin:

- تنظیمات و مدیریت سیستم

---

# 51. صفحه مشتریان

اطلاعات:

- نام
- شرکت
- شناسه
- تلفن
- آدرس
- اطلاعات مالیاتی
- معاملات
- پرداخت‌ها
- مطالبات
- اسناد
- اعتبار
- سوابق

Customer Profile باید Timeline داشته باشد.

---

# 52. صفحه محصولات

امکانات:

- فهرست
- جستجو
- دسته‌بندی
- ایجاد
- ویرایش
- فعال/غیرفعال
- مشخصات
- واحد
- بسته‌بندی

محصول غیرفعال:

در معاملات جدید قابل انتخاب نیست.

اما در معاملات تاریخی همچنان نمایش داده می‌شود.

---

# 53. مدیریت مشخصات محصول

Admin/Authorized User بتواند:

- Template ایجاد کند
- Field اضافه کند
- Required/Optional تعیین کند
- نوع داده تعیین کند
- ترتیب نمایش را تغییر دهد

نوع Field می‌تواند:

- Text
- Number
- Decimal
- Dropdown
- Date
- Boolean

باشد.

---

# 54. Form Template

Organization بتواند فرم‌های خود را تنظیم کند.

تنظیمات:

- عنوان
- فیلدها
- ترتیب
- Required
- Optional
- Terms
- Header
- Footer
- Logo
- Signature
- Print settings
- PDF settings

---

# 55. گزارش‌ها

UI گزارش‌ها باید شامل:

- فیلتر تاریخ
- مشتری
- محصول
- فروشنده
- وضعیت
- استان
- شهر
- روش پرداخت

باشد.

خروجی:

- نمایش در برنامه
- PDF
- Excel
- Print
- Share

---

# 56. نمودارها

Dashboard می‌تواند شامل:

- فروش در طول زمان
- فروش بر اساس محصول
- فروش بر اساس مشتری
- پرداخت‌ها
- مطالبات
- معاملات تکمیل‌شده
- معاملات مشکل‌دار

باشد.

نمودارها باید ابزار تصمیم‌گیری باشند، نه تزئینات گرافیکی که صرفاً فضای صفحه را می‌خورند.

---

# 57. تنظیمات

Settings شامل:

- اطلاعات سازمان
- کاربران
- نقش‌ها
- Permission
- محصولات
- دسته‌بندی‌ها
- واحدها
- Form Templates
- Business Rules
- Thresholdها
- اعلان‌ها
- تنظیمات PDF
- تنظیمات چاپ
- Backup
- Sync
- Security
- Language
- Date settings

---

# 58. Responsive Design

UI باید برای:

- Mobile
- Tablet
- Desktop

طراحی شود.

Mobile:

- Navigation ساده
- فرم‌های مرحله‌ای
- Bottom Navigation در صورت مناسب بودن

Desktop:

- Sidebar
- جدول‌های کامل
- چند ستون
- Dashboard گسترده

Tablet:

ترکیبی از دو حالت.

---

# 59. فرم‌های طولانی

فرم‌های طولانی نباید یک صفحه بسیار بلند باشند.

در موبایل:

Step-based Form

مثلاً:

1. مشتری
2. محصولات
3. قیمت
4. پرداخت
5. حمل
6. اسناد
7. بررسی نهایی

در Desktop امکان نمایش چند بخش در یک صفحه وجود دارد.

---

# 60. Auto Save

Draft باید در صورت امکان Auto Save داشته باشد.

کاربر باید وضعیت ذخیره را ببیند.

نمونه:

«ذخیره شد 14:32»

یا:

«در انتظار ذخیره روی سرور»

---

# 61. جلوگیری از از دست رفتن اطلاعات

در صورت:

- خروج از صفحه
- بسته شدن برنامه
- قطع اینترنت
- Crash

اطلاعات Draft نباید بدون هشدار از بین بروند.

---

# 62. Accessibility

رابط کاربری باید:

- اندازه متن مناسب
- Contrast مناسب
- دکمه‌های قابل لمس
- Label واضح
- پیام خطای قابل فهم
- عدم وابستگی صرف به رنگ

داشته باشد.

Status نباید فقط با رنگ نمایش داده شود.

---

# 63. طراحی بصری

طراحی باید:

- حرفه‌ای
- صنعتی
- ساده
- قابل اعتماد
- کم‌حجم
- خوانا

باشد.

از شلوغی غیرضروری پرهیز شود.

رنگ‌ها باید نقش مشخص داشته باشند.

مثلاً:

- وضعیت عادی
- هشدار
- خطا
- موفقیت
- اطلاعات

اما معنی Status باید با متن نیز مشخص باشد.

---

# 64. Design System

کامپوننت‌های مشترک:

- Button
- TextField
- Dropdown
- SearchableDropdown
- DatePicker
- TimePicker
- CurrencyField
- QuantityField
- WeightField
- StatusChip
- Card
- Table
- DataGrid
- Dialog
- BottomSheet
- AttachmentPicker
- Timeline
- Stepper
- Alert
- Toast
- EmptyState
- LoadingState

باید تا حد امکان reusable باشند.

---

# 65. ورود مقادیر مالی

فیلدهای مالی باید:

- جداکننده هزارگان
- واحد پول (در MVP: ریال)
- بدون اعشار در MVP (عدد صحیح؛ دقت قابل تنظیم = Future، ADR-042)

داشته باشند.

کاربر نباید مجبور باشد صفرهای متعدد را دستی بشمارد، چون بشر همین حالا هم در شمارش صفرها سابقه درخشانی ندارد.

---

# 66. ورود وزن

Weight Field باید:

- واحد
- تعداد اعشار
- Validation

داشته باشد.

وزن تخمینی و وزن واقعی باید از هم قابل تشخیص باشند.

---

# 67. ورود تعداد

Quantity باید بر اساس Unit کنترل شود.

مثلاً:

- kg
- ton
- piece
- bundle
- box
- set
- meter

واحد باید از Product/Transaction مشخص شود.

---

# 68. Navigation

Navigation باید قابل پیش‌بینی باشد.

کاربر باید بتواند از جزئیات معامله به بخش‌های مرتبط برسد:

Transaction
→ Customer

Transaction
→ Product

Transaction
→ Payment

Transaction
→ Transport

Transaction
→ Documents

Transaction
→ Dispute

---

# 69. Quick Actions

در صفحات مرتبط عملیات اصلی در دسترس باشند.

مثلاً در Transaction:

- ثبت پرداخت
- افزودن سند
- ثبت خودرو
- ثبت وزن
- مشاهده PDF

اما عملیات حساس فقط برای Role مجاز نمایش داده شود.

---

# 70. Audit UI

کاربر مجاز باید بتواند تاریخچه تغییرات را ببیند.

نمونه:

«قیمت از X به Y تغییر کرد»

توسط:

کاربر A

در:

1405/06/25 - 14:30

دلیل:

تخفیف توافق‌شده

---

# 71. امنیت UI

اطلاعات حساس باید بر اساس Permission نمایش داده شوند.

مثلاً:

- اطلاعات مالی
- حساب بانکی
- اسناد هویتی
- قرارداد
- ضمانت

نباید برای همه کاربران قابل مشاهده باشند.

---

# 72. Session

UI باید وضعیت Session را مدیریت کند.

در صورت پایان Session:

«جلسه شما منقضی شده است.»

اطلاعات Draft باید تا حد امکان حفظ شوند.

---

# 73. MVP Screen List

**صفحه‌های MVP (مطابق `MVP_SCOPE.md` §۴، ملاک تصمیم):**

- Login
- Dashboard (حداقلی)
- Customer List / Detail / Create-Edit
- Product List / Detail / Create-Edit / Specifications
- Purchase Request List / Detail / Form / Item Entry / Pricing
- Audit Log List
- Settings (فقط Organization)

**فهرست زیر لیست هدف تمام صفحات (MVP و فازهای بعد) است. هر صفحه‌ای که در فهرست بالا نیست — از جمله Approval، Payment، Voucher، Transport، Loading، Weighbridge، Release، Delivery، Documents، Dispute، Reports و Pre-Invoice — در MVP ساخته نمی‌شود.** Pre-Invoice تصمیم‌شده برای MVP+1 است (ADR-060).

## فهرست هدف (قبلاً «نسخه MVP» نامیده شده بود)

## Authentication

- Login

## Dashboard

- Dashboard

## Customers

- Customer List
- Customer Detail
- Customer Create/Edit

## Products

- Product List
- Product Detail
- Product Create/Edit
- Product Specifications

## Transactions

- Transaction List
- Transaction Detail
- Purchase Request
- Request Item Entry
- Pricing
- Pre-Invoice

## Approval

- Approval List
- Approval Detail

## Payment

- Payment List
- Payment Entry
- Payment Detail

## Voucher

- Voucher Detail

## Transport

- Vehicle List
- Driver List
- Transport Detail

## Loading

- Loading Detail

## Weighbridge

- Origin Weighing
- Destination Weighing
- Weight Discrepancy

## Release

- Release Authorization

## Delivery

- Delivery Detail

## Documents

- Document List
- Document Viewer
- Attachment Upload

## Dispute

- Dispute List
- Dispute Detail
- Return

## Reports

- Dashboard Reports
- Sales Report
- Payment Report
- Receivable Report
- Weight Discrepancy Report

## Settings

- Organization
- Users
- Roles
- Permissions
- Products
- Form Templates
- Business Rules

---

# 74. MVP Purchase Request Flow

**مسیر MVP (Slice اول، مطابق Baseline):**

Login → Dashboard → New Request → Select Customer → Add Products (با مشخصات) → Quantity → Estimated Weight → Price → Discount (مبلغی) → Review → Save Draft → Submit → Retrieve/Detail → Audit

مراحل «شرایط پرداخت»، «مقصد»، «اطلاعات حمل»، «پیوست»، «Pricing/Approval» و «Pre-Invoice» در MVP نیستند (Phase 2؛ Pre-Invoice = MVP+1).

**مسیر هدف کامل (برای مرجع):**

Login
→
Dashboard
→
New Transaction
→
Select Customer
→
Add Products
→
Enter Quantity
→
Enter Estimated Weight
→
Enter Price
→
Enter Discount
→
Select Payment Condition
→
Enter Destination
→
Enter Transport Information
→
Attach Documents
→
Review
→
Save Draft
→
Submit
→
Pricing/Approval
→
Pre-Invoice

---

# 75. Payment Flow (Phase 2 — خارج از MVP)

Transaction
→
Payment
→
Enter Amount
→
Payment Method
→
Reference Number
→
Attach Receipt
→
Submit
→
Finance Confirmation
→
Payment Status Update

---

# 76. Loading Flow (Phase 2 — خارج از MVP)

Transaction
→
Check Availability
→
Check Payment
→
Check Voucher
→
Check Vehicle
→
Check Driver
→
Origin Empty Weight
→
Loading
→
Origin Full Weight
→
Calculate Net Weight
→
Release Authorization
→
Release

---

# 77. Delivery Flow (Phase 2 — خارج از MVP)

Released
→
In Transit
→
Delivered
→
Destination Weighing
→
Compare Weight
→
Settlement
→
Invoice
→
Completed

---

# 78. UI Validation

Validation باید دو سطح داشته باشد:

Client Validation

و

Server Validation

Client validation برای UX است.

Server validation مرجع نهایی Business Rule است.

---

# 79. Unsaved Changes

اگر کاربر از فرم دارای تغییرات ذخیره‌نشده خارج شود:

نمایش:

«تغییرات ذخیره نشده‌اند.»

گزینه‌ها:

- ذخیره
- خروج بدون ذخیره
- بازگشت

---

# 80. Network Status

در Header یا بخش مناسب:

Online
Offline
Syncing
Sync Error

نمایش داده شود.

---

# 81. Sync Center

صفحه‌ای برای مشاهده:

- تغییرات در انتظار Sync
- Sync موفق
- Sync ناموفق
- Conflict

در نظر گرفته شود.

---

# 82. Error Reporting

کاربر باید بتواند خطای مهم را گزارش کند.

اطلاعات فنی برای Developer Log شود.

اما اطلاعات حساس نباید در Log عمومی ذخیره شود.

---

# 83. Performance UX

صفحات List باید Pagination داشته باشند.

در لیست‌های بزرگ:

- Lazy Loading
- Search
- Filter
- Pagination

استفاده شود.

نباید تمام اطلاعات یک‌باره از Server دریافت شود.

---

# 84. UI Architecture

Flutter UI باید از Business Logic جدا باشد.

پیشنهاد:

Presentation
↓
Application
↓
Domain
↓
Data
↓
Infrastructure

Widget نباید مستقیماً به Database متصل شود.

Widget نباید Business Rule مالی یا مجوز خروج را خودش تصمیم‌گیری کند.

---

# 85. Component Reuse

کامپوننت‌های مشترک باید در Design System قرار گیرند.

مثلاً:

TransactionStatusCard

در چند صفحه استفاده شود.

از ساختن چند Widget تقریباً یکسان با منطق متفاوت جلوگیری شود.

---

# 86. Form State

هر فرم باید State مشخص داشته باشد.

نمونه:

- Initial
- Editing
- Saving
- Saved
- Submitting
- Submitted
- Error
- OfflinePendingSync

---

# 87. Navigation Safety

اگر عملیات مهم در حال انجام است:

- جلوگیری از Double Submit
- نمایش Progress
- Disable کردن دکمه در زمان مناسب

اعمال شود.

مثلاً کاربر با دو بار ضربه روی «ثبت پرداخت» نباید دو پرداخت ایجاد کند.

Idempotency در Backend نیز الزامی است.

---

# 88. تاریخچه معامله

کاربر باید بتواند تمام تغییرات مهم را مشاهده کند.

هیچ تغییر مهم مالی یا عملیاتی نباید بدون Traceability باشد.

---

# 89. اصول طراحی برای صنایع مختلف

UI Core باید مستقل از صنعت باشد.

برای صنعت لوله:

Product Specifications ممکن است:

- قطر
- ضخامت
- طول
- استاندارد

باشد.

برای قطعات خودرو:

- برند
- مدل
- سال
- Part Number

باشد.

بنابراین UI باید بر اساس Configuration و Template ساخته شود.

---

# 90. عدم وابستگی به شرکت خاص

TradeFlow نباید در Core شامل:

- نام کارخانه خاص
- لوگوی خاص
- قیمت خاص
- شماره فرم خاص
- قوانین داخلی یک شرکت خاص

باشد.

این موارد باید از Organization Configuration دریافت شوند.

---

# 91. Branding

هر Organization بتواند تنظیم کند:

- Logo
- Company Name
- Address
- Contact
- Colors
- PDF Header
- Footer
- Signature

---

# 92. Customer Pilot UX

برای Pilot Customer:

UI باید تا حد ممکن ساده باشد.

کاربر جدید باید بتواند بدون آموزش طولانی:

- مشتری بسازد
- محصول انتخاب کند
- معامله ثبت کند
- PDF تولید کند
- پرداخت ثبت کند
- وضعیت معامله را مشاهده کند

---

# 93. Feedback

در نسخه Pilot امکان ثبت Feedback وجود داشته باشد.

Feedback:

- مشکل
- پیشنهاد
- تجربه کاربری
- درخواست قابلیت

همراه با:

- صفحه
- نسخه برنامه
- زمان

ثبت شود.

---

# 94. Version Display

نسخه برنامه در Settings نمایش داده شود.

نمونه:

TradeFlow

Version 0.1.0

---

# 95. Update UX

در صورت وجود نسخه جدید:

نمایش:

«نسخه جدید TradeFlow در دسترس است.»

اطلاعات:

- Version
- تغییرات
- حجم
- وضعیت Update

---

# 96. Backward Compatibility

UI باید با نسخه‌های API سازگار طراحی شود.

در صورت تغییر API:

Client قدیمی نباید بدون اطلاع کاربر دچار خرابی ناگهانی شود.

---

# 97. Testing UX

قبل از Release باید حداقل تست شود:

- Login
- Customer
- Product
- Purchase Request
- Multiple Items
- Price
- Discount
- Approval
- Payment
- Partial Payment
- Voucher
- Vehicle
- Driver
- Origin Weighing
- Release
- Delivery
- Destination Weighing
- Weight Discrepancy
- Documents
- PDF
- Offline
- Sync
- Permission
- Audit

---

# 98. Critical UX Rules

1. Payment ≠ Release

2. Voucher ≠ Release

3. Goods Ready ≠ Payment

4. Payment Complete ≠ Goods Ready

5. Loading ≠ Release

6. Origin Weight ≠ Destination Weight

7. Estimated Weight ≠ Actual Weight

8. Draft ≠ Registered Transaction

9. Cancel ≠ Delete

10. Approval ≠ Payment

این تفکیک‌ها باید در UI نیز قابل مشاهده باشند.

---

# 99. UI/UX Priority

اولویت طراحی:

1. Business Correctness
2. Data Integrity
3. Financial Safety
4. Security
5. Auditability
6. Reliability
7. Simplicity
8. Performance
9. Visual Design
10. Convenience

ظاهر زیبا بدون فرآیند درست، فقط یک فرم خوشگل برای تولید اشتباهات است.

---

# 100. Current Phase

Project Phase:

FOUNDATION / SPECIFICATION

در این مرحله:

- UI Code نوشته نمی‌شود.
- Widgetهای نهایی ساخته نمی‌شوند.
- Design جزئی رنگ و فونت هنوز نهایی نمی‌شود.
- Backend پیاده‌سازی نمی‌شود.

ابتدا Specification، Architecture، Data Model، Workflow، API و UI/UX باید هماهنگ شوند.

بعد از تکمیل اسناد، وارد مرحله طراحی فنی و سپس Implementation می‌شویم.

---

# 101. Next Step

پس از تکمیل UI_UX_SPECIFICATION.md:

1. بررسی هماهنگی تمام Specificationها
2. شناسایی تناقض‌ها
3. نهایی‌سازی Domain Model
4. نهایی‌سازی MVP
5. طراحی Repository Structure
6. انتخاب Backend
7. طراحی Database Schema
8. ایجاد Flet Client Project
9. ایجاد Backend Project
10. ایجاد اولین Vertical Slice

اولین Vertical Slice:

Login
→
Customer
→
Product
→
Purchase Request
→
Request Items
→
Price
→
Save
→
Retrieve
→
Audit

باشد.

هدف این است که اولین بخش واقعی سیستم از ابتدا تا انتها کار کند، نه اینکه صد صفحه UI نصفه و نیمه 
بسازیم و بعد بفهمیم فونداسیون را برعکس گذاشته‌ایم.
# UI/UX Gap Closure

## Purpose

This section extends the TradeFlow UI/UX specification to cover the
additional operational, commercial, financial, inventory, support,
exception and enterprise requirements identified during architecture
gap analysis.

The UI must represent the business workflow without making the user
responsible for enforcing rules that belong to the backend/domain layer.

The interface must clearly communicate:

- Current State
- Available Actions
- Blocked Actions
- Required Actions
- Pending Approvals
- Exceptions
- Financial Status
- Inventory Status
- Delivery Status
- Documents
- Audit History

---

# 1. UI Design Principles

TradeFlow UI must follow these principles:

- Persian RTL by default
- Shamsi date display
- 24-hour time display
- Responsive layout
- Clear status indicators
- Minimal unnecessary data entry
- Search before manual typing
- Progressive disclosure for complex information
- Role-based visibility
- Role-based actions
- Confirmation for destructive or sensitive actions
- Clear error messages
- No silent data loss
- No silent status changes
- Consistent terminology
- Consistent buttons and actions
- Accessible touch targets
- Mobile-first transaction screens
- Desktop-friendly management screens

The UI must not contain business rules that contradict backend rules.

---

# 2. Global Application Structure

Main application areas may include:

- Dashboard
- Transactions
- Customers
- Suppliers
- Products
- Inventory
- Pricing
- Payments
- Credit
- Shipments
- Transport
- Weighbridge
- Approvals
- Work Inbox
- Exceptions
- Claims
- Returns
- CRM
- Documents
- Notifications
- Reports
- Support
- Settings

The exact visible menu depends on:

- User Role
- Organization
- Permissions
- Enabled Features
- Subscription Plan

---

# 3. Global Navigation

Navigation should support:

- Main Menu
- Search
- Notifications
- Work Inbox
- User Profile
- Organization Selector where applicable
- Quick Actions

The user should always be able to identify:

- Current Organization
- Current Section
- Current Record
- Current Status

---

# 4. Global Search

TradeFlow should provide global search.

Searchable entities may include:

- Order
- Purchase Request
- Customer
- Supplier
- Product
- Shipment
- Voucher
- Invoice
- Payment
- Vehicle
- Driver
- Claim
- Document

Search results should show:

- Entity Type
- Human-readable Number
- Customer/Supplier
- Date
- Status
- Relevant summary

Search results must respect permissions and organization boundaries.

---

# 5. Dashboard

Dashboard must be role-aware.

Possible widgets:

- Today's Sales
- Open Orders
- Pending Approvals
- Pending Payments
- Credit Holds
- Reserved Inventory
- Low Availability
- Shipments Today
- Loading Queue
- Release Blocks
- Weight Discrepancies
- Open Claims
- Open Exceptions
- SLA Warnings
- Recent Activities

Widgets should be actionable.

Selecting a widget should navigate to the relevant filtered list.

---

# 6. Work Inbox

Work Inbox provides a centralized list of actions requiring the user's attention.

Examples:

- Approval Required
- Payment Review
- Credit Review
- Release Authorization
- Weight Discrepancy
- Claim Review
- Return Approval
- Document Review
- Exception
- SLA Escalation

Each item should display:

- Type
- Priority
- Related Transaction
- Customer
- Created Date
- Due Date
- Current Owner
- Status

Actions:

- Open
- Assign
- Reassign where permitted
- Approve
- Reject
- Resolve
- Escalate

---

# 7. Status Display

Every major transaction screen should clearly display its status.

Status should not depend only on color.

Display should include:

- Text
- Icon where useful
- Visual indicator
- Explanation when necessary

Examples:

PAID

RESERVED

PAYMENT_PENDING

CREDIT_HOLD

LOADING_BLOCKED

RELEASE_AUTHORIZED

DELIVERED

WEIGHT_DISCREPANCY

CLAIM_OPEN

---

# 8. Independent Status Panels

Because transaction processes are independent, the UI should not attempt
to represent everything with one status field.

Transaction detail may show separate status cards:

### Commercial

- Order Status
- Approval Status

### Financial

- Payment Status
- Credit Status
- Voucher Status

### Inventory

- Availability
- Reservation
- Allocation

### Logistics

- Shipment
- Loading
- Delivery

### Weighbridge

- Origin Weight
- Destination Weight
- Reconciliation

### Quality

- Quality Hold
- Claim
- Return

This prevents misleading states such as showing only "Paid" while release
is still blocked.

---

# 9. Customer Screen

Customer screen should include:

- Basic Information
- Contact Information
- Addresses
- Identification
- Tax Information
- Credit Profile
- Credit Limit
- Outstanding Balance
- Overdue Amount
- Guarantees
- Orders
- Payments
- Shipments
- Claims
- Documents
- Communication History
- Activities

Actions depend on permissions.

---

# 10. Customer Creation

Customer creation should support:

- Manual Entry
- Search Existing Customer
- Import
- API/Integration

Duplicate detection should occur before creation.

Potential duplicate warning should show:

- Similar Name
- Phone
- National/Tax ID
- Economic Code
- Other configured identifiers

The user must explicitly confirm creation when a possible duplicate exists.

---

# 11. Customer Credit Screen

Credit screen should display:

- Credit Limit
- Current Exposure
- Available Credit
- Overdue Balance
- Guarantees
- Credit Hold
- Hold Reason
- Expiration Dates

Sensitive financial information must be permission-controlled.

---

# 12. Product Screen

Product screen should support generic products.

Fields may include:

- Product Name
- Category
- Code
- Unit
- Active/Inactive
- Packaging
- Specification Template
- Minimum Order Quantity
- Pricing
- Documents

Industry-specific fields must come from configurable product specifications.

---

# 13. Dynamic Product Specifications

When selecting a product, the UI may display configurable fields.

Example for industrial products:

- Diameter
- Thickness
- Length
- Grade
- Standard

Example for another industry:

- Brand
- Model
- Year
- Part Number

The UI must not hardcode industry-specific fields into the core application.

---

# 14. Purchase Request List

Purchase Request list should support:

- Search
- Filter
- Sort
- Saved Filters
- Date Range
- Customer
- Status
- Product
- Salesperson
- Amount
- Payment Status
- Shipment Status

Actions may include:

- View
- Edit
- Submit
- Cancel
- Duplicate where permitted
- Export

---

# 15. Purchase Request Form

The request form should support:

- Automatic Request Number
- Shamsi Date
- Time
- Customer
- Contact
- Multiple Items
- Product Search
- Quantity
- Unit
- Bundle/Packaging
- Estimated Weight
- Price
- Discount
- Settlement Condition
- Destination
- Transport Information
- Notes
- Attachments

Actions:

- Save Draft
- Submit
- Cancel
- Generate PDF
- Print
- Share

---

# 16. Item Entry UX

Products must be selected from the active product catalog.

When a product is selected:

- Unit should be displayed automatically.
- Configured specifications should appear.
- Packaging rules should be applied.
- Quantity validation should occur.
- Minimum quantity should be checked.
- Availability should be displayed where permitted.

The user should not need to repeatedly type information already stored in
master data.

---

# 17. Order Summary

Before submission, display a clear summary:

- Customer
- Items
- Quantity
- Estimated Weight
- Price
- Discount
- Tax
- Freight
- Total
- Settlement Condition
- Destination

The user must be able to identify important errors before submission.

---

# 18. Pricing UI

Pricing screen should show:

- Base Price
- Price Source
- Customer Price
- Agreement Price
- Discount
- Final Price
- Currency
- Effective Date

If price is outside configured rules:

Display:

PRICE OVERRIDE REQUIRED

and show:

- Allowed Range
- Entered Price
- Difference
- Reason
- Approval Status

---

# 19. Discount UI

Discount entry should display:

- Discount Type
- Discount Value
- Final Amount
- Approval Requirement

If approval is required:

- Show Pending Approval
- Disable unauthorized completion actions
- Display Approver where permitted

---

# 20. Approval Screen

Approval screen should display:

- Transaction Summary
- Customer
- Amount
- Discount
- Credit
- Inventory
- Requested Action
- Supporting Documents
- Approval History

Actions:

- Approve
- Reject
- Request Revision
- Delegate where authorized

Rejection must require a reason when configured.

---

# 21. Approval Timeline

Every approval should be visible in a timeline.

Example:

Submitted
↓
Sales Approval
↓
Commercial Approval
↓
Management Approval

Each step displays:

- Person
- Date/time
- Decision
- Reason

---

# 22. Order Revision UI

When a registered transaction is changed:

Display:

- Current Version
- New Version
- Changed Fields
- Previous Value
- New Value
- Change Reason
- Re-approval Requirement

Users should be able to compare versions.

Historical versions must remain accessible.

---

# 23. Payment Screen

Payment screen should support:

- Full Payment
- Partial Payment
- Multiple Payments
- Weight-based final payment
- Credit transaction

Display:

- Total Amount
- Paid Amount
- Remaining Amount
- Payment Method
- Payment Reference
- Payment Date
- Verification Status

---

# 24. Payment Verification

Finance or authorized users should see:

- Payment Evidence
- Amount
- Payer
- Bank/Reference
- Related Transaction
- Current Verification Status

Actions:

- Confirm
- Reject
- Request Review
- Reverse where authorized

---

# 25. Credit Transaction UI

For credit transactions display:

- Credit Limit
- Current Exposure
- New Exposure
- Available Credit
- Overdue Amount
- Guarantee
- Approval Status

If credit hold applies:

Display clearly:

CREDIT HOLD

with the reason.

---

# 26. Voucher Screen

Voucher screen should display:

- Voucher Number
- Transaction
- Customer
- Amount
- Payment Status
- Credit Status
- Issued By
- Issue Date
- Related Shipment

Voucher cancellation or correction must display its history.

---

# 27. Inventory Screen

Inventory should distinguish:

- Physical
- Available
- Reserved
- Allocated
- In Production
- In Transit
- Damaged
- Quarantined
- Returned

Users must not confuse physical stock with available stock.

---

# 28. Inventory Reservation UI

Reservation screen should show:

- Requested Quantity
- Available Quantity
- Reserved Quantity
- Remaining Quantity
- Reservation Expiration
- Related Order

Actions:

- Reserve
- Release
- Modify where permitted

Reservation conflicts should be clearly displayed.

---

# 29. ATP Display

Where applicable:

Display:

Available Now

+

Expected Supply

-

Existing Commitments

=

Available to Promise

ATP must include an explanation or details view where practical.

---

# 30. Shipment Screen

Shipment detail should display:

- Original Order
- Shipment Number
- Customer
- Items
- Quantity
- Reserved Quantity
- Vehicle
- Driver
- Origin
- Destination
- Loading Status
- Weighing Status
- Release Status
- Delivery Status

---

# 31. Partial Shipment UI

For partially fulfilled orders display:

Ordered: X

Reserved: X

Shipped: X

Delivered: X

Remaining: X

The remaining quantity should be clearly identified as:

BACKORDER

when applicable.

---

# 32. Backorder Screen

Backorder should display:

- Original Order
- Original Item
- Requested Quantity
- Fulfilled Quantity
- Remaining Quantity
- Expected Availability
- Reservation Status
- Next Shipment

---

# 33. Transport Screen

Transport information:

- Vehicle
- Driver
- Origin
- Destination
- Freight Cost
- Freight Agreement
- Responsibility
- Documents

The interface must support seller-arranged and customer-arranged transport.

---

# 34. Vehicle and Driver Screen

Vehicle:

- Plate Number
- Type
- Capacity
- Owner
- Documents
- Validity

Driver:

- Name
- Phone
- Identification
- Documents
- Validity

Expired required documents must be clearly marked.

---

# 35. Loading Queue

Loading queue should display:

- Shipment
- Customer
- Vehicle
- Driver
- Product
- Quantity
- Payment Status
- Voucher Status
- Reservation Status
- Loading Status
- Release Status
- Blocking Reason

Blocked loads must be visibly distinguished.

---

# 36. Loading Validation

Before loading, the UI should present a checklist.

Example:

[✓] Order Approved

[✓] Payment Confirmed

[✓] Credit Approved

[✓] Voucher Issued

[✓] Inventory Available

[✓] Reservation Active

[✓] Vehicle Valid

[✓] Driver Valid

[✓] Documents Complete

If an item fails:

[✗] Payment Not Confirmed

The interface must explain the blocking reason.

---

# 37. Origin Weighbridge UI

Weighbridge screen should support:

Step 1:

Vehicle Identification

Step 2:

Empty Weight

Step 3:

Loading

Step 4:

Full Weight

Step 5:

Net Weight

Formula:

Net Weight = Full Weight - Empty Weight

The system should preserve the source ticket/document.

---

# 38. Destination Weighbridge UI

Destination screen should support:

- Full Weight
- Empty Weight
- Net Weight
- Ticket
- Date/time
- Location
- Evidence

Origin and destination results should be shown together.

---

# 39. Weight Reconciliation Screen

Display:

Origin Net Weight

Destination Net Weight

Difference

Difference %

Tolerance

Result

Possible result:

WITHIN TOLERANCE

or

DISCREPANCY

If discrepancy occurs, provide direct access to the related exception.

---

# 40. Release Authorization Screen

Release screen should show all conditions.

Example:

Payment: CONFIRMED

Voucher: ISSUED

Inventory: RESERVED

Vehicle: VALID

Driver: VALID

Weight: VERIFIED

Quality: CLEAR

Release: AUTHORIZED

If blocked:

Release: BLOCKED

Reason: PAYMENT NOT CONFIRMED

---

# 41. Release Override

If override is permitted:

Display:

- Block Reason
- Override Authority
- Reason Required
- Warning
- Confirmation

Override must never be hidden behind an ordinary action button.

---

# 42. Delivery Screen

Delivery screen should display:

- Shipment
- Vehicle
- Driver
- Destination
- Delivery Status
- Delivery Date
- Receiver
- POD
- Destination Weight
- Exceptions

---

# 43. Proof of Delivery UI

POD may contain:

- Receiver Name
- Signature
- Date/time
- Photos
- Delivery Document
- Notes
- Optional Location

The user should be able to view uploaded evidence.

---

# 44. Exception Center

Exception Center should provide a unified list of operational problems.

Filters:

- Type
- Severity
- Status
- Owner
- Date
- Customer
- Transaction
- SLA

Examples:

- Weight Discrepancy
- Payment Problem
- Credit Hold
- Inventory Shortage
- Quality Problem
- Delivery Problem
- Integration Failure

---

# 45. Exception Detail

Exception detail should contain:

- Problem Description
- Related Transaction
- Severity
- Owner
- Created Date
- Due Date
- Evidence
- Comments
- Actions
- Resolution
- Audit History

---

# 46. Claim Screen

Claim should display:

- Customer
- Shipment
- Product
- Problem Type
- Description
- Evidence
- Status
- Assigned Person
- Decision
- Financial Effect

Claim workflow should be visible through a timeline.

---

# 47. Return Screen

Return should display:

- Original Shipment
- Product
- Quantity
- Reason
- Approval
- Transport
- Receipt
- Inspection
- Inventory Adjustment
- Financial Adjustment

---

# 48. Reconciliation Screen

Reconciliation should provide a unified comparison.

Examples:

Order ↔ Payment

Order ↔ Voucher

Order ↔ Shipment

Shipment ↔ Delivery

Origin Weight ↔ Destination Weight

Invoice ↔ Payment

Customer Balance ↔ Transactions

Differences should be directly actionable.

---

# 49. CRM Screen

CRM should support:

- Leads
- Opportunities
- Customer Activities
- Follow-ups
- Notes
- Segments
- Communication History

Activity types may include:

- Phone Call
- Meeting
- Message
- Follow-up
- Offer
- Visit
- Other configured activity

---

# 50. Lead Screen

Lead fields:

- Name
- Company
- Contact
- Source
- Product Interest
- Estimated Volume
- Estimated Value
- Owner
- Status
- Next Action

Lead may be converted to a customer according to permissions.

---

# 51. Opportunity Screen

Opportunity may display:

- Customer
- Estimated Value
- Product
- Quantity
- Expected Close Date
- Probability where configured
- Owner
- Activities
- Current Stage

The interface must not imply that an opportunity is a confirmed order.

---

# 52. Notification Center

Notification Center should contain:

- Business Notifications
- Approval Notifications
- Payment Notifications
- Delivery Notifications
- Exception Notifications
- System Notifications

Users should be able to:

- Mark Read
- Mark Unread
- Open Related Record
- Configure Preferences where permitted

---

# 53. Notification Preferences

Users may configure channels where supported:

- In-App
- Push
- SMS
- Email

Preferences should distinguish important mandatory notifications from optional
notifications.

---

# 54. Document Center

Documents should be organized by:

- Transaction
- Customer
- Shipment
- Payment
- Vehicle
- Driver
- Claim
- Return
- Other Entity

Document types may include:

- Request Form
- Pre-Invoice
- Invoice
- Voucher
- Payment Receipt
- Vehicle Document
- Driver Document
- Weighbridge Ticket
- Quality Photo
- POD
- Contract
- Check
- Guarantee

---

# 55. Attachment UX

Attachment screen should support:

- Camera
- Gallery
- File Picker
- Preview
- Upload Progress
- Retry
- Delete where permitted
- Version
- Metadata

Sensitive documents must require appropriate permission.

---

# 56. PDF and Print

PDF generation must be independent of messaging applications.

Generated PDF should support:

- Organization Logo
- Header
- Footer
- Transaction Number
- Date
- Customer
- Items
- Financial Information
- Signatures
- Terms
- Attachments or references where appropriate

PDF must be generated from structured data rather than screenshots.

---

# 57. Share Workflow

Generic share flow:

Transaction

↓

Generate PDF

↓

Share

↓

Select Available Application

Examples:

- WhatsApp
- Bale
- Email
- Other Supported App

TradeFlow core transaction logic must remain independent of the selected
messaging application.

---

# 58. Import / Export

Management screens should support where authorized:

- Excel Import
- CSV Import
- Excel Export
- CSV Export
- PDF Export

Import process should include:

1. Upload
2. Validate
3. Show Errors
4. Preview
5. Confirm
6. Import
7. Result Summary

Invalid rows must be identifiable.

---

# 59. Bulk Operations

Authorized users may perform bulk actions.

Examples:

- Activate Products
- Deactivate Products
- Assign Owner
- Export
- Archive
- Update Status where permitted

Sensitive bulk operations require confirmation.

---

# 60. Saved Views and Filters

Users should be able to save frequently used filters.

Examples:

- Today's Pending Payments
- My Pending Approvals
- Blocked Loads
- Open Claims
- Customers with Overdue Balance

Saved views should respect permissions.

---

# 61. Audit Timeline

Each important transaction should provide a timeline.

Example:

Created

↓

Price Changed

↓

Approved

↓

Payment Confirmed

↓

Voucher Issued

↓

Shipment Created

↓

Loaded

↓

Released

↓

Delivered

↓

Settled

The timeline should show:

- User
- Date/time
- Action
- Previous State
- New State
- Reason where applicable

---

# 62. Communication History

Communication history should show authorized records of:

- Calls
- Messages
- Emails
- Shared Documents
- Notifications
- Customer Activities

TradeFlow should not claim to contain the full contents of an external
messaging service unless the relevant integration explicitly provides that data.

---

# 63. Offline UI

When offline:

Display a clear connection indicator.

Users should be able to see:

- Offline Mode
- Pending Sync
- Sync Errors
- Last Successful Sync

Operations that require online authorization must be clearly disabled or
identified.

---

# 64. Synchronization Center

Sync Center should display:

- Pending Operations
- Successful Operations
- Failed Operations
- Conflicts
- Last Sync Time

Conflict records should allow authorized users to review the problem.

---

# 65. Error Handling

Errors must be understandable.

Avoid displaying only technical messages such as:

500 Internal Server Error

Instead display:

"عملیات انجام نشد. ارتباط با سرور برقرار نشد."

Where appropriate, provide:

- Retry
- Reference ID
- More Details for authorized users

Sensitive technical information must not be exposed to ordinary users.

---

# 66. Technical Issue Reporting

Users should be able to report an issue from the relevant screen.

Automatically include where permitted:

- Screen
- Transaction ID
- Application Version
- Device
- Time
- Correlation ID

The user should add:

- Description
- Screenshot
- Optional Attachment

Passwords, tokens and sensitive authentication data must never be included.

---

# 67. Loading States

Every network operation should have clear states:

- Loading
- Success
- Failure
- Retry

The interface must prevent accidental duplicate submission while a critical
operation is being processed.

---

# 68. Empty States

Empty screens should explain what is missing.

Example:

"No shipment has been created for this order."

Where permitted, provide an appropriate next action.

---

# 69. Confirmation Dialogs

Confirmation is required for sensitive actions such as:

- Cancel Order
- Cancel Voucher
- Release Reservation
- Approve Credit
- Reject Approval
- Authorize Release
- Return
- Financial Adjustment
- Archive
- Bulk Operation

Confirmation should clearly state the consequence.

---

# 70. Delete Rules in UI

### Unsaved Draft

Clear/Delete may be available.

### Saved Draft

Delete may be allowed according to permission.

### Registered Transaction

Delete button should normally not exist.

Use:

CANCEL

or

REVERSE

or

ARCHIVE

according to the business process.

Historical records must remain traceable.

---

# 71. Role-Based UI

UI actions should depend on permissions.

Examples:

Salesperson:

- Create Order
- Edit Draft
- Request Approval
- View Customer
- View Pricing

Finance:

- Review Payment
- Confirm Payment
- Issue Voucher
- View Financial Records

Warehouse:

- View Loading
- Record Loading
- Record Weight

Authorized Release User:

- Review Conditions
- Authorize Release

Manager:

- Approve
- Override where permitted
- View Reports

Customer:

- View Own Orders
- Pay
- View Documents
- Track Shipment

---

# 72. Customer Portal UI

Customer portal may include:

- Dashboard
- New Request
- Orders
- Payments
- Shipments
- Delivery
- Documents
- Claims
- Balance
- Profile

Customer must only access authorized organization data.

---

# 73. Supplier Portal UI

Supplier portal may include:

- Purchase Orders
- Confirmation
- Availability
- Shipments
- Documents
- Invoices
- Payments

Supplier access must be isolated.

---

# 74. Multi-Organization UI

> **MVP (ADR-059):** a user belongs to exactly one organization, so there is no organization switching in the MVP; the UI only displays the current organization. This section applies if a membership model (multi-organization users) is introduced by a later ADR.

If a user belongs to multiple organizations:

Display the current organization clearly.

Organization switching must:

- Revalidate permissions
- Reload relevant data
- Prevent cross-organization data leakage

Transactions must never accidentally be created under the wrong organization.

---

# 75. Subscription and Feature UI

Where subscription management is enabled:

Display:

- Current Plan
- Active Features
- Usage
- Limits
- Renewal
- Upgrade
- Downgrade

Disabled features should display an understandable explanation.

Historical transactions must remain accessible according to retention rules.

---

# 76. Feature Flags

Features controlled by feature flags must:

- Appear only when enabled
- Not break navigation when disabled
- Not expose unfinished functionality
- Be controlled by authorized backend configuration

---

# 77. Security UI

Security-related screens may include:

- Login
- Logout
- Password Change
- Password Reset
- 2FA
- Active Sessions
- Session Revocation
- Security Events

Critical security actions should require appropriate confirmation.

---

# 78. Session Management

Users should be able to view active sessions where supported.

Possible information:

- Device
- Browser/Application
- Last Activity
- Login Time

Users may revoke sessions according to permissions.

---

# 79. Master Data Management UI

Authorized users may manage:

- Products
- Categories
- Units
- Customers
- Suppliers
- Vehicle Types
- Payment Methods
- Currencies
- Tax Definitions
- Status Configurations
- Workflow Rules

Changes must be permission-controlled and audited.

---

# 80. Form Template UI

Organizations may configure forms.

Configuration may include:

- Field Name
- Field Type
- Required/Optional
- Order
- Visibility
- Default Value
- Validation
- Section
- Terms
- Header
- Footer
- Logo
- Signature

Changes must be versioned.

---

# 81. Organization Branding

Organization settings may include:

- Name
- Logo
- Address
- Phone
- Tax Information
- Header
- Footer
- Signature
- PDF Style

Branding changes must not alter historical documents unless a new document
version is explicitly generated.

---

# 82. Multi-Currency UI

Where enabled:

Display:

- Transaction Currency
- Base Currency
- Exchange Rate
- Exchange Rate Date
- Foreign Amount
- Base Amount

Currency must never be inferred silently.

---

# 83. Tax UI

Tax information may include:

- Tax Type
- Rate
- Taxable Amount
- Tax Amount
- Tax Exemption
- Tax Registration Status

Tax calculations must be validated server-side.

---

# 84. Cost and Margin UI

Authorized users may view:

- Revenue
- Direct Cost
- Freight Cost
- Other Cost
- Gross Margin
- Margin %

Sensitive profitability information must be permission-controlled.

---

# 85. Accessibility

The UI should support:

- Readable typography
- Sufficient contrast
- Keyboard navigation on desktop
- Touch-friendly controls
- Clear focus states
- Text alternatives where applicable
- Avoiding color-only status indicators

---

# 86. Responsive Design

The same business workflow must adapt to:

### Mobile

- Compact cards
- Bottom actions where appropriate
- Step-based forms
- Camera/file capture
- Touch-friendly controls

### Desktop

- Tables
- Multi-column layouts
- Advanced filters
- Bulk operations
- Reporting
- Management dashboards

The underlying business logic must remain identical.

---

# 87. Mobile Transaction Flow

For complex transactions, mobile UI should use logical steps.

Example:

Customer

↓

Products

↓

Pricing

↓

Payment

↓

Transport

↓

Documents

↓

Review

↓

Submit

Users should be able to move backward without losing entered data.

---

# 88. Draft Auto-Save

Where appropriate, complex forms should support automatic draft saving.

The UI should show:

- Saved
- Saving
- Offline Draft
- Sync Pending
- Save Error

Auto-save must not be interpreted as transaction submission.

---

# 89. Data Validation

Validation should occur:

- At field level
- At form level
- At submission
- On server

Validation messages should identify:

- Problem
- Field
- Required action

Server validation remains authoritative.

---

# 90. Performance UX

The interface should:

- Load important content first
- Paginate large lists
- Avoid unnecessary full reloads
- Cache safe read-only data
- Show progress for long operations
- Prevent duplicate actions

Large tables should support pagination or virtualized rendering.

---

# 91. Privacy

Sensitive data should be protected in the UI.

Examples:

- Financial information
- National identifiers
- Bank information
- Guarantees
- Personal documents

Depending on permissions, data may be:

- Hidden
- Masked
- Restricted
- Fully visible

---

# 92. Audit Visibility

Users should only see audit information permitted by their role.

The UI must not allow ordinary users to edit audit history.

---

# 93. QR / Barcode

Where enabled, QR/Barcode may be used for:

- Product
- Shipment
- Voucher
- Vehicle
- Document
- Order

Scanning should open the relevant record only after permission validation.

---

# 94. Future OCR

OCR may later support extraction from:

- National ID
- Vehicle Documents
- Invoices
- Weighbridge Tickets
- Other configured documents

OCR results must always be treated as extracted data requiring validation,
not automatically as authoritative truth.

---

# 95. Future Geolocation

Where enabled and legally/organizationally permitted:

Location may support:

- Delivery
- Vehicle Tracking
- Proof of Delivery
- Operational Verification

Location access must be explicit and permission-controlled.

---

# 96. Update Management UI

The application should display:

- Current Version
- Minimum Supported Version
- Available Update
- Release Notes

Critical updates may require the user to update before continuing.

Business data must remain protected during application updates.

---

# 97. Support Center

Support Center should distinguish:

- Technical Error
- Crash
- Business Error
- User Bug
- Support Request
- Feature Request
- Complaint

Each type should follow its appropriate workflow.

---

# 98. User Feedback

Users may submit:

- Feedback
- Problem Report
- Feature Request

Feedback should optionally include:

- Screen
- Transaction
- Screenshot
- Application Version

---

# 99. UI Audit Requirements

The UI must not allow the following to happen silently:

- Price change
- Discount override
- Credit override
- Payment confirmation
- Voucher cancellation
- Reservation release
- Loading override
- Release override
- Financial adjustment
- Return approval
- Order cancellation

Each sensitive action must provide appropriate confirmation and auditability.

---

# 100. UI / API Boundary

The UI is responsible for:

- Presentation
- User Input
- Navigation
- Local Validation
- User Feedback
- Offline Queue Management where applicable

The backend/domain layer is responsible for:

- Authorization
- Financial Validation
- Inventory Validation
- Pricing Rules
- Credit Rules
- Approval Rules
- Release Rules
- Settlement
- Audit
- State Transitions
- Data Integrity

The UI must never be the sole enforcement mechanism for critical business rules.

---

# 101. UI Testing

UI testing must cover:

### Functional

- Create Draft
- Edit Draft
- Submit
- Approve
- Reject
- Pay
- Partial Pay
- Reserve
- Ship
- Load
- Weigh
- Release
- Deliver
- Reconcile
- Claim
- Return
- Cancel

### Negative

- Invalid Customer
- Invalid Product
- Insufficient Inventory
- Credit Hold
- Missing Payment
- Missing Voucher
- Invalid Vehicle
- Invalid Driver
- Missing Document
- Weight Discrepancy
- Permission Denied
- Network Failure

### Offline

- Create Draft Offline
- Sync
- Conflict
- Retry
- Duplicate Prevention

### Security

- Unauthorized Screen
- Unauthorized Action
- Session Expiration
- Revoked Session
- Organization Boundary

---

# 102. UI Consistency Requirement

The same concepts must use the same terminology throughout the application.

For example:

"پرداخت تأیید شد"

must not appear elsewhere as:

"تسویه شد"

unless those terms represent genuinely different business states.

Similarly:

"مجوز خروج"

must remain distinct from:

"بارگیری"

and

"تحویل"

because these are separate workflow events.

---

# 103. MVP UI Scope

Initial MVP should focus on the first complete vertical slice:

Login

↓

Customer

↓

Product

↓

Purchase Request

↓

Multiple Items

↓

Price

↓

Save Draft

↓

Submit

↓

Retrieve

↓

Basic Audit

The MVP UI should establish reusable components for:

- Lists
- Detail Pages
- Forms
- Status Cards
- Timelines
- Attachments
- Search
- Pagination
- Error Handling
- Permissions

---

# 104. Phase 2 UI Scope

Phase 2 may add:

- Inventory
- Reservation
- ATP
- Approval
- Payment
- Credit
- Voucher
- Shipment
- Loading
- Weighbridge
- Release
- Delivery
- POD
- Claims
- Returns
- Exceptions
- Notifications
- Work Inbox
- CRM
- Reports

---

# 105. Future UI Scope

Future versions may include:

- Customer Portal
- Supplier Portal
- Subscription Management
- Advanced CRM
- OCR
- QR/Barcode
- Geolocation
- Advanced Integrations
- Advanced Analytics
- Advanced Automation
- Digital Signature

---

# 106. Final UI/UX Principle

TradeFlow UI must make the business process understandable to the user.

The interface should answer three questions at every important point:

1. What has happened?
2. What is preventing the next step?
3. What can I do now?

The UI must make exceptions visible, preserve transaction history,
prevent accidental actions, and provide the correct next action according
to the user's role and permissions.

The goal is not to create a collection of attractive screens.

The goal is to create a reliable operational interface over the
TradeFlow business domain.

---

# Current UI/UX Status

The TradeFlow UI/UX specification now covers:

- Navigation
- Dashboard
- Global Search
- Work Inbox
- Status Architecture
- Customer
- Product
- Dynamic Specifications
- Purchase Request
- Pricing
- Discount
- Approval
- Order Revision
- Payment
- Credit
- Voucher
- Inventory
- Reservation
- ATP
- Shipment
- Partial Shipment
- Backorder
- Transport
- Vehicle
- Driver
- Loading
- Weighbridge
- Release
- Delivery
- POD
- Reconciliation
- Exceptions
- Claims
- Returns
- CRM
- Notifications
- Documents
- PDF
- Sharing
- Import/Export
- Bulk Operations
- Offline
- Synchronization
- Technical Support
- Security
- Subscription
- Customer Portal
- Supplier Portal
- Form Templates
- Organization Branding
- Multi-Currency
- Tax
- Cost/Margin
- Accessibility
- Responsive Design
- QR/Barcode
- Future OCR
- Future Geolocation
- Update Management
- UI Testing
- MVP / Phase 2 / Future separation

The UI/UX specification must remain aligned with:

PROJECT_SPECIFICATION.md

DATA_MODEL.md

WORKFLOW.md

API_SPECIFICATION.md

AGENTS.md

No implementation should begin by inventing UI behavior that contradicts
these documents.