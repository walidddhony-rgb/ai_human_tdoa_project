# RUNNING.md

هذا الملف يشرح كيف تشغّل محاكاة النظام ثنائي القناة (مايكروفونين) وكيف تعيد إنشاء الرسومات الموجودة في مجلد results/.

الافتراضات المسبقة
- لديك Python 3.9 أو أحدث.
- المستودع مكلّف (clone) على جهازك.
- يُنصح بإنشاء بيئة افتراضية.

إعداد البيئة

1) إنشاء وتفعيل بيئة افتراضية (مثال باستخدام venv):

```bash
python -m venv .venv
source .venv/bin/activate   # على Linux / macOS
.venv\Scripts\activate     # على Windows (PowerShell)
```

2) تثبيت التبعيات:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

ملاحظات:
- requirements.txt يحتوي على numpy, scipy, matplotlib. إذا احتجت pandas أو مكتبات إضافية لاحقًا أضفها.

تشغيل المحاكاة الأساسية

الملف التنفيذي للمحاكاة هو `src/analog_simulation.py`.

لتشغيل المحاكاة مع الإعدادات الافتراضية:

```bash
python -m src.analog_simulation
```

ماذا تفعل هذه الأوامر؟
- تقوم بتشغيل `run_simulation()` مع `AnalogSimulationConfig()` الافتراضي.
- سينتج عن ذلك طباعة نتائج كل تجربة على الشاشة، ثم إحصاء المترجمات النهائية.

تغيير إعدادات المحاكاة (مثال)

يمكنك تعديل المتغيرات داخل `AnalogSimulationConfig` في بداية `src/analog_simulation.py` أو إنشاء ملف صغير لاستدعاء `run_simulation` بقيم مخصصة. مثال سريع لتشغيل 100 تجربة مع نطاق تأخير مختلف:

```python
# مثال: run_custom.py
from src.analog_simulation import (
    AnalogSimulationConfig,
    run_simulation,
)

config = AnalogSimulationConfig(
    trials=100,
    min_true_delay_seconds=2.0e-6,
    max_true_delay_seconds=25.0e-6,
    numerical_points=80000,
)

results = run_simulation(config=config)
```

ثم شغّل:

```bash
python run_custom.py
```

تخزين النتائج وإعادة إنتاج الرسومات

- بعض المسوحات تُخزَّن في ملف CSV داخ�� `results/robustness_sweep.csv` أو أسماء مشابهة. سكربت `src/plot_results.py` يقرأ CSV باسم `results/robustness_sweep.csv` افتراضياً.

لإعادة إنشاء الرسومات من CSV:

```bash
python -m src.plot_results
```

ما سيحدث:
- يتم قراءة `results/robustness_sweep.csv`.
- تُنشأ خرائط حرارية وصور منحنيات جديدة في `results/`:
  - mean_error_heatmap_rebuilt.png
  - failure_rate_heatmap_rebuilt.png
  - percentile_95_heatmap.png
  - mean_error_curves_rebuilt.png

تأكد أن الملف `results/robustness_sweep.csv` موجود ويحتوي الأعمدة التالية (كمثال مستنتج من سكربت الرسم):
- channel_2_gain
- noise_std
- mean_distance_error_mm
- failure_rate_above_1mm_percent
- percentile_95_distance_error_mm

إذا كان CSV باسم آخر، افتح `src/plot_results.py` وغير قيمة `CSV_PATH` أو مرّر نسخة باسم `results/robustness_sweep.csv`.

نصائح لإعادة الإنتاج والتحقق

- التحكم بالعشوائية: `AnalogSimulationConfig.random_seed` ثابت افتراضياً (42) لضمان تكرار النتائج؛ غيّره إذا أردت نتائج مختلفة.
- ملفات النتائج القديمة: قبل إعادة تشغيل المسوحات الكبيرة، أنشئ نسخة احتياطية من `results/` أو استخدم مجلد مؤقت.
- جودة الصور: `plot_results.py` يستخدم dpi=160؛ غيّر `figure.savefig(..., dpi=...)` لو احتجت دقة أعلى.

أمثلة عملية متتابعة

1) تشغيل المحاكاة الافتراضية ثم إعادة رسم النتائج:

```bash
python -m src.analog_simulation
python -m src.plot_results
```

2) تشغيل مسح robustess (إنشاؤه) ثم إعادة الرسم (افتراض أن سكربت المسح ينتج robustness_sweep.csv):

```bash
python -m src.robustness_sweep
python -m src.plot_results
```

إضافات مقترحة (إن أردت أن أضيفها)
- سكربت CLI يقرأ ملف إعداد YAML ويشغّل تجارب متعددة مع حفظ metadata لكل تشغيل.
- توثيق تنسيق CSV وإضافة مثال CSV في `results/sample_robustness_sweep.csv`.
- أوتوماتيزم لإنشاء مجلد timestamped لكل تشغيل مع حفظ config.json و CSV و PNG.

إذا كنت تريد، سأضيف الآن ملف RUNNING.md في المستودع (أقوم بإنشائه ورفع التعديل).