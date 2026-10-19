# تابلوی اختیار — پلتفرم شخصی تحلیل اختیار معامله بورس تهران

زنجیره قراردادها (Call/Put بر اساس سررسید و قیمت اعمال)، نوسان ضمنی (IV) و یونانی‌ها با مدل بلک‌شولز، و ماشین‌حساب سود و زیان استراتژی؛ بک‌اند FastAPI و فرانت‌اند Next.js + Tailwind (راست‌به‌چپ).

## ساختار پروژه

```
option-platform/
├── backend/
│   ├── main.py              # FastAPI: REST + WebSocket
│   ├── calculator.py        # بلک‌شولز، دلتا/گاما/تتا/وگا، IV، نمودار سود و زیان
│   ├── tsetmc_collector.py  # دریافت و تجزیه داده بازار اختیار از TSETMC
│   ├── chain_builder.py     # ساخت نردبان قیمت اعمال + IV/یونانی‌ها + ITM/ATM/OTM
│   ├── service.py           # حلقه دریافت داده، کش، تاریخچه، پخش به WebSocket
│   ├── cache.py             # Redis (اختیاری) یا کش درون‌حافظه‌ای
│   ├── database.py          # SQLite (پیش‌فرض) یا PostgreSQL
│   ├── demo_collector.py    # داده نمایشی با همان قالب TSETMC
│   ├── schemas.py           # مدل‌های Pydantic
│   ├── config.py            # تنظیمات از متغیرهای محیطی / فایل .env
│   ├── tests/               # ۱۰۲ تست
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── page.tsx                 # داشبورد دارایی‌های پایه
    │   ├── option-chain/page.tsx    # زنجیره قراردادها
    │   └── payoff-calc/page.tsx     # ماشین‌حساب سود و زیان
    ├── components/
    │   ├── OptionChainTable.tsx     # جدول زنجیره (کامپوننت اصلی)
    │   ├── OptionChainView.tsx      # انتخاب نماد/سررسید + وضعیت زنده
    │   ├── PayoffBuilder.tsx        # ویرایشگر موقعیت‌ها
    │   └── PayoffChart.tsx          # نمودار SVG
    ├── hooks/useOptionChain.ts      # WebSocket با بازگشت به polling
    ├── lib/                         # api.ts، format.ts (ارقام فارسی، تاریخ شمسی)
    ├── package.json
    └── tailwind.config.js
```

## اجرا

### بک‌اند (پایتون ۳٫۱۰ به بالا)

ویندوز (PowerShell):

```powershell
cd option-platform\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # تنظیمات را در .env ویرایش کنید
uvicorn main:app --reload
```

لینوکس / مک:

```bash
cd option-platform/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

مستندات تعاملی API: http://127.0.0.1:8000/docs

### فرانت‌اند (Node.js ۲۰٫۹ به بالا)

```bash
cd option-platform/frontend
npm install
npm run dev
```

سپس http://localhost:3000 را باز کنید. اگر بک‌اند جای دیگری اجرا می‌شود، `.env.local.example` را به `.env.local` کپی و `NEXT_PUBLIC_API_URL` را عوض کنید.

## حالت نمایشی

برای کار روی رابط کاربری بدون TSETMC (بازار بسته، خارج از ایران، آفلاین) در `.env` بنویسید `OPTIONS_SOURCE=demo`. داده نمایشی ساختگی است، از همان تجزیه‌گر داده زنده عبور می‌کند و در بالای صفحه با نشان «داده نمایشی» مشخص می‌شود.

## اولین اتصال به داده زنده TSETMC

این بخش را من نتوانستم از محیط خودم آزمایش کنم، چون TSETMC از بیرون ایران در دسترس نیست. اندپوینت و نام فیلدها از کتابخانه متن‌باز `tseopt` گرفته شده‌اند و API غیررسمی است، پس در اولین اجرا این‌ها را بررسی کنید:

1. بک‌اند را روی ماشینی با اینترنت داخل ایران اجرا کنید و `OPTIONS_SOURCE=live` بگذارید.
2. آدرس `http://127.0.0.1:8000/api/health` را باز کنید. `status: "ok"` و `contracts` بزرگ‌تر از صفر یعنی همه‌چیز درست است. اگر خطا بود، متن آن در `last_error` است.
3. اگر قراردادی نیامد، پاسخ خام را ببینید و با فیلدهای توضیح‌داده‌شده بالای فایل `tsetmc_collector.py` مقایسه کنید:

   ```powershell
   curl.exe -s https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0 -o raw.json
   ```

   اگر نام فیلدی عوض شده، فقط تابع `_parse_row` در همان فایل باید تغییر کند. قالب تاریخ سررسید هم چند حالت را می‌پذیرد (میلادی فشرده، ISO، شمسی، یا تاریخ داخل نام قرارداد).

فاصله دریافت پیش‌فرض ۵ ثانیه است؛ هر درخواست کل بازار اختیار را برمی‌گرداند، پس نیازی به درخواست جدا برای هر نماد نیست.

## تنظیمات مهم (`.env`)

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `OPTIONS_SOURCE` | `live` | `live` داده TSETMC، `demo` داده نمایشی |
| `POLL_INTERVAL_SECONDS` | `5` | فاصله دریافت داده |
| `RISK_FREE_RATE` | `0.30` | نرخ بدون ریسک سالانه؛ **فرض است، نه داده بازار**؛ خودتان تنظیم کنید |
| `DIVIDEND_YIELD` | `0` | بازده سود نقدی سالانه دارایی پایه |
| `IV_PRICE_SOURCE` | `mid` | قیمتی که IV از آن حساب می‌شود: `mid` (میانگین خرید و فروش)، `last`، `close` |
| `UNDERLYING_PRICE_SOURCE` | `last` | قیمت «فعلی» دارایی پایه: `last` یا `close` |
| `DATABASE_URL` | `sqlite:///./options.db` | برای PostgreSQL: `postgresql+psycopg://user:pass@localhost/options` و `pip install "psycopg[binary]"` |
| `REDIS_URL` | خالی | خالی یعنی کش درون‌حافظه‌ای. Redis روی ویندوز رسمی نیست، برای همین اختیاری است |

## API

| مسیر | کار |
|---|---|
| `GET /api/health` | وضعیت دریافت داده (`ok` / `stale` / `starting`) |
| `GET /api/underlyings` | دارایی‌های پایه دارای اختیار و سررسیدهایشان |
| `GET /api/option-chain?underlying=&expiry=` | نردبان Call/Put یک سررسید (بدون `expiry` نزدیک‌ترین) |
| `POST /api/payoff` | منحنی سود و زیان در سررسید، سر به سر، حداکثر سود و زیان |
| `GET /api/contracts/{ins_code}/history` | تاریخچه ذخیره‌شده قیمت و IV یک قرارداد |
| `WS /ws/option-chain/{underlying}?expiry=` | ارسال نردبان بعد از هر دریافت داده |

## فرض‌های مدل و محدودیت‌ها

- اختیار معامله سهام در بورس تهران اروپایی است (اعمال فقط در سررسید)، بنابراین بلک‌شولز مستقیم قابل استفاده است. زمان تا سررسید برابر «روز تقویمی باقی‌مانده ÷ ۳۶۵» است.
- یونانی‌ها: دلتا و گاما نسبت به یک ریال تغییر قیمت پایه؛ تتا به ازای یک روز؛ وگا به ازای یک واحد درصد تغییر IV (همه به ریال برای هر سهم).
- بازار اختیار کم‌عمق است و قیمت‌ها گاهی پرت‌اند؛ IV قراردادهای کم‌معامله ممکن است نویزی باشد. با نگه داشتن ماوس روی ستون IV می‌بینید از کدام قیمت محاسبه شده.
- ماشین‌حساب سود و زیان کارمزد، مالیات و وجه تضمین را لحاظ نمی‌کند.
- سیستم احراز هویت ندارد و برای استفاده محلی ساخته شده است (CORS فقط برای `localhost:3000` باز است).

## تست

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

