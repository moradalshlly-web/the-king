# Milestone: Visual Critic

**التاريخ:** 2 أكتوبر 2026

## ما تحقق

ناقد بصري يعطي كل موقع درجة (0-10) من 5 زوايا.

## المكونات

### brain/visual_critic.py (523 سطر)

**طبقة 1: تحليل ثابت (بلا LLM)**
- structure، design_system، accessibility، content، responsive

**طبقة 2: نقد LLM**
- درجة جمالية عامة (0-10) + نقاط قوة + اقتراحات

**النتيجة:** overall = 40% static + 60% llm

## النتائج الفعلية

اختبار على najma/index.html: **9.2/10**
- structure: 10 · design_system: 10 · content: 9 · responsive: 10
- accessibility: 7 (كشف نقص lang/dir)
- الناقد أدّى دوره — كشف مشكلة حقيقية

## الدرس

الناقد كشف أن Builder نسي `<html lang="ar" dir="rtl">`.
الإصلاح: قاعدة صريحة في Builder prompt.
