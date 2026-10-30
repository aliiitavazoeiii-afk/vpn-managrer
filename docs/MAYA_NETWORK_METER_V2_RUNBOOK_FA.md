# اندازه‌گیری ترافیک واقعی کارت شبکه برای سه مایا — V2

**وضعیت:** سورس در GitHub ثبت شده؛ هنوز نصب و اندازه‌گیری زنده روی production تأیید نشده است. در این راهکار، هیچ شمارنده X-UI برای سهمیه دیتاسنتر استفاده نمی‌شود.

## معماری

- روی هرکدام از سرورهای `maya1`, `maya-s3` (مایا ۳), `maya4` سنسور Python بسیار سبک `/usr/local/libexec/hesab-net-meter` فقط مقدار `/sys/class/net/IFACE/statistics/rx_bytes` و `tx_bytes` را می‌خواند؛ هیچ daemon، پورت جدید، آدرس listening، تغییر iptables/X-UI یا عامل با مجوز root دائم ندارد.
- یک اکانت کم‌دسترسی `hesab-meter` فقط کلید ED25519 مخصوص همان سرور را می‌پذیرد؛ `authorized_keys` دارای `from="5.10.248.50",restrict,command="..."` است. کلید و فایل تنظیمات مرکزی در `/root/.ssh` و `/root/.config` محفوظ‌اند. هویت host SSH باید **از کنسول خود سرور** با اثر انگشت مستقل تأیید شود. SSH reverse/push یا رمز مشترک وجود ندارد.
- سرور مدیریت هر دقیقه با یک `systemd timer` مستقل به هر مایا متصل می‌شود، RX/TX خام را خوانده و state دوره‌ای را در `/var/lib/hesab-maya-net-meter-v2/state.json` ذخیره می‌کند. فقط آمار محدود را اتمیک در `maya_extra_sync/phase1/status.json` قرار می‌دهد. صفحه V4 از همان endpoint موجود `/control-room/phase1/status` استفاده می‌کند.
- در کارت‌های اتاق کنترل مقدار مصرف سهمیه، درصد و باقی‌مانده همراه با برچسب «حدودی» نشان داده می‌شوند. آستانه ۱۰ گیگ **هشدار داخل اتاق کنترل** می‌دهد. هنوز کانال Push به گوشی ایجاد نشده است.

## نکته تعیین‌کننده: تعریف دیتاسنتر از دانلود

`RX` یعنی ورود بایت به کارت شبکه VPS و `TX` یعنی خروج آن. برای VPN، دانلود کاربر غالباً در TX VPS دیده می‌شود؛ اما برخی دیتاسنترها در پنل خود «download» را از دید VPS و در نتیجه RX می‌نامند. تا زمانی که دو نمونه پنل دیتاسنتر با رشد RX/TX مقایسه نشده است، **هیچ جهتی به صورت پیش‌فرض کسر نمی‌شود**.

شمارنده کارت شبکه با مقدار دقیق صورتحساب لزوماً برابر نیست: VLAN، سربار شبکه، ترافیک سیستم، تعداد کارت شبکه و روش فروشنده ممکن است فرق کنند. سیستم برای چنین حالتی صادقانه برچسب `estimated` دارد و نباید با ضریب ساختگی اصلاح شود.

## آماده‌سازی: تشخیص کارت شبکه روی هر مایا

روی **خود هر سرور** (با جایگزین کردن مایا/آدرس مقصد):

```bash
ip -4 route get 5.10.248.50
ip -br link
ip -s link
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

نام کارت شبکه اصلی که ترافیک اینترنت دیتاسنتر را حمل می‌کند (مثلاً `ens160` یا `eth0`) را یادداشت کن. `tun0` و `lo` برای محاسبه سهمیه دیتاسنتر مناسب نیستند. نام واقعی را از سرور بگیر، فرض نکن.

## نصب بخش مرکزی — روی سرور حساب VPN 5.10.248.50

از یک checkout با commit ثابت و پس از اجرای syntax/preflight:

```bash
bash <REPO_CHECKOUT>/scripts/install_maya_net_meter_hub_v2.sh
```

نصب‌کننده از UI قبلی backup می‌گیرد، فقط app را recreate می‌کند، منطق محاسبه و راه‌انداز pairing را کپی می‌کند و systemd سرویس/تایمر را **غیرفعال** آماده می‌کند. پس از نصب، تا وصل شدن واقعی سه سنسور سراغ شروع تایمر نرو. هیچ رکورد مالی/X-UI تغییر نمی‌کند.

## Pair هر سرور ایران

روی **سرور مدیریت** (برای هر مایا با NIC/IP/پورت SSH واقعی):

```bash
cd /opt/vpn-control-center
bash scripts/maya_net_meter_pair_v2.sh maya1 94.184.4.38 ACTUAL_NIC [SSH_PORT]
bash scripts/maya_net_meter_pair_v2.sh maya-s3 ACTUAL_MAYA3_IP ACTUAL_NIC [SSH_PORT]
bash scripts/maya_net_meter_pair_v2.sh maya4 ACTUAL_MAYA4_IP ACTUAL_NIC [SSH_PORT]
```

قبل از پذیرفتن SSH host key، اثر انگشت نمایش‌داده‌شده با fingerprint کنسول سرور مقصد مطابقت داشته باشد. اسکریپت کلید اختصاصی می‌سازد، به root مقصد فقط برای کپی‌کردن سنسور متصل می‌شود و پس از ایجاد حساب محدود، اتصال sensor را تست می‌کند. اگر از قبل کلید همین اکانت تحت محدودیت دیگری ثبت شده باشد، installer fail-closed می‌شود.

## شروع نمونه‌برداری بدون تعیین سهمیه

```bash
systemctl start hesab-maya-net-meter-v2.service
python3 /opt/vpn-control-center/scripts/maya_net_meter_manage_v2.py status
systemctl enable --now hesab-maya-net-meter-v2.timer
systemctl list-timers --all | grep hesab-maya-net-meter
```

در این مرحله باید RX و TX مستقل روی هر سرور افزایش یابد. **تا زمان تأیید جهت قابل‌صورتحساب، باقی‌مانده همچنان «—» است.** چند دقیقه بعد مقدار RX/TX را با دو عدد در پنل دیتاسنتر مقایسه کن.

## تعیین سهمیه برای دوره جدید

برای هر سرور ابتدا از خود دیتاسنتر بگیر: سقف ترافیک دوره `TOTAL_GB`، مقدار مصرف‌شده **در لحظه شروع مبنا** `ALREADY_USED_GB`، شناسه دوره `PERIOD_ID` و جهت قابل‌صورتحساب `rx` یا `tx`. سپس:

```bash
cd /opt/vpn-control-center
python3 scripts/maya_net_meter_manage_v2.py quota maya1 PERIOD_ID TOTAL_GB ALREADY_USED_GB rx
python3 scripts/maya_net_meter_manage_v2.py quota maya-s3 PERIOD_ID TOTAL_GB ALREADY_USED_GB rx
python3 scripts/maya_net_meter_manage_v2.py quota maya4 PERIOD_ID TOTAL_GB ALREADY_USED_GB rx
systemctl start hesab-maya-net-meter-v2.service
python3 scripts/maya_net_meter_manage_v2.py status
```

`rx` در مثال صرفاً جایگزین قابل تعویض است: اگر دیتاسنتر **خروجی از سرور** را حساب کند باید `tx` بگذاری. از مقادیر واقعی استفاده کن، نه عدد آزمایشی. در ابتدای دوره baseline گرفته می‌شود؛ تغییر سهمیه در همان دوره (top-up) مصرف انباشته را پاک نمی‌کند. تغییر جهت یا مبنای اولیه با همان شناسه دوره ممنوع است و باید شناسه مبنای جدید با مقدار تأییدشده از دیتاسنتر ثبت شود.

## در صورت ری‌استارت سرور یا reset کارت شبکه

مقادیر قبل از ری‌استارت حفظ می‌شوند. اما چون ممکن است ترافیک فاصله آخرین نمونه تا reset قابل بازسازی نباشد، وضعیت `uncertain_reset` می‌گیرد و نمایش «باقی‌مانده دقیق» متوقف می‌شود. پس از تطبیق مقدار جاری دیتاسنتر، با یک `period_id` **جدید و مصرف اولیه واقعی همان لحظه** دوره محاسبه را دوباره مبناگذاری کن.

**محدوده این فاز:** مستقل از X-UI، هشدار وب ۱۰ گیگ، پایش سه مایا. هنوز پیام Push اندروید یا کشف خرابی VPN/Xray End-to-End جزو این نصب نیست.
