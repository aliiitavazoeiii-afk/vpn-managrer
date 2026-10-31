# اتاق کنترل حساب VPN — فاز یک (نصب مرحله‌ای)

**وضعیت: کد آماده در GitHub، نه تأییدشده روی Production.**

## آماده برای نصب فوری (بدون تنظیم ترافیک یا دسترسی SSH جدید)

- `patches/control_room_phase1_v1.py` نمای `/control-room` را کارت‌محور می‌کند و مشکل هدر چسبنده جدول را حذف می‌کند. کنترل دقیق X-UI و جریان تأیید تطبیق موجود محفوظ‌اند.
- `/control-room/phase1/status` فقط اطلاعات محدود فایل `maya_extra_sync/phase1/status.json` را برمی‌گرداند. اگر سنسور یا سهمیه تعریف نشده باشد، «در انتظار/نامشخص» نمایش می‌دهد؛ عدد CPU/RAM یا پینگ جعلی تولید نمی‌کند.
- `scripts/install_control_room_phase1_v1.sh` با بکاپ و rollback، فقط `app` مدیریت را recreate می‌کند؛ `customer-portal`، درگاه مالی، دیتابیس و X-UI دست‌نخورده می‌مانند.
- `scripts/diagnose_phase1_maya_payments_v1.sh` بدون تغییر داده‌ها، سرویس سینک Maya و heartbeat worker فعال‌سازی و وضعیت‌های `waiting_vpn_controls` را بررسی می‌کند. پیشنهاد: قبل از نصب UI این خروجی را بگیرید.

## پایش واقعی منابع سرور ایران — نیازمند تنظیمات میزبان

دو اسکریپت آماده‌اند: `scripts/phase1_iran_remote_sensor_v1.py` (فقط Linux /proc و کارت شبکه) و `scripts/phase1_iran_metrics_collect_v1.py` (تجمیع مرکزی از SSH با StrictHostKeyChecking و یک کلید محدود مستقل).

اطلاعات ضروری برای **هر سرور ایران**:

1. IP جدید قطعی، اینترفیس خروجی واقعاً قابل‌محاسبه (مثل `ens160`) و SSH host fingerprint تأییدشده از کنسول خود سرور.
2. سقف ترافیک خریداری‌شده به GB، میزان مصرف واقعی تا شروع پایش از پنل فروشنده، تاریخ شروع/پایان دوره، و اینکه فروشنده دقیقاً چه ترافیکی را حساب می‌کند (RX، TX، هر دو، نرخ افزوده، یا API).
3. یک کلید SSH *جدید با دسترسی فقط‌خواندنی*؛ کلید فعلی X-UI tunnel صرفاً برای همان کار است و نباید برای اجرای فرمان عمومی استفاده شود.
4. برای تست واقعی VPN، کانفیگ قابل تست و معتبر هر مسیر باید جداگانه فقط روی سرور مدیریت/ایران در محل محرمانه تنظیم شود؛ در GitHub یا چت منتشر نشود.

### نحوه استفاده از سنسور (پس از اتصال امن)

روی هر میزبان ایران فایل سنسور را از GitHub بردارید و توسط root در مسیر `/usr/local/sbin/hesab-phase1-sensor` قرار دهید (اجرایی و متعلق به root، بدون امکان نوشتن توسط حساب سنسور). کاربر اختصاصی `hesab-probe` ایجاد کرده، فقط کلید عمومی مربوط به همین سنسور را در `authorized_keys` با محدودیت `restrict,command="/usr/local/sbin/hesab-phase1-sensor ens160"` ثبت کنید (اینترفیس واقعی را جایگزین کنید). SSH fingerprint را مستقل از خود میزبان بررسی کنید.

> برای اجرای `python` به‌عنوان فایل دارای مجوز اجرا، باید shebang `#!/usr/bin/env python3` حفظ شود. هیچ پنل یا دیتابیس X-UI برای خواندن CPU و RAM نیاز نیست.

در میزبان مدیریت، تنظیمات مخفی در `/root/.config/hesab-phase1.json` با مجوز 0600، مثلاً:

```json
{
  "servers": {
    "maya1": {
      "role": "iran",
      "host": "IP_FROM_SERVER_CONSOLE",
      "ssh_port": 22,
      "ssh_user": "hesab-probe",
      "ssh_identity": "/root/.ssh/hesab_phase1_iran",
      "interface": "ens160",
      "quota_gb": null,
      "used_at_start_gb": null
    },
    "maya-s3": {"role": "foreign"},
    "maya4": {"role": "foreign"}
  }
}
```

این فقط **نمونه** است: نقش و جغرافیای واقعی سرورها باید تأیید شود. بعد از نصب سنسور و اعتماد SSH، اجرای دوره‌ای `python3 /opt/vpn-control-center/scripts/phase1_iran_metrics_collect_v1.py` یک فایل وضعیت فقط‌خواندنی برای UI می‌سازد؛ **این کار هنوز به‌صورت Cron/Timer فعال نشده است**. اطلاعات مانیتورینگ پس از تنظیم واقعی باید با کنترل دو سویه آزمایش شود.

**دقت حجم باقی‌مانده:** شمارنده NIC = مصرف سطح شبکه، لزوماً برابر مصرف محاسبه‌شده توسط فروشنده نیست؛ می‌تواند شامل بسته‌های مدیریتی/ترافیک نامرتبط باشد. بعد از شروع پایش، مقدار خروجی تا تأیید منبع فروشنده فقط با برچسب «حدودی» نمایش داده می‌شود. اگر سرور reboot شود یا شمارنده reset گردد، به‌جای پیش‌بینی قطعی، وضعیت نامطمئن نمایش داده می‌شود.

## ارسال هشدار به اپ و آزمون Xray

- در کد فعلی اپ پیامک اندروید، مسیر مشخصی برای **دریافت Push Notification هشدار سرور** وجود ندارد. صرف قرارگرفتن هشدار در UI به معنی دریافت اعلان گوشی نیست. برای تحویل واقعی باید کانال امن دریافت/اعلان برنامه بررسی و جداگانه پیاده‌سازی و آزمایش شود.
- پایش سلامت پنل 3x-ui فقط می‌گوید پنل در دسترس هست یا نه؛ **پینگ موفق به پنل به معنای سالم‌بودن مسیر VPN نیست**. برای آزمون end-to-end، یک Xray مستقل با کانفیگ کاربر-تست و مسیر مشخص از داخل سرور ایران لازم است. در غیاب کانفیگ `probe_state=not_configured` می‌ماند.
- هیچ Auto-disable گروهی، روشن‌کردن بدون تطبیق یا بازیابی اکانت مبهم در این فاز اجرا نمی‌شود.

## پرداخت و سینک Maya1 — منشأ خرابی را پیش از اصلاح کنترل شناسایی کنید

- کد فعلی auto-restore فقط اکانت‌هایی را روشن می‌کند که قبلاً با قطع دستیِ ثبت‌شده در `waiting_vpn_controls` غیرفعال شده‌اند و بعد از قطع، پرداخت مثبت، تسویه و انقضای معتبر دارند. اکانتی که در خارج از این مسیر خاموش شده، هیچ journal معتبری ندارد و نباید خودکار روشن شود.
- پس از جابه‌جایی IP مایا ۱، ابتدا تایید میزبان SSH، پروتکل HTTPS/SSH X-UI، مسیر پنل، شناسه‌ها و نمونه واقعیِ پرداخت انجام شود. تایمر/مکانیزم ۳۰ ثانیه‌ای فقط وقتی به کار می‌افتد که worker واقعاً در عمر FastAPI فعال باشد.
- فقط بعد از دیدن خروجی تشخیصی بدون داده حساس، روی مورد مشخص تعمیر و آزمون می‌کنیم. اسکریپت‌های قدیمی با mapping ثابت ۱۴۵ حساب را بر اساس X-UI جدید بدون تایید بازسازی نکنید.


## V3 — بازگشت جدول + فیلترهای تحلیلی (2026-10-30، فقط کد؛ هنوز نصب زنده تأیید نشده)

- `patches/control_room_table_v3.py` به آخر `patches/maya1_control.py` اضافه می‌شود و **فقط** رابط `/control-room` و مقدارهای تحلیلی خروجی خواندنی `/control-room/v2/data` را تکمیل می‌کند؛ همه مسیرهای اقدام X-UI/پرداخت بدون تغییر می‌مانند.
- طرح کاربران دوباره جدولی است؛ ستون‌های خلاصه نام اکانت، شناسه مالی، وضعیت، مصرف امروز، مصرف ۳۰ روز، آخرین اتصال و کنترل را دارد. ستون‌های حجیم «مصرف کل» و «نرخ» از جدول مخفی ولی در پنجره جزئیات قابل نمایش‌اند. سربرگ *چسبنده نیست* و جدول در عرض کم اسکرول افقی می‌شود تا سرستون روی اطلاعات نیفتد. سه کارت سرور/کارت‌های پایش فاز یک حفظ شده‌اند.
- **برای هر سرور به صورت مستقل**: جست‌وجو، حالت فیلتر و ترتیب به صورت مرورگری نگه داشته می‌شود. فیلترها: همه، رتبه امروز، رتبه ۳۰ روز، بیشتر از ۴۸ ساعت بدون اتصال **با زمان ثبت‌شده قابل اعتماد**، آخرین اتصال نامشخص، مصرف غیرعادی امروز.
- ردیف «جزئیات» تمام اطلاعات قبلی + سهمیه XUI، آپلود/دانلود کل، نرخ، میانگین روزهای معتبر قبلی، سررسید و نسبت به سابقه را نشان می‌دهد. همه متن‌های حساب با `textContent` درج می‌شوند، نه HTML تزریقی. تطبیق دستی و تغییر وضعیت با guardهای قبلی دست‌نخورده‌اند. دو گزارش تکراری «پرمصرف‌ترین امروز/۳۰ روز» از صفحه حذف می‌شوند (خود فیلتر رتبه‌بندی جایگزین است).
- **منطق مصرف غیرعادی:** فقط با حداقل ۳ روز سابقه معتبر از ۷ روز پیش از امروز، هر روز با حداقل ۲۴ نمونه موجود، امروز بیش از `max(2 GiB, 3 × میانگین روزهای معتبر)` باید باشد. این فقط یک پرچم آماری هشدار است، نه قطع خودکار، تشخیص اشتراک‌گذاری یا اثبات مصرف بیش از سهمیه فروشنده؛ تاریخچه ناکافی = غیرقابل ارزیابی. SQLite فقط خوانده می‌شود.
- نصب `scripts/install_control_room_table_v3.sh` باید از یک Git commit **ثابت** با بکاپ، پیش‌بررسی روی کد واقعی production و rollback در صورت شکست باشد. فقط سرویس `app` بازسازی بدون build می‌شود. تست ایزوله `scripts/test_control_room_table_v3.py` و CI کنترل Jinja/JS و سه حالت anomaly را انجام می‌دهند.
- سورس GitHub و preflight به تنهایی به معنای موفقیت نصب production یا تأیید مرورگر نیستند؛ بعد از `SUCCESS: CONTROL ROOM TABLE V3 INSTALLED` جدول/فیلترهای واقعی در مرورگر و یک نمونه سابقه تست شود.


## V4 — یکپارچه‌سازی طراحی کارت‌های اصلی با خود اتاق کنترل (2026-10-30)

- **وضعیت: کد در GitHub، نیازمند نصب/تأیید کاربر روی production.**
- همان ساختار گرافیکی کارت‌های `focus-server-card` نمای اصلی (حلقه، آمار منابع و باکس‌های ظرفیت) در `/control-room` استفاده می‌شود. به جای ۸ سرور آزمایشی `IR-1..4` و `Foreign-1..4`، **فقط ۳ شناسه واقعی** `maya1`, `maya-s3` (= مایا ۳), `maya4` نمایش می‌یابند. چون نقش جغرافیایی هر سرور از config معتبر اعلام نشده، در UI با عنوان دقیق «سرورهای تحت مدیریت» نمایش داده می‌شوند؛ ادعای نادرست ایران/خارج نداریم.
- داده اکانت‌ها از **همان** `/control-room/v2/data` و broker زنده، شامل آمار کل، فعال و تطبیق، می‌آیند. موفقیت X-UI فقط به معنی پاسخ‌گویی پنل است، **نه** تأیید عملکرد end-to-end کانفیگ VPN.
- برای CPU/RAM یک منبع سریع‌تر و بدون نصب Agent کشف شد: API مستند 3x-ui `GET /panel/api/server/status`. فایل `scripts/maya_xui_host_metrics_v1.py` با اتصال موجود `maya_multi_panel_sync.py` فقط GET می‌زند (HTTPS معتبر یا verified SSH local forward). تنها اعداد sanitized را در `maya_extra_sync/phase1/xui_status_v1.json` ثبت می‌کند، اطلاعات رمز/کلاینت/پاسخ کامل ذخیره نمی‌شوند. برای پنل‌های ناسازگار وضعیت `unavailable` نشان داده می‌شود. Cron هر ۲ دقیقه، endpoint admin `/control-room/v4/host-metrics` بازخوانی فایل فقط‌خواندنی را فراهم می‌کند.
- حلقه درصد و ترافیک باقی‌مانده تا نصب و تأیید quota provider واقعی «—» است؛ API `server/status` مصرف رابط شبکه را می‌دهد، **نه لزوماً سهمیه خریداری‌شده نزد ارائه‌دهنده**. هیچ هشدار Push، Auto-off یا تست VPN end-to-end در V4 ساخته نشده است.
- UI قبلی فاز یک، V3 جدول، جست‌وجوی مستقل و فیلترهای ۴۸ ساعت/امروز/۳۰ روز/غیرعادی، پنجره جزئیات، CSRF و عملیات دقیق X-UI حفظ می‌شوند. با انتخاب کارت سرور، جدول همان سرور نمایش داده می‌شود.
- `patches/control_room_live_visual_v4.py` باید **بعد از** V3 در runtime overlay `patches/maya1_control.py` اجرا شود. `scripts/install_control_room_live_visual_v4.sh` source را preflight می‌کند، بکاپ می‌گیرد، فقط سرویس `app` را recreate می‌کند، Cron read-only می‌گذارد و روی خطا rollback می‌کند. پایگاه PostgreSQL، XUI، SMS، customer-portal و طراحی صفحه اصلی تغییر نمی‌کنند.
- آزمایش ایزوله `scripts/test_control_room_live_visual_v4.py` قالب واقعی V2→Phase1→V3→V4 را بدون network اجرا می‌کند و Jinja/inline JS و API read-only را بررسی می‌کند. تست کارکرد مرورگر و تأیید ۳ سرور فقط بعد از نصب واقعی امکان‌پذیر است.


## V5 — RX/TX readouts visible before billing-direction calibration

Diagnosed 2026-10-31 from operator samples: `maya1` RX 1.437 GB TX 1.396 GB; `maya-s3` RX 1.166 GB TX 1.167 GB; `maya4` RX 0.709 GB TX 0.695 GB (observations from an earlier moment, not current numbers). Meter state was `direction_unconfirmed` on all servers and no remaining value appeared on website.

**Root cause:** `/control-room/phase1/status` whitelisted only `traffic_used_gb`, `remaining_gb`, `traffic_quota_gb`, CPU/RAM, but not `rx_period_gb` and `tx_period_gb`. V4 `quotaUsable` additionally requires an operator-confirmed billing period/direction. As a result, NIC data was captured properly on Linux yet invisible in V4 cards.

**Remedy:** additive read-only route `GET /control-room/v5/nic-traffic` reads `/srv/maya-live/phase1/status.json` with fresh-age (<= 180 s), format, type and range checks. It provides only sanitized three-server RX/TX samples. `patches/control_room_nic_live_v5.py` patches existing V4 cards to display both measurements even while billing direction remains unconfirmed; warning text distinguishes uncalibrated/stale/unavailable values. Existing remaining GB continues to show `—` until direction and baseline are confirmed, no financial effects. Installer `scripts/install_control_room_nic_live_v5.sh` refuses absent V4/M2 prerequisites, requires three real samples in the admin container preflight, backs up existing overlay, recreates only app and rolls back on runtime verification failure. CI includes full template chain Jinja/inline JS sanity test `scripts/test_control_room_nic_live_v5.py`.

**Caution:** Provider balance snapshot provided by operator for Maya1 144 GB, Maya3 189 GB and Maya4 144 GB has no timestamp and is NOT currently a live measured remaining balance. Do not present it as real-time or silently calculate with `rx` until billing direction and the appropriate initial balance are confirmed against provider. Never reset the NIC measurement ledger just to expose the values.


## V6 (2026-10-31) — نمایش مانده اعلامی دیتاسنتر بدون ادعای زنده بودن

مبالغ مانده اعلام‌شده کاربر در گفتگو: `maya1=144 GB`، `maya-s3=189 GB`، `maya4=144 GB` (مجموع 477GB). اینها **تاریخ مشاهده تأییدشده در پنل دیتاسنتر ندارند**؛ نباید با زمان ثبت در سرور، تاریخ مشاهده واقعی اشتباه گرفته شوند. بلافاصله پس از نصب در UI نمایش داده شوند اما با برچسب دقیق «آخرین مانده اعلامی دیتاسنتر — زنده نیست». تا کالیبراسیون RX/TX، مصرف خودکار از آنها کسر نمی‌شود و هشدار ۱۰GB بر این مبنا فعال نمی‌گردد.

- افزونه `patches/control_room_provider_reference_v6.py` فقط API محدود و خواندنی `GET /control-room/v6/provider-reference` و نمایش داخل کارت‌های V4 را اضافه می‌کند؛ با V5 نیز سازگار است. هیچ مسیر پرداخت، XUI، worker، NIC state، quota یا اعلان تغییر نمی‌کند.
- اسکریپت `scripts/maya_provider_balance_reference_v1.py` با `set 144 189 144` یک فایل محلی ذخیره می‌کند: `/opt/vpn-control-center/maya_extra_sync/phase1/provider_balance_reference_v1.json`. مقادیر در GitHub commit نمی‌شوند و گزارش قبلی هنگام تغییر backup دارد. فیلد `recorded_at` زمان ثبت در سیستم است، `provider_observed_at_known=false` باعث می‌شود UI آن را زنده جا نزند.
- installer `scripts/install_control_room_provider_reference_v6.sh 144 189 144`: پیش‌بررسی ادغام قالب روی app زنده در فرایند جدا، نسخه پشتیبان `patches/maya1_control.py` و فایل گزارش، recreate **فقط** app، احراز دقیق ارقام خوانده‌شده در داخل کانتینر و rollback خودکار. اگر قبلاً نصب باشد، فقط ارقام مرجع جدید به‌روزرسانی می‌شوند، بدون restart.
- پس از آن، برای محاسبه زنده: ابتدا جهت واقعی قابل‌صورتحساب `rx` یا `tx` و timestamp هم‌زمان با اعداد دیتاسنتر باید تأیید شود؛ سپس period-baseline با داده معتبر تعریف می‌شود. بدون این کار اعداد به روز نمی‌شوند.
- تست مستقل `scripts/test_control_room_provider_reference_v6.py` زنجیره V2→Phase1→V3→V4→M2→V5→V6 را برای syntax قالب و JavaScript و بازگرداندن reference معتبر یا ناامن بررسی می‌کند.


## V7 (2026-10-31): مانده آزمایشی کاهشی، فقط از لحظه جدید

Issue: after V6 displaying last reported provider balances `maya1=144GB, maya-s3=189GB, maya4=144GB`, values remained unchanged overnight because V6 intentionally stores a static operator-provided **historical reference**; independent NIC RX/TX counters do increment but never influence V6.

V7 implementation:
- `scripts/maya_provider_provisional_baseline_v7.py` creates a fresh, immutable RX+TX baseline on activation for all three hosts, using a current `status.json` and the operator's old V6 balance file. No attempt to infer the unmeasured time difference between historical provider observation and new baseline.
- `scripts/maya_net_meter_collect_v2.py` adds a boolean `counter_uncertain` field to the existing read-only summary; no changes to NIC accounting, XUI, finance, SSH or purchased provider quota. Expose counter-reboot/reset uncertainty in meter output even when billing direction remains unconfirmed.
- `patches/control_room_provisional_remaining_v7.py` adds read-only `GET /control-room/v7/provisional-remaining` with age/format/value/uncertainty checks, calculates `max(0, old_provider_report_gb - (current_rx_period_gb - activation_rx_baseline_gb))` ONLY when sample is fresh and no reset uncertainty. UI labels it “برآورد موقت از مرجع قدیمی · RX”, with 0.001GB display precision; retains old reference on unavailable reading. Never treats this provisional estimate as verified, and **does not trigger 10GB alerts**.
- `scripts/install_control_room_provisional_remaining_v7.sh` refuses already-baselined/mismatched collector, verifies the 1-minute timer is active, runs an isolated admin preflight, takes app+collector backups, replaces only the collector and app patch and initialises a fresh immutable baseline, recreates only `app`, verifies route and readback then rolls back on error.
- `scripts/test_control_room_provisional_remaining_v7.py` verifies full Jinja/JS overlay chain, forward subtraction, RX-only assumption, reset fail-closed, and disabled alerts.
- **Crucial limitation:** last night's time of provider observation has not been established. Therefore V7 is a *moving trend from activation*, not reliable actual remaining GB. Avoid using for automatic network cutoff decisions or provider expiry alerts. For accurate remaining GB, obtain the **current provider balance** concurrently with RX/TX sample, determine provider-billed direction, then configure approved quota baseline; do not pretend historical usage can be backfilled.


## V8: گزارش تازه کاربر و تنظیم دوباره مبنای RX به‌صورت صریح (2026-10-31)

کاربر از پنل دیتاسنتر مانده‌های تازه اعلام کرده است: `maya1=82 GB`, `maya-s3=140 GB`, `maya4=137.66 GB`. مانده‌های قبلی (از شب گذشته): `144/189/144 GB`. تفاوت‌ها: `62/49/6.34 GB`. مجموع جدید `359.66 GB`. **این مقادیر در زمان گفتگوی کاربر از پنل اعلام شده‌اند اما وقت دقیق مشاهده با snapshot سنسور یکی نشده است**. زمان گرفتن snapshot نباید زمان مشاهده دیتاسنتر جا زده شود.

`scripts/maya_operator_rebaseline_v8.py --apply 82 140 137.66` در صورت نصب V7:
- وضعیت واقعی `maya_extra_sync/phase1/status.json` را با نمونه تازه (<=120s)، سنسورهای سالم، `counter_uncertain=false`, و `direction_unconfirmed` بررسی می‌کند.
- به صورت صریح و اتمیک هم فایل V6 گزارش `provider_balance_reference_v1.json` و هم فایل مبنای V7 `provisional_meter_baseline_v7.json` را به مانده‌های جدید و شمارنده RX *لحظه ثبت مبنا* وصل می‌کند. فایل‌های قبلی را در `/root/hesab-maya-v8-rebaseline-...` بکاپ می‌گیرد و هنگام شکست نوشتن، rollback می‌کند. هیچ تغییر روی `/var/lib/hesab-maya-net-meter-v2/state.json`، quota مالی، خرید ترافیک، XUI، یا VPN نمی‌دهد. بدون restart، در بارگذاری بعدی API تغییر اعمال می‌شود.
- V7 عدد تقریبی جدید را از `new_reported_remaining - post_rebaseline_RX` حساب می‌کند. `rx` فقط فرض قبلی است؛ به همین علت خطای ممکن نسبت به مانده واقعی دیتاسنتر را اعلام می‌کند و هشدار خودکار ۱۰GB همچنان غیرفعال است.
- اگر V7 نصب نبوده، ابتدا V6 reference را با `scripts/maya_provider_balance_reference_v1.py set 82 140 137.66` به‌روزرسانی کن و V7 guarded installer را اجرا کن؛ سپس دستور rebaseline V8 بزن. وقتی V7 نصب است هیچ نصب مجدد و app restart لازم نیست.
- تست محافظتی `scripts/test_maya_operator_rebaseline_v8.py` برای اعداد جدید، backup، نوشتن جفتی، امتناع از سنسور stale/reset و عدم دستکاری داده‌های قبلی در مسیر CI وجود دارد.

هیچ عدد مرجع اعلام‌شده شب گذشته نباید به‌عنوان «مانده زنده» معرفی شود؛ بعد از V8 هم برای صحت حسابداری باید افت واقعی پنل دیتاسنتر و `RX/TX` در یک بازه یکسان مقایسه شوند.
