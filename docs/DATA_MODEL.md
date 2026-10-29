# TradeFlow - Data Model

> **وضعیت سند — همگام‌شده با Baseline Hardened (001 + 002 + Runner) و ADR-056 تا ADR-063.**
>
> این سند دو لایه دارد:
> 1. **مدل مفهومی هدف** (بخش‌های ۱ تا ۵۹ و «Data Model Gap Closure»): تصویر کامل و بلندمدت دامنه. اینها Schema اجرایی نیستند و نام‌ها و ستون‌های آن لزوماً با دیتابیس یکی نیست.
> 2. **مدل فیزیکی اجرایی MVP** (بخش «MVP Physical Data Model — Baseline Hardened» در انتهای سند): دقیقاً همان چیزی که `001_initial_mvp.sql` و `002_harden_mvp.sql` می‌سازند.
>
> **قاعده اولویت:** برای MVP، در هر تعارض، مدل فیزیکی انتهای سند و Migration‌ها معتبرند؛ سپس `MVP_SCOPE.md`. ورود هر چیز از مدل مفهومی به MVP نیاز به ADR و Migration جدید دارد.

## نگاشت نام‌های مفهومی به مدل فیزیکی MVP

| مفهوم (بخش‌های مفهومی) | در MVP |
|---|---|
| Party | `customers` |
| Order / Purchase Request، `order_number` | `purchase_requests`، `request_number` (با شمارندهٔ ADR-057) |
| OrderItem، `package_count`، `price`، `final_amount` | `purchase_request_items`، `bundle_count`، `unit_price`، `line_total` |
| `specification_values` روی OrderItem | ستون `specifications` (آرایهٔ JSONB، Snapshot، ADR-061 C6) |
| `active` | `is_active` |
| AuditLog `old_value` / `new_value` | `audit_logs.old_data` / `new_data` |
| `organization_code` | ستون `organizations.code` — در مدل پایهٔ 001+002 **وجود نداشت**؛ در Migration 003 (`003_org_code_and_username.sql`، ADR-059) اضافه شده است |
| PreInvoice | **در MVP وجود ندارد**؛ تصمیم‌شده برای MVP+1 (ADR-060) |
| Price، Discount، Approval، Revision، Currency، Payment و … | Phase 2 / Future؛ در MVP نیستند |
| Currency / Precision قابل تنظیم | MVP: ریال، `NUMERIC(20,0)` (ADR-058). ارز و دقت قابل تنظیم = ADR-042 (Future) |

---

## 1. هدف

این سند مدل داده‌های اصلی نرم‌افزار TradeFlow را مشخص می‌کند.

TradeFlow یک نرم‌افزار عمومی مدیریت معاملات و گردش فروش است و نباید به یک صنف خاص، مانند آهن و فولاد، وابسته باشد.

صنایع مختلف باید بتوانند محصولات، مشخصات فنی، فرم‌ها، واحدها، شرایط فروش و فرآیندهای خود را تعریف و استفاده کنند.

صنعت آهن و فولاد اولین سناریوی واقعی برای طراحی و آزمایش سیستم است، اما هسته سیستم عمومی خواهد بود.

---

# 2. اصول اصلی مدل داده

1. اطلاعات هر سازمان از سازمان‌های دیگر جدا باشد.
2. محصول در فرم درخواست به صورت انتخابی از فهرست محصولات فعال انتخاب شود.
3. ثبت نام محصول به صورت متن آزاد در فرم اصلی درخواست مجاز نباشد.
4. کاربران دارای مجوز بتوانند محصول جدید تعریف کنند.
5. محصولات غیرفعال در درخواست‌های جدید نمایش داده نشوند.
6. غیرفعال کردن محصول نباید سوابق معاملات قبلی را حذف یا تغییر دهد.
7. اطلاعات تخصصی هر صنف نباید در هسته سیستم به صورت ثابت و سخت‌کد شده قرار گیرد.
8. مشخصات فنی کالا باید قابل تعریف و توسعه باشد.
9. درخواست، قیمت، تأیید، پرداخت، حواله، بارگیری، باسکول، خروج، تحویل و تسویه موجودیت‌ها و وضعیت‌های مستقل داشته باشند.
10. هیچ عملیات مهم مالی یا عملیاتی نباید بدون ثبت سابقه تغییرات انجام شود.
11. تاریخ در دیتابیس به صورت استاندارد ذخیره شود و نمایش تاریخ برای کاربر به صورت شمسی باشد.
12. فایل‌ها و اسناد باید به معامله یا موجودیت مرتبط متصل باشند.
13. حذف اطلاعات مهم معاملاتی نباید باعث از بین رفتن سابقه شود.
14. مدل داده باید قابلیت توسعه برای چند شرکت و چند صنف را داشته باشد.

---

# 3. Organization

نماینده شرکت، فروشگاه، کارخانه یا کسب‌وکاری است که از TradeFlow استفاده می‌کند.

## Fields

- id
- organization_code
- name
- legal_name
- organization_type
- industry_id
- national_id
- economic_code
- registration_number
- postal_code
- address
- province
- city
- phone
- mobile
- email
- website
- logo
- active
- created_at
- updated_at

## Organization Type

نمونه‌ها:

- Factory
- TradingCompany
- Store
- Wholesale
- Retail
- ServiceProvider
- Other

---

# 4. Industry

صنف یا حوزه فعالیت سازمان.

نمونه:

- آهن و فولاد
- قطعات خودرو
- مصالح ساختمانی
- تجهیزات صنعتی
- مواد اولیه
- کالاهای مصرفی
- خدمات
- سایر

Industry نباید باعث ایجاد منطق سخت‌کد شده در هسته سیستم شود.

---

# 5. User

کاربر سیستم.

## Fields

- id
- organization_id
- username
- mobile
- email
- first_name
- last_name
- password_hash
- active
- last_login_at
- created_at
- updated_at

> **وضعیت (ADR-059):** در MVP هر کاربر به یک سازمان تعلق دارد و ورود با `organization_code + username + password` انجام می‌شود. `username` فقط درون یک سازمان یکتاست.

---

# 6. Role

نقش کاربر.

نمونه نقش‌ها:

- SystemAdmin
- OrganizationAdmin
- Owner
- Manager
- SalesManager
- SalesEmployee
- Finance
- Warehouse
- Weighbridge
- Freight
- Buyer
- Driver
- Other

نقش‌ها باید قابل توسعه باشند.

---

# 7. Permission

مجوز انجام عملیات.

نمونه:

- product.create
- product.edit
- product.activate
- product.deactivate
- customer.create
- customer.edit
- order.create
- order.edit
- price.edit
- discount.approve
- credit.approve
- payment.confirm
- voucher.create
- loading.approve
- release.approve
- weighing.register
- dispute.manage
- return.approve
- report.view

مجوزها باید در سمت Backend نیز کنترل شوند و فقط به رابط کاربری وابسته نباشند.

---

# 8. Party

طرف معامله یا طرف مرتبط با عملیات.

Party می‌تواند شخص، شرکت، مشتری، فروشنده، تأمین‌کننده یا سایر طرف‌های تجاری باشد.

## Fields

- id
- organization_id
- party_type
- person_or_company
- name
- national_id
- economic_code
- registration_number
- postal_code
- province
- city
- address
- phone
- mobile
- email
- banking_information
- tax_information
- notes
- active
- created_at
- updated_at

Party باید قابلیت استفاده مجدد در معاملات مختلف را داشته باشد.

---

# 9. Product

تعریف عمومی کالا یا خدمت.

## Fields

- id
- product_code
- name
- category_id
- industry_id
- default_unit_id
- description
- active
- created_at
- updated_at

Product نباید دارای فیلدهای اختصاصی یک صنف خاص باشد.

مثلاً نباید ستون‌های ثابت زیر در هسته سیستم ایجاد شود:

- pipe_diameter
- pipe_thickness
- pipe_length

این اطلاعات باید از طریق Product Specification مدیریت شوند.

---

# 10. OrganizationProduct

رابط بین سازمان و محصول.

این موجودیت مشخص می‌کند یک سازمان چه محصولی را فعال کرده و چگونه آن را ارائه می‌کند.

## Fields

- id
- organization_id
- product_id
- internal_product_code
- sales_unit_id
- purchase_unit_id
- active
- default_price
- notes
- created_at
- updated_at

یک محصول عمومی می‌تواند توسط سازمان‌های مختلف با شرایط متفاوت استفاده شود.

---

# 11. ProductCategory

دسته‌بندی محصولات.

## Fields

- id
- organization_id
- industry_id
- parent_id
- name
- code
- description
- active

دسته‌بندی می‌تواند سلسله‌مراتبی باشد.

مثال:

آهن و فولاد
→ لوله
→ لوله گاز

یا:

قطعات خودرو
→ سیستم ترمز
→ لنت

---

# 12. Unit

واحد اندازه‌گیری.

نمونه:

- کیلوگرم
- تن
- عدد
- بسته
- شاخه
- متر
- لیتر
- جعبه
- ست
- دستگاه

## Fields

- id
- name
- symbol
- decimal_precision
- active

واحدها نباید فقط برای آهن طراحی شوند.

---

# 13. ProductSpecificationTemplate

قالب مشخصات فنی محصول یا گروه محصولات.

## Fields

- id
- organization_id
- category_id
- name
- description
- active
- version
- created_at
- updated_at

---

# 14. ProductSpecificationField

فیلد مشخصات فنی.

## Fields

- id
- template_id
- name
- field_code
- field_type
- unit_id
- required
- searchable
- sort_order
- options
- active

## Field Types

نمونه:

- text
- number
- decimal
- integer
- select
- multi_select
- boolean
- date
- measurement

---

# 15. ProductSpecificationValue

مقدار مشخصات فنی یک محصول.

## Fields

- id
- product_id
- specification_field_id
- value
- created_at
- updated_at

مثلاً برای یک محصول:

قطر = 2 اینچ  
ضخامت = 2.5 میلی‌متر  
طول = 6 متر

ولی برای یک محصول دیگر می‌تواند:

برند = X  
مدل = Y  
سال = 1405

باشد.

---

# 16. ProductPackaging

اطلاعات بسته‌بندی محصول.

## Fields

- id
- organization_product_id
- packaging_type
- pieces_per_package
- estimated_weight
- weight_unit_id
- description
- active

وزن تقریبی بسته‌بندی با وزن واقعی باسکول متفاوت است.

---

# 17. Inventory / Availability

وضعیت موجودی یا آماده بودن کالا.

## Fields

- id
- organization_id
- organization_product_id
- quantity
- unit_id
- estimated_weight
- available_quantity
- availability_status
- source
- recorded_at
- notes

سیستم باید بتواند موجودی تقریبی و واقعی را از هم تفکیک کند.

---

# 18. Order / Purchase Request

موجودیت اصلی درخواست خرید / معامله.

در مراحل اولیه می‌تواند از نوع درخواست خرید شروع شود و در ادامه وارد فرآیند فروش شود.

## Fields

- id
- organization_id
- order_number
- party_id
- order_type
- status
- request_date
- destination_address
- destination_province
- destination_city
- destination_postal_code
- destination_contact
- destination_phone
- payment_condition
- freight_condition
- notes
- created_by
- created_at
- updated_at

---

# 19. OrderItem

هر قلم کالا در یک درخواست.

## Fields

- id
- order_id
- organization_product_id
- quantity
- unit_id
- package_count
- estimated_weight
- price
- discount_type
- discount_value
- final_unit_price
- final_amount
- specification_values
- notes
- sort_order

یک درخواست می‌تواند یک یا چند OrderItem داشته باشد.

---

# 20. Price

قیمت کالا.

## Fields

- id
- organization_product_id
- price_type
- price
- currency
- effective_from
- effective_to
- customer_id
- minimum_quantity
- maximum_quantity
- created_by
- approved_by
- approval_date
- reason
- active

Price Type نمونه:

- Base
- Market
- CustomerSpecific
- Special
- Negotiated
- Volume

---

# 21. Discount

تخفیف معامله.

## Fields

- id
- order_id
- order_item_id
- discount_type
- value
- reason
- requested_by
- approved_by
- approved_at

قیمت اولیه نباید با قیمت نهایی جایگزین شود.

---

# 22. Approval

تأیید مدیریتی عملیات حساس.

## Fields

- id
- organization_id
- entity_type
- entity_id
- approval_type
- requested_by
- approved_by
- status
- reason
- decision_note
- created_at
- decided_at

Approval Type نمونه:

- SpecialPrice
- Discount
- BelowPrice
- CreditSale
- SpecialCondition
- Loading
- Release
- Return
- Adjustment

---

# 23. PreInvoice

پیش‌فاکتور.

## Fields

- id
- order_id
- pre_invoice_number
- version
- issue_date
- subtotal
- discount_amount
- freight_amount
- tax_amount
- total_amount
- payment_condition
- destination
- status
- created_by
- approved_by
- created_at
- approved_at

پس از تأیید، تغییرات حساس باید باعث ایجاد نسخه جدید و در صورت نیاز تأیید مجدد شوند.

> **وضعیت (ADR-060، Stage 4):** فهرست فیلدهای بالا **مفهومی و بلندمدت** است. مدل **نوشته‌شده** در Migration `db/sql/004_pre_invoices.sql` است (هنوز توسط نویسنده اجرا نشده؛ پس از اجرای تست‌ها توسط مالک تأیید می‌شود) و با فهرست بالا فرق دارد: بدون `order_id`، `freight_amount`، `payment_condition`، `destination`، `approved_by/at`.
>
> **پیاده‌شده در 004 (سه جدول):**
>
> - `pre_invoices`: `id`, `organization_id`, `source_request_id` (FK مرکب)، `chain_id`, `supersedes_id` (زنجیرهٔ جایگزینی)، `pre_invoice_number` و `version` (فقط پس از صدور؛ NULL در DRAFT)، `status` (`DRAFT/ISSUED/SUPERSEDED/CANCELLED`)، Snapshot درخواست (`request_number`, `request_date`, `requested_delivery_date`, `request_notes`)، Snapshot فروشنده (`seller_*`)، Snapshot مشتری (`customer_*` بدون `credit_limit`)، مبالغ (`subtotal`, `discount_total`, `tax_total`, `grand_total` — کپی از سربرگ درخواست، `NUMERIC(20,0)`)، چرخهٔ حیات (`created_by/at`, `issued_by/at`, `superseded_at`, `cancelled_by/at`, `cancel_reason`, `updated_at`).
> - `pre_invoice_items`: `line_no`, `source_item_id`, Snapshot محصول و واحد (id/code/name)، مقدار و مبالغ با همان قیدهای 001، `specifications` (JSONB، آرایه).
> - `pre_invoice_documents`: یک ردیف برای هر پیش‌فاکتور صادرشده؛ `status` (`pending/ready/failed`)، `pdf_data` (BYTEA)، `pdf_sha256`، `pdf_size`، `template_version`، `generated_at`، `attempt_count`، `window_started_at`، `window_attempt_count`، `last_attempt_at`، `last_error_code`.
>
> **قیدها و Triggerها (پیاده‌شده):** FK مرکب هم‌سازمانی؛ یکتایی `(org, chain_id, version)` و `(org, number, version)`؛ ایندکس‌های جزئی یکتا: یک `ISSUED` برای هر درخواست، یک `DRAFT` برای هر درخواست، یک `ISSUED` برای هر زنجیره، یک جانشین زنده برای هر سند، شمارهٔ نسخهٔ ۱ یکتا در سازمان؛ `CHECK`: وضعیت، تجمیع شماره/نسخه/صدور، شکل وضعیت، علت لغو (۱ تا ۵۰۰ نویسه، بدون فاصلهٔ اضافی)، مبالغ و `grand_total = subtotal − discount + tax`، `line_total = ROUND(q·p − d + t, 0)`، اندازهٔ PDF ≤ ۱۰٬۴۸۵٬۷۶۰ بایت و تطابق اندازه/SHA-256/سرآیند `%PDF-` با بایت‌های ذخیره‌شده. Triggerها (SQLSTATE `55000` ← `STATE_CONFLICT`): گذارهای مجاز، تغییرناپذیری هویت و Snapshot در همهٔ وضعیت‌ها (DRAFT هم قابل ویرایش نیست)، ممنوعیت حذف، اقلام فقط در DRAFT و فقط یک‌بار نوشته می‌شوند، در صدور: درخواست مبدأ هنوز `SUBMITTED` و جمع اقلام = مبالغ سربرگ، `SUPERSEDED` فقط همراه صدور جانشین، سند آماده و هش آن نهایی است، `attempt_count` کاهش نمی‌یابد.
>
> **شمارنده:** جدول جدیدی ساخته نشد؛ همان `organization_request_counters` با `series = 'PI-<سال شمسی>'` (ADR-057). **محدودیت:** گارد «لغو درخواست با پیش‌فاکتور صادرشده» در Service است، نه در پایگاه داده (002 ثابت است)؛ SQL مستقیم می‌تواند آن را دور بزند.
>
> **قابل‌پیکربندی امروز:** هیچ‌چیز. **Future:** مدت اعتبار، پیش‌پرداخت، شرایط پرداخت، فیلدهای چاپی، سیاست اصلاح اختصاصی هر شرکت.

---

# 24. Payment

پرداخت.

## Fields

- id
- order_id
- payment_type
- amount
- currency
- payment_date
- reference_number
- bank
- payer
- confirmation_status
- confirmed_by
- confirmed_at
- notes

Payment Type نمونه:

- Cash
- BankTransfer
- Check
- Credit
- Partial
- WeightAndMoney
- Other

یک سفارش می‌تواند چند Payment داشته باشد.

---

# 25. CreditAgreement

شرایط فروش اعتباری.

## Fields

- id
- order_id
- credit_days
- due_date
- guarantee_type
- guarantee_reference
- responsible_person
- approved_by
- notes

---

# 26. Voucher

حواله یا مجوز مالی/انبار مربوط به معامله.

## Fields

- id
- order_id
- voucher_number
- voucher_date
- amount
- status
- issued_by
- notes

---

# 27. Driver

اطلاعات راننده.

## Fields

- id
- name
- national_id
- mobile
- license_number
- notes
- active

---

# 28. Vehicle

اطلاعات خودرو.

## Fields

- id
- owner_party_id
- plate_number
- vehicle_type
- capacity
- driver_id
- active
- notes

Vehicle Type نمونه:

- Trailer
- Tandem
- Truck
- Pickup
- Other

---

# 29. Transport

اطلاعات حمل.

## Fields

- id
- order_id
- vehicle_id
- driver_id
- origin
- destination
- agreed_freight
- actual_freight
- freight_payer
- freight_status
- transport_status
- planned_loading_date
- delivery_date
- notes

کرایه توافق‌شده و کرایه واقعی باید جداگانه نگهداری شوند.

---

# 30. Weighing

ثبت باسکول.

## Fields

- id
- order_id
- transport_id
- weighing_type
- empty_weight
- full_weight
- net_weight
- weighing_date
- weighing_time
- ticket_number
- scale_location
- document_id
- registered_by
- notes

Weighing Type:

- Origin
- Destination

فرمول:

Net Weight = Full Weight - Empty Weight

---

# 31. WeighingDiscrepancy

اختلاف وزن.

## Fields

- id
- order_id
- origin_net_weight
- destination_net_weight
- difference
- difference_percent
- threshold
- status
- investigation_result
- decision
- approved_by
- notes

حد مجاز اختلاف وزن باید قابل تنظیم باشد.

---

# 32. Loading

عملیات بارگیری.

## Fields

- id
- order_id
- transport_id
- planned_date
- start_time
- end_time
- status
- warehouse_operator
- notes

---

# 33. ReleaseAuthorization

مجوز خروج کالا.

این موجودیت مستقل از Payment است.

## Fields

- id
- order_id
- transport_id
- status
- authorized_by
- authorization_time
- reason
- blocked_reason
- notes

## Status

- Pending
- Authorized
- Blocked
- LoadingCompleted
- Released

پرداخت کامل به تنهایی به معنی مجوز خروج نیست.

---

# 34. Delivery

تحویل کالا.

## Fields

- id
- order_id
- transport_id
- delivery_date
- receiver_name
- receiver_phone
- destination
- status
- destination_document_id
- notes

---

# 35. Dispute

اختلاف یا مشکل معامله.

## Fields

- id
- order_id
- type
- description
- reported_by
- reported_at
- status
- resolution
- resolved_by
- resolved_at
- compensation_amount
- notes

نمونه:

- Quality
- Quantity
- Weight
- Freight
- WrongProduct
- DamagedGoods
- MissingGoods
- Price
- Payment
- Delivery

---

# 36. Return

برگشت کالا.

## Fields

- id
- order_id
- order_item_id
- quantity
- weight
- reason
- approved_by
- return_date
- status
- notes

---

# 37. Document

تمام اسناد و فایل‌های مرتبط.

## Fields

- id
- organization_id
- entity_type
- entity_id
- document_type
- file_name
- file_path
- file_type
- file_size
- uploaded_by
- uploaded_at
- description

Document Type نمونه:

- PurchaseRequest
- PreInvoice
- PaymentReceipt
- Voucher
- DriverNationalCard
- VehicleDocument
- WeighbridgeTicket
- QualityPhoto
- Contract
- Check
- Other

اسناد باید بتوانند به سفارش، پرداخت، حمل، راننده، خودرو، باسکول و سایر موجودیت‌ها متصل شوند.

---

# 38. FormTemplate

قالب فرم قابل تنظیم.

این موجودیت باعث می‌شود TradeFlow برای صنوف مختلف قابل استفاده باشد.

## Fields

- id
- organization_id
- form_type
- name
- version
- header_configuration
- footer_configuration
- field_configuration
- terms_and_conditions
- logo
- signature_configuration
- active
- created_at
- updated_at

---

# 39. FormField

فیلدهای قابل نمایش در فرم.

## Fields

- id
- form_template_id
- field_name
- field_type
- required
- visible
- editable
- sort_order
- default_value
- validation_rule

---

# 40. AuditLog

ثبت تمام تغییرات حساس.

## Fields

- id
- organization_id
- user_id
- entity_type
- entity_id
- action
- old_value
- new_value
- ip_address
- device_information
- created_at

Action نمونه:

- Create
- Update
- Approve
- Reject
- Cancel
- Delete
- PaymentConfirm
- Release
- Return

حذف فیزیکی اطلاعات حساس باید تا حد امکان ممنوع باشد و از Soft Delete یا وضعیت مناسب استفاده شود.

---

# 41. Notification

اعلان‌های سیستم.

## Fields

- id
- organization_id
- user_id
- type
- title
- message
- related_entity_type
- related_entity_id
- read_at
- created_at

نمونه اعلان:

- پرداخت ثبت شد
- پرداخت تأیید شد
- کالا آماده شد
- درخواست تأیید می‌خواهد
- اختلاف وزن ایجاد شد
- مجوز خروج صادر شد
- مشکل کیفیت ثبت شد

---

# 42. File Sharing / Export

سیستم باید امکان تولید خروجی از اطلاعات معامله را داشته باشد.

خروجی‌ها:

- PDF
- Print
- Share
- WhatsApp
- Bale
- سایر برنامه‌های اشتراک‌گذاری سیستم‌عامل

منطق اصلی معامله نباید به WhatsApp یا Bale وابسته باشد.

فرآیند پیشنهادی:

Order
→ Generate Document
→ PDF
→ Share
→ انتخاب برنامه توسط کاربر

---

# 43. Order Status

وضعیت کلی معامله نمونه:

- Draft
- PurchaseRequest
- PreInvoice
- WaitingApproval
- WaitingPayment
- PartialPayment
- Paid
- VoucherIssued
- WaitingGoods
- WaitingLoading
- Loading
- OriginWeighed
- ReleaseAuthorized
- Released
- InTransit
- Delivered
- DestinationWeighed
- Settlement
- Invoiced
- Completed
- Cancelled

وضعیت‌ها باید قابل توسعه باشند.

---

# 44. وضعیت‌های مستقل

Order Status نباید جای تمام وضعیت‌ها را بگیرد.

سیستم باید وضعیت‌های مستقل برای موارد زیر داشته باشد:

- Order
- Approval
- Payment
- ProductAvailability
- Voucher
- Loading
- Weighing
- Release
- Delivery
- Settlement
- Dispute

---

# 45. Persian / Shamsi Date

در رابط کاربری:

- تاریخ شمسی
- نمایش ساعت
- تقویم شمسی
- اعداد و فرم‌های مناسب فارسی
- رابط RTL

در دیتابیس:

تاریخ‌ها باید به صورت استاندارد و قابل پردازش ذخیره شوند.

تبدیل به شمسی فقط در Presentation Layer انجام شود.

---

# 46. Purchase Request Form Requirements

فرم درخواست خرید باید دارای حداقل امکانات زیر باشد:

- شماره درخواست خودکار
- تاریخ شمسی
- ساعت ثبت
- اطلاعات مشتری
- انتخاب محصول از فهرست
- جستجوی محصول
- افزودن چند قلم کالا
- مقدار
- واحد
- تعداد بسته
- وزن تقریبی
- قیمت
- تخفیف
- شرایط تسویه
- مقصد
- اطلاعات حمل
- توضیحات
- پیوست فایل
- ذخیره
- ویرایش
- پاک کردن پیش‌نویس
- لغو درخواست
- تولید PDF
- چاپ
- اشتراک‌گذاری
- ارسال از طریق WhatsApp
- ارسال از طریق Bale

---

# 47. Product Selection Rules

در فرم درخواست:

1. محصول فقط از فهرست محصولات فعال انتخاب شود.
2. کاربر عادی اجازه تعریف محصول جدید نداشته باشد مگر مجوز مربوطه را داشته باشد.
3. مدیر یا کاربر دارای Permission مناسب بتواند محصول جدید ایجاد کند.
4. محصول غیرفعال در درخواست‌های جدید نمایش داده نشود.
5. معاملات قبلی محصول غیرفعال باقی بمانند.
6. اطلاعات محصول پس از انتخاب در فرم نمایش داده شود.
7. مشخصات فنی مربوط به محصول یا دسته محصول به صورت خودکار در صورت نیاز نمایش داده شود.
8. انتخاب محصول باید قابلیت جستجو داشته باشد.
9. امکان دسته‌بندی و فیلتر محصولات وجود داشته باشد.

---

# 48. Draft / Delete Rules

## فرم جدید

اگر هنوز ذخیره نشده باشد:

- پاک کردن اطلاعات مجاز است.

## پیش‌نویس

حذف با تأیید کاربر مجاز است.

## درخواست ثبت‌شده

حذف فیزیکی مجاز نیست.

در صورت نیاز:

- Cancel
- Archive
- Soft Delete

با ثبت AuditLog انجام شود.

---

# 49. Multi-Industry Principle

هیچ موجودیت اصلی نباید به یک صنعت خاص وابسته باشد.

نمونه صحیح:

Product
→ Category
→ Specification

نمونه نادرست:

Product
→ PipeDiameter
→ PipeThickness
→ PipeLength

اطلاعات تخصصی صنایع از طریق:

- Category
- SpecificationTemplate
- SpecificationField
- FormTemplate

مدیریت می‌شوند.

---

# 50. Multi-Organization Principle

تمام اطلاعات تجاری باید در محدوده Organization مربوطه کنترل شوند.

کاربر یک سازمان نباید بدون مجوز بتواند:

- مشتری سازمان دیگر
- قیمت سازمان دیگر
- معامله سازمان دیگر
- اسناد سازمان دیگر
- پرداخت سازمان دیگر

را مشاهده یا تغییر دهد.

---

# 51. Financial Integrity

محاسبات مالی باید با دقت مناسب انجام شوند.

مبالغ نباید با روش‌هایی ذخیره شوند که باعث خطای گرد کردن مالی شوند.

Currency و Precision باید قابل تنظیم باشند.

> **وضعیت (ADR-058):** این جمله هدف معماری بلندمدت است (ADR-042، Future). در MVP واحد ذخیره **ریال**، نوع `NUMERIC(20,0)` و رُند کردن `ROUND_HALF_UP` ثابت است؛ ارز و مقیاس قابل تنظیم وارد MVP نمی‌شوند.

---

# 52. Weight Integrity

وزن تقریبی، وزن بسته و وزن واقعی باسکول نباید با یکدیگر جایگزین شوند.

اطلاعات زیر مستقل نگهداری شوند:

- Estimated Weight
- Packaging Weight Information
- Origin Empty Weight
- Origin Full Weight
- Origin Net Weight
- Destination Empty Weight
- Destination Full Weight
- Destination Net Weight
- Difference

---

# 53. Historical Integrity

تغییر اطلاعات Master مانند:

- Product
- Customer
- Price
- Unit

نباید سوابق تاریخی معاملات را خراب کند.

در صورت نیاز، اطلاعات مهم معامله باید در زمان معامله Snapshot یا Version مناسب داشته باشند.

---

# 54. Offline Support

سیستم باید در معماری قابلیت کار در حالت Offline را در نظر بگیرد.

نمونه:

- ثبت درخواست
- مشاهده اطلاعات ذخیره‌شده
- ثبت اطلاعات محلی
- ذخیره اسناد
- ثبت عملیات قابل همگام‌سازی

پس از اتصال اینترنت:

Local Data
→ Sync
→ Server

همگام‌سازی باید از ایجاد Duplicate و Conflict جلوگیری کند.

---

# 55. Backup and Recovery

سیستم باید از ابتدا قابلیت طراحی برای:

- Backup
- Restore
- Data Recovery
- Versioning
- Migration

را داشته باشد.

---

# 56. Database Direction

با توجه به ماهیت رابطه‌ای و مالی TradeFlow:

Central Database:
PostgreSQL

Local Database:
Relational Local Database such as SQLite/Drift

انتخاب نهایی ابزارهای دیتابیس در مرحله Architecture Decision Record انجام خواهد شد.

Hive در این مرحله به عنوان دیتابیس اصلی سیستم قفل نمی‌شود.

---

# 57. Core Relationships

رابطه‌های اصلی:

Organization
→ Users

Organization
→ Parties

Organization
→ Products

Organization
→ OrganizationProducts

OrganizationProduct
→ Product

Product
→ Category

Product
→ Specifications

Organization
→ Orders

Order
→ OrderItems

OrderItem
→ OrganizationProduct

Order
→ PreInvoice

Order
→ Payments

Order
→ Approvals

Order
→ Voucher

Order
→ Transport

Transport
→ Vehicle

Transport
→ Driver

Transport
→ Weighings

Order
→ ReleaseAuthorization

Order
→ Delivery

Order
→ Disputes

Order
→ Returns

Order
→ Documents

Order
→ AuditLogs

Organization
→ FormTemplates

FormTemplate
→ FormFields

---

# 58. Important Architectural Rule

TradeFlow نباید صرفاً فرم‌های کاغذی را دیجیتال کند.

هدف سیستم:

ثبت اطلاعات
→ کنترل فرآیند
→ کاهش خطا
→ کاهش اختلاف
→ ثبت مسئولیت
→ ایجاد سابقه
→ گزارش‌گیری
→ امکان توسعه

است.

فرم کاغذی موجود فقط یکی از منابع شناخت فرآیند واقعی کسب‌وکار است.

---

# 59. Current Phase

Current Phase:

FOUNDATION / DATA MODEL

در این مرحله هنوز:

- UI نهایی نوشته نمی‌شود.
- Backend نوشته نمی‌شود.
- Database واقعی ساخته نمی‌شود.
- API نوشته نمی‌شود.

ابتدا مدل داده، روابط و قواعد اصلی تأیید می‌شوند.

بعد از تأیید:

1. Architecture Decision Record
2. Workflow Model
3. Database Schema
4. API Specification
5. UI/UX Specification
6. Project Structure
7. Development
8. Testing
# Data Model Gap Closure

## Purpose

This section extends the TradeFlow data model with additional entities and relationships
identified during architecture gap analysis.

The new entities must follow the existing principles:

- Multi-organization
- Multi-industry
- Auditability
- Historical integrity
- Role-based access
- Financial integrity
- Configurable business rules
- Offline/synchronization compatibility
- No uncontrolled physical deletion of registered transactions

---

# 1. Inventory Management

## Inventory

Represents the quantity of a product available within an organization and location.

Suggested fields:

- id
- organization_id
- warehouse_id
- product_id
- quantity
- reserved_quantity
- allocated_quantity
- available_quantity
- in_production_quantity
- in_transit_quantity
- damaged_quantity
- quarantined_quantity
- returned_quantity
- unit_id
- status
- created_at
- updated_at

Available quantity must be calculated or maintained according to controlled business rules.

---

# 2. Inventory Reservation

## InventoryReservation

Represents inventory reserved for a specific business transaction.

Suggested fields:

- id
- organization_id
- inventory_id
- order_id
- order_item_id
- product_id
- requested_quantity
- reserved_quantity
- unit_id
- status
- reserved_at
- expires_at
- released_at
- created_by
- released_by
- reason
- created_at
- updated_at

Possible statuses:

- ACTIVE
- PARTIALLY_RELEASED
- RELEASED
- EXPIRED
- CANCELLED

Reservation history must remain auditable.

---

# 3. Availability / ATP

TradeFlow should support an Available-to-Promise concept.

ATP may be calculated from:

- Physical Inventory
- Reserved Inventory
- Allocated Inventory
- In-Production Inventory
- Expected Receipts
- In-Transit Inventory
- Backorders

ATP calculation must remain configurable by industry and organization.

---

# 4. Order Revision

## OrderRevision

Represents a controlled version of an order.

Suggested fields:

- id
- order_id
- version_number
- changed_by
- change_reason
- approval_required
- approval_status
- created_at

The system must preserve historical versions.

Sensitive changes should create a new revision rather than silently modifying historical information.

---

# 5. Order Change

## OrderChange

Represents individual field-level changes within an order revision.

Suggested fields:

- id
- order_revision_id
- field_name
- old_value
- new_value
- change_type
- created_at

Sensitive values must be handled according to security and privacy rules.

---

# 6. Shipment

## Shipment

Represents one physical shipment related to an order.

One order may have multiple shipments.

Suggested fields:

- id
- organization_id
- order_id
- shipment_number
- status
- planned_date
- actual_date
- origin_location_id
- destination_location_id
- transport_id
- total_quantity
- total_weight
- delivery_status
- created_by
- created_at
- updated_at

---

# 7. ShipmentItem

Represents the product quantities contained in a shipment.

Suggested fields:

- id
- shipment_id
- order_item_id
- product_id
- quantity
- unit_id
- estimated_weight
- actual_weight
- delivered_quantity
- remaining_quantity
- created_at
- updated_at

Shipment quantities must remain linked to the original order items.

---

# 8. Backorder

## Backorder

Represents quantity requested but not currently fulfilled.

Suggested fields:

- id
- organization_id
- order_id
- order_item_id
- product_id
- requested_quantity
- available_quantity
- backordered_quantity
- fulfilled_quantity
- status
- expected_date
- created_at
- updated_at

---

# 9. Customer Credit

## CustomerCreditProfile

Represents customer credit-control information.

Suggested fields:

- id
- organization_id
- party_id
- credit_limit
- used_credit
- available_credit
- overdue_amount
- credit_period_days
- credit_status
- hold_status
- risk_level
- effective_from
- effective_to
- approved_by
- approved_at
- created_at
- updated_at

Credit calculations must not rely solely on client-side logic.

---

# 10. Credit Guarantee

## CreditGuarantee

Represents guarantees supporting a credit arrangement.

Possible guarantee types:

- Check
- Contract
- Collateral
- Bank Guarantee
- Promissory Note
- Other

Suggested fields:

- id
- organization_id
- party_id
- credit_agreement_id
- guarantee_type
- reference_number
- amount
- currency_id
- issue_date
- expiration_date
- status
- document_id
- notes
- created_at
- updated_at

---

# 11. CRM Lead

## Lead

Represents a potential customer or business opportunity before becoming a customer.

Suggested fields:

- id
- organization_id
- party_id
- title
- source
- status
- assigned_to
- expected_value
- expected_close_date
- notes
- created_at
- updated_at

---

# 12. Opportunity

## Opportunity

Represents a structured sales opportunity.

Suggested fields:

- id
- organization_id
- party_id
- lead_id
- title
- stage
- estimated_value
- probability
- expected_close_date
- assigned_to
- status
- notes
- created_at
- updated_at

Probability is an analytical field and must not be interpreted as an election or external prediction.

---

# 13. CRM Activity

## CRMActivity

Represents customer-related interactions.

Possible types:

- Call
- Meeting
- Message
- Email
- Follow-up
- Note
- Visit
- Other

Suggested fields:

- id
- organization_id
- party_id
- lead_id
- opportunity_id
- activity_type
- subject
- description
- performed_by
- activity_at
- next_follow_up_at
- status
- created_at
- updated_at

---

# 14. Customer Segment

## CustomerSegment

Represents configurable customer groups.

Examples:

- Wholesale
- Retail
- Strategic
- New
- Active
- Inactive
- Credit
- Cash

Suggested fields:

- id
- organization_id
- name
- description
- status
- created_at
- updated_at

A party may belong to multiple segments.

---

# 15. Pricing Agreement

## PricingAgreement

Represents a controlled pricing arrangement.

Suggested fields:

- id
- organization_id
- party_id
- customer_segment_id
- product_id
- price
- currency_id
- minimum_quantity
- payment_condition
- effective_from
- effective_to
- status
- approval_id
- reason
- created_at
- updated_at

Historical pricing must remain preserved.

---

# 16. Approval Rule

## ApprovalRule

Represents configurable approval criteria.

Possible conditions:

- Transaction Amount
- Discount Percentage
- Quantity
- Credit Amount
- Customer
- Product
- Transaction Type
- Organization
- Risk Level

Suggested fields:

- id
- organization_id
- name
- entity_type
- conditions
- approval_sequence
- required_approvers
- status
- effective_from
- effective_to
- created_at
- updated_at

Conditions may be represented using structured configuration rather than hard-coded application logic.

---

# 17. Approval Step

## ApprovalStep

Represents one stage in an approval workflow.

Suggested fields:

- id
- approval_id
- approval_rule_id
- sequence
- approver_type
- approver_id
- status
- decision
- decision_reason
- decided_at
- delegated_from
- created_at
- updated_at

---

# 18. Approval Delegation

## ApprovalDelegation

Represents temporary delegation of approval authority.

Suggested fields:

- id
- organization_id
- delegator_user_id
- delegate_user_id
- start_at
- end_at
- scope
- status
- reason
- created_at
- updated_at

Delegation must never exceed the authority of the original approver.

---

# 19. SLA Rule

## SLARule

Represents a configurable service-level rule.

Suggested fields:

- id
- organization_id
- entity_type
- event_type
- target_duration
- warning_duration
- escalation_duration
- escalation_target
- status
- created_at
- updated_at

---

# 20. Exception

## BusinessException

Represents an operational or business exception requiring attention.

Possible types:

- Weight Discrepancy
- Payment Mismatch
- Credit Hold
- Missing Document
- Price Violation
- Discount Violation
- Vehicle Document Expired
- Product Unavailable
- Delivery Delay
- Quality Problem
- Customer Claim

Suggested fields:

- id
- organization_id
- exception_number
- exception_type
- severity
- status
- title
- description
- related_entity_type
- related_entity_id
- assigned_to
- due_at
- resolved_at
- resolution
- created_by
- created_at
- updated_at

---

# 21. Reconciliation

## ReconciliationRecord

Represents comparison between two or more related records.

Possible reconciliation types:

- Order vs Payment
- Payment vs Accounting
- Order vs Voucher
- Origin Weight vs Destination Weight
- Shipment vs Delivery
- Invoice vs Payment
- Customer Balance vs Transactions

Suggested fields:

- id
- organization_id
- reconciliation_number
- reconciliation_type
- source_entity_type
- source_entity_id
- target_entity_type
- target_entity_id
- expected_value
- actual_value
- difference
- status
- reviewed_by
- reviewed_at
- resolution
- created_at
- updated_at

---

# 22. Proof of Delivery

## ProofOfDelivery

Represents evidence that a shipment was delivered.

Suggested fields:

- id
- organization_id
- shipment_id
- receiver_name
- receiver_identifier
- delivered_at
- signature_document_id
- delivery_document_id
- photo_document_id
- location_data
- notes
- created_at
- updated_at

Location data is optional and must respect privacy and permissions.

---

# 23. Customer Claim

## Claim

Represents a formal customer claim.

Suggested fields:

- id
- organization_id
- claim_number
- party_id
- order_id
- shipment_id
- claim_type
- severity
- status
- description
- reported_at
- assigned_to
- investigation_result
- decision
- compensation_amount
- resolution
- resolved_at
- created_at
- updated_at

---

# 24. Issue Management

## Issue

Represents a technical, business or support issue.

Possible types:

- TECHNICAL_ERROR
- APPLICATION_CRASH
- BUSINESS_ERROR
- USER_REPORTED_BUG
- SUPPORT_REQUEST
- FEATURE_REQUEST
- COMPLAINT

Suggested fields:

- id
- organization_id
- issue_number
- reported_by
- assigned_to
- type
- severity
- status
- title
- description
- module
- screen
- transaction_id
- app_version
- api_version
- platform
- device_info
- correlation_id
- created_at
- updated_at
- resolved_at
- resolution
- resolution_version

---

# 25. Issue Comment

## IssueComment

Represents communication associated with an issue.

Suggested fields:

- id
- issue_id
- user_id
- comment
- visibility
- created_at
- updated_at

---

# 26. Issue Status History

## IssueStatusHistory

Represents the lifecycle of an issue.

Suggested fields:

- id
- issue_id
- old_status
- new_status
- changed_by
- reason
- created_at

---

# 27. Notification

## Notification

Represents an in-app or system notification.

Suggested fields:

- id
- organization_id
- user_id
- notification_type
- title
- message
- related_entity_type
- related_entity_id
- priority
- channel
- status
- sent_at
- read_at
- created_at

---

# 28. Notification Preference

## NotificationPreference

Represents user notification preferences.

Suggested fields:

- id
- user_id
- notification_type
- channel
- enabled
- quiet_hours
- created_at
- updated_at

---

# 29. Work Item

## WorkItem

Represents an actionable task assigned to a user.

Possible sources:

- Approval
- Exception
- Issue
- Claim
- Credit Hold
- Loading
- Payment Review
- Document Review

Suggested fields:

- id
- organization_id
- user_id
- source_entity_type
- source_entity_id
- priority
- status
- due_at
- completed_at
- created_at
- updated_at

---

# 30. Subscription Plan

## SubscriptionPlan

Represents a TradeFlow product plan.

Examples:

- Free
- Basic
- Professional
- Enterprise

Suggested fields:

- id
- name
- description
- price
- currency_id
- billing_period
- limits
- features
- status
- created_at
- updated_at

---

# 31. Organization Subscription

## OrganizationSubscription

Represents an organization's active subscription.

Suggested fields:

- id
- organization_id
- subscription_plan_id
- status
- start_at
- end_at
- renewal_at
- limits
- created_at
- updated_at

Subscription data must remain separate from core transaction records.

---

# 32. Feature Flag

## FeatureFlag

Represents configurable system features.

Suggested fields:

- id
- key
- name
- description
- default_value
- environment
- status
- created_at
- updated_at

Feature availability may be controlled by:

- Organization
- Subscription Plan
- User Role
- Application Version

---

# 33. Currency

## Currency

Represents a supported currency.

Suggested fields:

- id
- code
- name
- symbol
- decimal_precision
- status
- created_at
- updated_at

---

# 34. Exchange Rate

## ExchangeRate

Represents currency conversion information.

Suggested fields:

- id
- base_currency_id
- target_currency_id
- rate
- effective_at
- source
- created_at
- updated_at

Historical exchange rates must remain immutable once used in a registered transaction.

---

# 35. Tax Definition

## TaxDefinition

Represents configurable tax information.

Suggested fields:

- id
- organization_id
- name
- code
- rate
- tax_type
- included_in_price
- effective_from
- effective_to
- status
- created_at
- updated_at

---

# 36. Cost Record

## CostRecord

Represents cost information used for profitability calculations.

Possible types:

- Purchase Cost
- Production Cost
- Freight Cost
- Handling Cost
- Other Cost

Suggested fields:

- id
- organization_id
- entity_type
- entity_id
- cost_type
- amount
- currency_id
- quantity
- unit_id
- occurred_at
- source
- created_at
- updated_at

---

# 37. Archive Record

## ArchiveRecord

Represents controlled archival metadata.

Suggested fields:

- id
- organization_id
- entity_type
- entity_id
- archived_by
- archived_at
- reason
- retention_until
- status

Archiving must not break relationships required for historical reporting and audit.

---

# 38. Integration

## Integration

Represents an external system connection.

Examples:

- Accounting
- Tax
- Banking
- SMS
- Email
- Maps
- Weighbridge
- ERP
- CRM

Suggested fields:

- id
- organization_id
- integration_type
- provider
- configuration
- status
- last_sync_at
- created_at
- updated_at

Credentials and secrets must be stored securely and must never be exposed through ordinary API responses.

---

# 39. Webhook Subscription

## WebhookSubscription

Represents an external webhook registration.

Suggested fields:

- id
- organization_id
- endpoint
- subscribed_events
- secret_reference
- status
- last_delivery_at
- created_at
- updated_at

Webhook delivery must support:

- Retry
- Failure Tracking
- Idempotency
- Signature Verification

---

# 40. Audit and Security Events

AuditLog remains separate from Issue management.

AuditLog records:

- Who
- What
- When
- Where
- Previous Value
- New Value
- Related Entity
- Correlation ID

Security events should additionally record relevant events such as:

- Login Success
- Login Failure
- Password Reset
- Two-Factor Authentication
- Session Revocation
- Permission Change
- Role Change
- Sensitive Operation

Sensitive information such as passwords, tokens and authentication secrets must never be stored in logs.

---

# 41. Entity Relationship Principles

The following relationships must be preserved:

Organization
→ Users
→ Parties
→ Products
→ Warehouses
→ Inventory
→ Orders
→ Payments
→ Shipments
→ Documents
→ Audit Logs
→ Issues
→ Exceptions

Order
→ Order Items
→ Reservations
→ Shipments
→ Payments
→ Voucher
→ Loading
→ Weighing
→ Release
→ Delivery
→ Proof of Delivery
→ Claims
→ Settlement

Customer/Party
→ Credit Profile
→ Credit Guarantees
→ Orders
→ Payments
→ CRM Activities
→ Leads
→ Opportunities
→ Claims

Product
→ Category
→ Specification
→ Unit
→ Pricing
→ Inventory
→ Reservations
→ Order Items

---

# 42. Data Integrity Rules

The following must be enforced at the domain and database levels where applicable:

1. Registered financial transactions must not be physically deleted.
2. Historical prices used by completed transactions must remain unchanged.
3. Historical order revisions must remain available.
4. Payment totals must be validated against transaction requirements.
5. Inventory reservation must not exceed allowed available quantity unless an authorized override exists.
6. Shipment quantity must not exceed the permitted order quantity without an authorized adjustment.
7. Delivery quantity must remain traceable to shipment quantity.
8. Credit exposure must be calculated server-side.
9. Sensitive approvals must be auditable.
10. Reversals must be used instead of destructive deletion for financial corrections.
11. All sensitive state transitions must be auditable.
12. Organization boundaries must be enforced server-side.
13. Feature flags must not bypass security or authorization rules.
14. Offline synchronization must not silently overwrite newer server data.
15. Financial calculations must use controlled precision.
16. Weight calculations must preserve measurement precision.
17. Historical data must remain reportable after archival.

---

# 43. Soft Delete and Cancellation

Entities must be classified according to whether deletion is permitted.

### Temporary Records

Draft records may be deleted according to permissions.

### Registered Transactions

Registered transactions must use:

- Cancel
- Reverse
- Archive
- Void

instead of physical deletion.

### Master Data

Master data should normally use:

- Active
- Inactive
- Archived

so historical transactions remain valid.

---

# 44. Data Versioning

Entities that may be modified after registration should support versioning or controlled history.

At minimum:

- Orders
- Pricing
- Approval Rules
- Forms
- Product Specifications
- Tax Definitions
- Subscription Plans
- Feature Flags
- Integration Configuration

---

# 45. Data Ownership and Tenant Isolation

Every organization-owned entity must be associated with an organization where applicable.

Server-side authorization must ensure that a user cannot access another organization's records by manipulating identifiers.

Client-side filtering is never considered sufficient for tenant isolation.

---

# 46. Offline and Synchronization Metadata

Entities participating in offline operation may require:

- local_id
- server_id
- sync_status
- sync_version
- last_synced_at
- updated_at
- deleted_at where soft deletion applies

Synchronization must support:

- Retry
- Conflict Detection
- Conflict Resolution
- Idempotency
- Failed Sync Queue

---

# 47. Correlation and Traceability

Important operations should carry a Correlation ID.

A single business operation should be traceable across:

- Flutter Client
- API
- Business Service
- Database
- Notification Service
- Integration Service
- Audit Log
- Error/Issue Reporting

---

# 48. File and Evidence Relationships

Documents and files must be linked through structured references rather than stored as uncontrolled paths.

Possible related entities:

- Customer
- Product
- Order
- Payment
- Voucher
- Vehicle
- Driver
- Shipment
- Weighing
- Delivery
- Claim
- Issue
- Exception
- Credit Guarantee

Files must have:

- Owner
- Entity Type
- Entity ID
- Document Type
- Version
- Upload User
- Upload Date
- Storage Reference
- Integrity Metadata
- Access Permissions

---

# 49. Data Model Design Principle

The TradeFlow database must model the real business lifecycle without forcing unrelated concepts into a single table.

Core concepts such as:

- Order
- Payment
- Inventory
- Reservation
- Shipment
- Delivery
- Weighing
- Approval
- Credit
- Claim
- Exception
- Issue
- Audit

must remain logically independent while maintaining explicit relationships.

The database design must avoid both extremes:

- One giant transaction table containing unrelated concepts
- Excessive fragmentation into unnecessary tables

The final relational model must be reviewed for normalization, performance,
historical integrity and practical implementation before database migration creation.

---

# Current Data Model Status

The TradeFlow data model now includes the original core entities plus
the additional entities identified during architecture gap analysis.

Before implementation:

1. Review all entities.
2. Remove duplicate concepts.
3. Normalize relationships.
4. Define primary keys.
5. Define foreign keys.
6. Define indexes.
7. Define unique constraints.
8. Define nullable/non-nullable fields.
9. Define enums or lookup tables.
10. Define database migrations.
11. Validate the model against the complete workflow.
12. Validate the model against the API specification.
13. Validate the model against the UI specification.

No production database schema should be generated until this validation is complete.

---

# MVP Physical Data Model — Baseline Hardened (001 + 002)

> **وضعیت:** این بخش مدل فیزیکی اجرایی MVP است و عیناً با `001_initial_mvp.sql` + `002_harden_mvp.sql` هماهنگ شده است. تصمیم‌های ADR-056 تا ADR-063 در آن اعمال شده‌اند.
> **اولویت:** در هر تعارض بین این بخش و بخش‌های مفهومی (۱ تا ۵۹ و Gap Closure)، برای MVP همین بخش و فایل‌های Migration معتبرند. بخش‌های مفهومی «مدل هدف» هستند، نه Schema اجرایی.
> **قاعده تغییر:** هر تغییر در این بخش فقط با Migration جدید (۰۰۳ و بعد) و ADR انجام می‌شود. Migration‌های ۰۰۱ و ۰۰۲ تغییرناپذیرند (Checksum).

## ۱. جدول‌های MVP (۱۶ جدول)

۱۵ جدول از `001` و ۱ جدول از `002` (ADR-057):

| # | جدول | منشأ | نقش |
|---:|---|---|---|
| 1 | organizations | 001 | سازمان (Tenant) |
| 2 | roles | 001 | نقش‌ها |
| 3 | users | 001 | کاربران |
| 4 | customers | 001 (+002) | مشتریان |
| 5 | product_categories | 001 | دسته‌بندی محصول |
| 6 | units | 001 | واحدها |
| 7 | products | 001 | محصولات |
| 8 | product_specification_templates | 001 | قالب مشخصات |
| 9 | product_specification_fields | 001 | فیلدهای مشخصات |
| 10 | product_specification_values | 001 | مقادیر مشخصات محصول |
| 11 | purchase_requests | 001 (+002) | درخواست خرید |
| 12 | purchase_request_items | 001 (+002) | اقلام درخواست |
| 13 | audit_logs | 001 (+002) | Audit (فقط‌افزودنی) |
| 14 | refresh_tokens | 001 | Refresh Token (فقط Hash) |
| 15 | schema_migrations | 001 | ثبت Migration‌ها (زیرساختی) |
| 16 | organization_request_counters | 002 | شمارنده شماره درخواست |

**در مدل پایهٔ 001+002 وجود ندارد:** `currency_id`، `organizations.code` (در 001+002 وجود ندارد؛ در Migration 003 اضافه شده، ADR-059)، جدول Pre-Invoice (در Migration 004 نوشته شده؛ هنوز اجرا نشده، ADR-060)، Revision، Approval، Payment و سایر دامنه‌های Phase 2.

## ۲. اصول کلی فیزیکی

1. کلید اصلی همه جدول‌ها `UUID` با `gen_random_uuid()` است (افزونه `pgcrypto`).
2. زمان‌ها `TIMESTAMPTZ` و در UTC هستند؛ نمایش شمسی فقط در UI است.
3. `requested_delivery_date` یک **تاریخ تقویمی** (`DATE`) به وقت تهران است، نه زمان.
4. پول (ADR-058): واحد **ریال**، نوع `NUMERIC(20,0)` در همه ستون‌های مالی؛ مقدار صحیح بدون اعشار (`125000` نه `125000.00`). Python با `Decimal` و `ROUND_HALF_UP` کار می‌کند.
5. `quantity` و `estimated_weight` از نوع `NUMERIC(18,3)` هستند. واحد وزن تخمینی در MVP کیلوگرم است.
6. هر جدول Tenant ستون `organization_id` دارد و ارجاع‌های بین جدول‌ها با **کلید خارجی ترکیبی هم‌سازمانی** `(id, organization_id)` کنترل می‌شود. (ارجاع از `refresh_tokens` به `users` ساده است و ستون سازمان ندارد.)
7. دیتابیس باید `UTF8` باشد؛ `002` در غیر این صورت خطا می‌دهد.
8. `updated_at` با Trigger `set_updated_at` روی ۱۲ جدول مدیریت می‌شود: organizations، roles، users، customers، product_categories، units، products، product_specification_templates، product_specification_fields، product_specification_values، purchase_requests، purchase_request_items.

## ۳. جزئیات جدول‌ها

علامت‌ها: **NN** = NOT NULL. **PK** = کلید اصلی. تمام ستون‌های `created_at` و `updated_at` از نوع `TIMESTAMPTZ NN DEFAULT NOW()` هستند، مگر خلافش گفته شود.

### ۳.۱ — schema_migrations

TABLE: schema_migrations

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| version | VARCHAR(100) | NN، یکتا |
| name | VARCHAR(255) | NN |
| checksum | VARCHAR(128) | اختیاری (Runner آن را پر می‌کند) |
| executed_at | TIMESTAMPTZ | NN، پیش‌فرض NOW() |

قواعد: Runner طبق ADR-056 نسخه، نام و Checksum را در **همان تراکنش** Migration ثبت می‌کند. نسخه‌های ۰۰۱ تا ۸۹۹ Migration هستند؛ ۹۰۰ تا ۹۹۹ Seed توسعه‌اند و ثبت نمی‌شوند.

### ۳.۲ — organizations

TABLE: organizations

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| name | TEXT | NN |
| legal_name | TEXT | |
| national_id | VARCHAR(50) | |
| economic_code | VARCHAR(50) | |
| registration_number | VARCHAR(50) | |
| phone | VARCHAR(50) | |
| email | VARCHAR(255) | |
| address | TEXT | |
| postal_code | VARCHAR(20) | |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

قواعد: یکتایی `national_id` و `economic_code` برای سازمان‌ها در Baseline **اعمال نشده است**. ستون `code` (کد سازمان برای Login، ADR-059) در 001+002 وجود نداشت و در Migration 003 اضافه شده است (جدول بالا وضعیت پس از 001+002 است).

### ۳.۳ — roles

TABLE: roles

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| code | VARCHAR(50) | NN |
| name | VARCHAR(100) | NN |
| description | TEXT | |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(organization_id, code)` و `(id, organization_id)`.

### ۳.۴ — users

TABLE: users

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| role_id | UUID | NN، FK ترکیبی `(role_id, organization_id)` → roles |
| first_name | VARCHAR(100) | NN |
| last_name | VARCHAR(100) | NN |
| mobile | VARCHAR(30) | |
| email | VARCHAR(255) | |
| username | VARCHAR(100) | NN |
| password_hash | TEXT | NN |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| last_login_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(organization_id, username)` و `(id, organization_id)`. یکتایی `mobile` در Baseline اعمال **نشده** است. هر کاربر به یک سازمان تعلق دارد (ADR-059، گزینه A). Login با `organization_code + username + password` انجام می‌شود و توکن `organization_id` را به‌عنوان Context حمل می‌کند.

### ۳.۵ — customers

TABLE: customers

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| customer_type | VARCHAR(20) | NN، فقط INDIVIDUAL یا COMPANY |
| name | VARCHAR(255) | NN |
| national_id | VARCHAR(50) | نرمال‌سازی‌شده |
| economic_code | VARCHAR(50) | نرمال‌سازی‌شده |
| registration_number | VARCHAR(50) | |
| mobile | VARCHAR(30) | |
| phone | VARCHAR(50) | |
| email | VARCHAR(255) | |
| address | TEXT | |
| postal_code | VARCHAR(20) | |
| credit_limit | NUMERIC(20,0) | NN، پیش‌فرض 0، ≥ 0 |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

قواعد (ADR-061، C2 و C3):
1. **نام مشتری یکتا نیست.** فقط `national_id` و `economic_code` هویت مشتری را مشخص می‌کنند.
2. یکتایی جزئی: `(organization_id, national_id)` و `(organization_id, economic_code)` وقتی مقدار NULL نباشد.
3. این دو ستون با Trigger نرمال می‌شوند: ارقام فارسی/عربی به ASCII، حذف فاصله، ZWNJ و NBSP، رشتهٔ خالی → NULL. یک CHECK هم نرمال بودن را تضمین می‌کند.
4. `credit_limit` در MVP فقط ذخیره می‌شود؛ کنترل اعتبار Phase 2 است.

### ۳.۶ — product_categories

TABLE: product_categories

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| parent_id | UUID | FK ترکیبی `(parent_id, organization_id)` → product_categories |
| name | VARCHAR(255) | NN |
| code | VARCHAR(50) | NN |
| description | TEXT | |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(organization_id, code)`.

### ۳.۷ — units

TABLE: units

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| name | VARCHAR(100) | NN |
| code | VARCHAR(20) | NN |
| unit_type | VARCHAR(30) | NN، یکی از QUANTITY, WEIGHT, LENGTH, AREA, VOLUME, TIME |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(organization_id, code)`. نمونه‌ها: PCS، KG، TON، M، M2، M3.

### ۳.۸ — products

TABLE: products

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| category_id | UUID | NN، FK ترکیبی → product_categories |
| name | VARCHAR(255) | NN |
| code | VARCHAR(100) | NN |
| description | TEXT | |
| default_unit_id | UUID | NN، FK ترکیبی → units |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(organization_id, code)` و `(organization_id, name)`. مشخصات تخصصی در جدول‌های Specification نگهداری می‌شود، نه در این جدول.

### ۳.۹ — product_specification_templates

TABLE: product_specification_templates

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| category_id | UUID | FK ترکیبی → product_categories (اختیاری) |
| name | VARCHAR(255) | NN |
| code | VARCHAR(100) | NN |
| description | TEXT | |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(organization_id, code)`.

### ۳.۱۰ — product_specification_fields

TABLE: product_specification_fields

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| template_id | UUID | NN، FK ترکیبی → product_specification_templates |
| name | VARCHAR(255) | NN |
| code | VARCHAR(100) | NN |
| data_type | VARCHAR(30) | NN، یکی از TEXT, NUMBER, DECIMAL, BOOLEAN, DATE, SELECT, MULTI_SELECT |
| is_required | BOOLEAN | NN، پیش‌فرض FALSE |
| is_active | BOOLEAN | NN، پیش‌فرض TRUE |
| display_order | INTEGER | NN، پیش‌فرض 0 |
| options | JSONB | گزینه‌ها برای SELECT و MULTI_SELECT |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

یکتا: `(template_id, code)`. حذف فیزیکی توصیه نمی‌شود؛ فیلد غیرفعال می‌شود.

### ۳.۱۱ — product_specification_values

TABLE: product_specification_values

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| product_id | UUID | NN، FK ترکیبی → products |
| field_id | UUID | NN، FK ترکیبی → product_specification_fields |
| value_text | TEXT | |
| value_number | BIGINT | |
| value_decimal | NUMERIC(18,6) | |
| value_boolean | BOOLEAN | |
| value_date | DATE | |
| value_option | TEXT | |
| value_options | JSONB | |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

قواعد: یکتا `(product_id, field_id)`. حداکثر یکی از ستون‌های `value_*` مقدار دارد (CHECK). **تطابق نوع مقدار با `data_type` فیلد در دیتابیس اعمال نمی‌شود** و وظیفهٔ Service است (بخش ۶).

### ۳.۱۲ — purchase_requests

TABLE: purchase_requests

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| request_number | VARCHAR(50) | NN، یکتا در سازمان |
| customer_id | UUID | NN، FK ترکیبی → customers |
| status | VARCHAR(30) | NN، پیش‌فرض DRAFT، فقط DRAFT / SUBMITTED / CANCELLED |
| request_date | TIMESTAMPTZ | NN، پیش‌فرض NOW() |
| requested_delivery_date | DATE | اختیاری |
| subtotal | NUMERIC(20,0) | NN، پیش‌فرض 0 |
| discount_total | NUMERIC(20,0) | NN، پیش‌فرض 0 |
| tax_total | NUMERIC(20,0) | NN، پیش‌فرض 0 |
| grand_total | NUMERIC(20,0) | NN، پیش‌فرض 0 |
| notes | TEXT | |
| created_by | UUID | NN، FK ترکیبی → users |
| updated_by | UUID | FK ترکیبی → users |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

قواعد:
1. یکتا: `(organization_id, request_number)` و `(id, organization_id)`.
2. مبالغ ≥ 0 و `grand_total = subtotal - discount_total + tax_total` (CHECK).
3. `requested_delivery_date` (C1): تاریخ تقویمی به وقت تهران و بزرگ‌تر یا مساوی روز `request_date` (می‌تواند همان روز باشد).
4. **ماشین حالت (C5):** `DRAFT → SUBMITTED`، `DRAFT → CANCELLED`، `SUBMITTED → CANCELLED`. هر انتقال دیگر ممنوع است (خطا با کد `55000`). `CANCELLED` پایانی است.
5. تغییرناپذیر در هر حالت: `organization_id`، `request_number`، `created_by`، `created_at`.
6. وقتی وضعیت قبلی `DRAFT` نیست، فیلدهای تجاری Freeze می‌شوند: `customer_id`، `request_date`، `requested_delivery_date` و چهار جمع مالی. فقط `status`، `notes` و `updated_*` می‌توانند تغییر کنند.
7. حذف فیزیکی فقط برای `DRAFT` مجاز است؛ `SUBMITTED` و `CANCELLED` حذف نمی‌شوند.
8. چهار جمع مالی پس از هر تغییر ردیف توسط Trigger از روی اقلام بازسازی می‌شود. دیتابیس فقط سازگاری داخلی آن‌ها را کنترل می‌کند (`grand_total = subtotal - discount_total + tax_total`)؛ بنابراین Service نباید این مقادیر را از ورودی Client بپذیرد (ADR-058).
9. `request_number` را Service با `next_request_number` می‌گیرد (بخش ۴). ستون `currency_id` وجود ندارد.

### ۳.۱۳ — purchase_request_items

TABLE: purchase_request_items

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| purchase_request_id | UUID | NN، FK ترکیبی → purchase_requests |
| product_id | UUID | NN، FK ترکیبی → products |
| quantity | NUMERIC(18,3) | NN، > 0 |
| unit_id | UUID | NN، FK ترکیبی → units |
| bundle_count | NUMERIC(18,0) | NN، پیش‌فرض 0، ≥ 0 |
| estimated_weight | NUMERIC(18,3) | اختیاری، ≥ 0، واحد KG |
| unit_price | NUMERIC(20,0) | NN، پیش‌فرض 0، ≥ 0 |
| discount_amount | NUMERIC(20,0) | NN، پیش‌فرض 0، ≥ 0 |
| tax_amount | NUMERIC(20,0) | NN، پیش‌فرض 0، ≥ 0 |
| line_total | NUMERIC(20,0) | NN، پیش‌فرض 0، ≥ 0 |
| notes | TEXT | |
| specifications | JSONB | NN، پیش‌فرض `[]`، باید آرایه باشد |
| created_at | TIMESTAMPTZ | NN |
| updated_at | TIMESTAMPTZ | NN |

قواعد:
1. یکتا: `(id, organization_id)`.
2. `discount_amount <= quantity × unit_price`.
3. **فرمول ردیف (ADR-058):** `line_total = ROUND_HALF_UP(quantity × unit_price − discount_amount + tax_amount)` به صورت برابری دقیق (CHECK). در PostgreSQL همان `ROUND(...,0)` است؛ در Python `Decimal` با `ROUND_HALF_UP` و Context صریح (نه پیش‌فرض `ROUND_HALF_EVEN`).
4. جمع‌های سربرگ: `subtotal = Σ ROUND(quantity × unit_price, 0)`، `discount_total = Σ discount_amount`، `tax_total = Σ tax_amount`، `grand_total = Σ line_total`.
5. **Freeze (C5):** فقط وقتی درخواست والد `DRAFT` است می‌توان ردیف را افزود، تغییر داد یا حذف کرد. جابه‌جایی ردیف بین درخواست‌ها یا سازمان‌ها ممنوع است. Trigger والد را `FOR UPDATE` قفل می‌کند تا ثبت هم‌زمان (Submit) و نوشتن ردیف با هم تداخل نکنند.
6. **Snapshot مشخصات (C6):** `specifications` آرایه‌ای از عناصری با کلیدهای `field_id`، `field_code`، `field_name`، `data_type`، `value` است. Trigger وجود فیلد، هم‌سازمانی، تطابق `code` و `data_type` و نبودن فیلد تکراری را کنترل می‌کند. تغییر بعدی قالب یا مقادیر محصول به Snapshot دست نمی‌زند.

### ۳.۱۴ — audit_logs

TABLE: audit_logs

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | NN، FK → organizations(id) |
| user_id | UUID | FK ترکیبی → users (اختیاری) |
| entity_type | VARCHAR(100) | NN |
| entity_id | UUID | |
| action | VARCHAR(50) | NN |
| old_data | JSONB | |
| new_data | JSONB | |
| description | TEXT | |
| ip_address | INET | |
| created_at | TIMESTAMPTZ | NN |

قواعد (C4): جدول **فقط‌افزودنی** است. `UPDATE`، `DELETE` و `TRUNCATE` با خطای `55000` رد می‌شوند. ستون `updated_at` ندارد. `action` در دیتابیس CHECK ندارد؛ فهرست مقادیر (`CREATE`, `UPDATE`, `SUBMIT`, `CANCEL`, `LOGIN`, `LOGOUT`, …) واژگان Service است و در قرارداد API تعریف می‌شود. Refresh Token خام هرگز در Audit ثبت نمی‌شود.

### ۳.۱۵ — refresh_tokens

TABLE: refresh_tokens

| ستون | نوع | قید |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | NN، FK → users(id) |
| token_hash | TEXT | NN، یکتا |
| expires_at | TIMESTAMPTZ | NN |
| revoked_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | NN |

قواعد: فقط Hash ذخیره می‌شود. Token باید به همان Context سازمانی کاربر وابسته باشد (ADR-059). انقضا و ابطال را Service کنترل می‌کند.

### ۳.۱۶ — organization_request_counters

TABLE: organization_request_counters

| ستون | نوع | قید |
|---|---|---|
| organization_id | UUID | NN، FK → organizations(id)، بخشی از PK |
| series | VARCHAR(50) | NN، بخشی از PK |
| last_number | BIGINT | NN، پیش‌فرض 0، ≥ 0 |
| updated_at | TIMESTAMPTZ | NN |

PK: `(organization_id, series)`.

## ۴. شماره درخواست (ADR-057)

1. Service در همان تراکنش ایجاد درخواست، `next_request_number(organization_id, series)` را صدا می‌زند. `series` را Service انتخاب می‌کند (مثلاً سال شمسی `1405`).
2. تابع با `INSERT … ON CONFLICT DO UPDATE … RETURNING` عدد بعدی را برمی‌گرداند. قفل ردیف تا پایان تراکنش می‌ماند؛ عددها یکتا و پشت‌سرهم‌اند و اگر تراکنش Rollback شود عدد برمی‌گردد.
3. `MAX()+1` ممنوع است. قالب متنی نهایی (پیشوند، صفر پشت عدد) در DB تعریف نشده و در قرارداد Slice اول مشخص می‌شود.
4. `request_number` توسط Client تولید یا ارسال نمی‌شود.

## ۵. روابط

```text
organizations 1 ─< roles ─< users
organizations 1 ─< customers
organizations 1 ─< product_categories (parent_id: خود-ارجاع) ─< products
organizations 1 ─< units
organizations 1 ─< product_specification_templates ─< product_specification_fields
products 1 ─< product_specification_values >─ 1 product_specification_fields
organizations 1 ─< purchase_requests ─< purchase_request_items
customers 1 ─< purchase_requests
products 1 ─< purchase_request_items >─ 1 units
users 1 ─< purchase_requests (created_by, updated_by)
organizations 1 ─< audit_logs >─ 0..1 users
users 1 ─< refresh_tokens
organizations 1 ─< organization_request_counters
```

قواعد رابطه‌ای (همه با FK ترکیبی `(id, organization_id)` در دیتابیس اعمال می‌شوند، به‌جز `refresh_tokens`):
1. هر User فقط به یک Organization تعلق دارد.
2. Role، Customer، Product، Unit، Category، Template و Field هر کدام به یک Organization تعلق دارند.
3. Customer، `created_by`، `updated_by`، Product و Unit در یک درخواست باید هم‌سازمان آن درخواست باشند.
4. Role کاربر باید هم‌سازمان کاربر باشد.
5. Parent دسته‌بندی باید هم‌سازمان باشد.
6. `product_specification_values` باید به Product و Field هم‌سازمان اشاره کند.
7. ردیف درخواست از طریق `organization_id` و FK ترکیبی به همان سازمان درخواست محدود است.

## ۶. چه چیزی در دیتابیس اعمال می‌شود و چه چیزی در Service

**در دیتابیس اعمال می‌شود (تست‌شده در `tests/regression.sql`):**
هم‌سازمانی ارجاع‌ها، یکتایی‌ها، علامت و حد مبالغ، فرمول `line_total`، بازسازی خودکار جمع‌های سربرگ پس از تغییر ردیف، ماشین حالت و Freeze، حذف فقط DRAFT، Append-only بودن Audit، نرمال‌سازی شناسه‌های مشتری، تاریخ تحویل، ساختار Snapshot مشخصات، شماره‌گذاری هم‌زمان.

**در دیتابیس اعمال نمی‌شود و وظیفهٔ Service است (و باید تست شود):**

| قاعده | محل |
|---|---|
| فعال بودن Customer، Product، Unit، Role هنگام ایجاد تراکنش جدید | Service |
| تطابق `value` در `product_specification_values` و در Snapshot ردیف با `data_type` (DECIMAL، INTEGER، BOOLEAN، DATE، OPTION، TEXT) | Service |
| ثبت اجباری فیلدهای `is_required` | Service |
| تولید Snapshot از روی فیلدهای فعال هنگام ذخیرهٔ ردیف | Service |
| ثبت رویداد Audit برای هر عملیات حساس (DB فقط جلوی ویرایش را می‌گیرد، تولید رکورد با Service است) | Service |
| احراز هویت، مجوزها، انقضای Token، نرخ‌محدودسازی Login | Service |
| قالب متنی شماره درخواست و انتخاب `series` | Service |
| `updated_at ≥ created_at` | Trigger `set_updated_at` مقدار `updated_at` را همیشه NOW() می‌کند؛ کنترل جداگانه لازم نیست |
| یکتایی `national_id` / `economic_code` سازمان‌ها و `mobile` کاربران | اعمال نشده (در Baseline وجود ندارد) |

## ۷. Indexها

```text
roles:                           (organization_id)
users:                           (organization_id) ، (organization_id, role_id)
customers:                       (organization_id) ، (organization_id, name)
products:                        (organization_id) ، (organization_id, category_id) ، (organization_id, name)
product_categories:              (organization_id) ، (organization_id, parent_id)
units:                           (organization_id)
product_specification_templates: (organization_id)
product_specification_fields:    (organization_id, template_id, display_order)
product_specification_values:    (organization_id, product_id) ، (organization_id, field_id)
purchase_requests:               (organization_id, request_date) ، (organization_id, status)
                                 (organization_id, customer_id) ، (organization_id, created_by)
purchase_request_items:          (organization_id, purchase_request_id) ، (organization_id, product_id)
audit_logs:                      (organization_id, created_at) ، (organization_id, user_id)
                                 (organization_id, entity_type, entity_id)
refresh_tokens:                  (user_id) ، (expires_at)
```

علاوه بر اینها Indexهای ضمنی `UNIQUE` و دو Index یکتای جزئی مشتری وجود دارد. Index جدید فقط با الگوی واقعی مصرف و با Migration اضافه می‌شود.

## ۸. وضعیت رکوردها

1. Master Data (Customer، Product، Unit، Role، Category) با `is_active` مدیریت می‌شود؛ غیرفعال‌سازی سوابق قبلی را تغییر نمی‌دهد.
2. درخواست `DRAFT` قابل حذف است؛ درخواست ثبت‌شده فقط `CANCELLED` می‌شود.
3. Audit هرگز حذف یا ویرایش نمی‌شود.
4. تغییر محتوای درخواست `SUBMITTED` در MVP ممنوع است. Revision (نسخه‌گذاری) در Phase 2 است و تا آن زمان راه تغییر، لغو و ایجاد درخواست جدید است.

## ۹. Migration Strategy (ADR-056)

1. تمام تغییرات Schema فقط با Migration شماره‌دار انجام می‌شود: `001_initial_mvp`، `002_harden_mvp`، بعدی‌ها `003_xxx` و …
2. نسخه Migration بین ۰۰۱ و ۸۹۹ و Seed توسعه بین ۹۰۰ و ۹۹۹ است. نسخه‌های ۰۰۰ و ۱۰۰۰ به بالا رد می‌شوند.
3. هر Migration در تراکنش جداگانه اجرا و همراه Checksum ثبت می‌شود. Migration اجراشده تغییرناپذیر است؛ ترتیب‌شکنی (نسخه کمتر از آخرین اجراشده) رد می‌شود.
4. Seed توسعه فقط با `--include-dev-seed` اجرا می‌شود و در محیط Production (`TRADEFLOW_ENV=prod|production`) رد می‌شود.
5. هم‌زمانی چند Runner با قفل Advisory جلوگیری می‌شود.
6. Migration 003 (ستون `organizations.code`، ADR-059) نوشته و روی PostgreSQL 16 تست شده است (`003_org_code_and_username.sql`، ۱۴۰۵/۰۷/۱۸). جدول‌های مدل فیزیکی وضعیت پس از 001+002 را نشان می‌دهند و ستون `code` و CHECK نام‌کاربری را شامل نیستند؛ مرجع آن‌ها `SLICE_01_CONTRACT.md` بخش ۳.۱ است.
