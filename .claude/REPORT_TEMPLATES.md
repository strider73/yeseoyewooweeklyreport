# Report Templates

Reference for daily and weekly report formats used by the Python report scripts (`reports/`).
Reports are delivered via n8n workflows: SMS daily (10pm), Email+SMS weekly (Saturday 9pm).

---

## Daily SMS Report (per child)

Sent nightly at 10pm AEST. Shows today's totals with 7-day rolling averages and trend arrows.

### Format

```
[Name] Daily Report - Mon DD (Day)

Study: XhYm (7d avg: XhYm)
  Subject1  XhYm  arrow (avg XhYm)
  Subject2  XhYm  arrow (avg XhYm)
  ...

Workout: XhYm (7d avg: XhYm)
  Type1  XhYm

Rest: XhYm (7d avg: XhYm)
```

### Trend Arrows
- `↑` — more than 10% above 7-day average
- `↓` — more than 10% below 7-day average
- `→` — within 10% of average (on track)
- `NEW` — no prior history for this item

### Examples with Data

```
[Yewoo] Daily Report - Feb 13 (Fri)

Study: 3h0m ↓ (7d avg: 5h12m)
  Maths    2h0m  → (avg 2h0m)
  Chem     1h0m  ↓ (avg 1h48m)
  Physics    -   ↓ (avg 36m)
  Reading    -   ↓ (avg 14m)

Workout: 3h0m ↑ (7d avg: 42m)
  Tennis   3h0m
  Jogging    -

Rest: 0m
```

```
[Yeseo] Daily Report - Feb 13 (Fri)

Study: 3h30m ↓ (7d avg: 4h18m)
  Piano    1h30m → (avg 1h18m)
  Chem       30m ↓ (avg 1h0m)
  Methods     -  ↓ (avg 30m)
  Lit         -  ↓ (avg 24m)
  Comp        -  ↓ (avg 12m)

Workout: 0m ↓ (7d avg: 30m)

Rest: 1h30m
  Nap 1h30m
```

### Edge Cases
- No data for today: `[Name] No activities logged today.`
- Fewer than 3 days of history: show averages with `(limited data)` note
- Routine category entries are combined into Rest for display

---

## Weekly SMS Report

Sent Saturday at 9pm AEST. Shows both children in one message with weekly totals and 4-week averages.

### Format

```
Weekly Report: Mon DD - Mon DD

[Name]
Study: XhYm arrow (4wk avg: XhYm)
  Subject1 XhYm arrow | Subject2 XhYm arrow
  ...
Workout: XhYm arrow (4wk avg: XhYm)
  Type Sessions Total arrow
Days active: X/7 (4wk avg: X/7)

[Name]
...
```

### Example

```
Weekly Report: Feb 9 - Feb 15

[Yewoo]
Study: 22h30m ↑ (4wk avg: 19h45m)
  Maths    10h0m ↑ | Chem    7h30m ↑
  Physics   3h30m → | JMSS    1h0m NEW
  Reading   1h10m →
Workout: 5h30m ↑ (4wk avg: 2h30m)
  Jogging 4x 2h0m → | Tennis 1x 3h0m NEW
Days active: 5/7 (4wk avg: 4.5/7)

[Yeseo]
Study: 16h30m → (4wk avg: 17h0m)
  Piano    7h30m ↑ | Chem    4h0m ↓
  Methods  2h30m → | Lit     2h0m ↑
  Comp     1h0m  ↓ | Legal     -  ↓
Workout: 1h30m ↓ (4wk avg: 2h15m)
  Jogging 3x 1h30m ↓
Rest: 7h45m ↑ (4wk avg: 5h30m)
Days active: 6/7 (4wk avg: 5.5/7)
```

---

## Weekly HTML Email Report

Sent Saturday at 9pm AEST alongside the SMS. Comprehensive formatted email with summary cards, breakdowns, and daily view.

### Structure
1. **Summary cards** per child — Study (blue #E3F2FD), Workout (green #E8F5E9), Rest (orange #FFF3E0)
2. **Study breakdown table** — Subject | This Week | 4wk Avg | Trend
3. **Workout breakdown table** — Type | Sessions | Total Time
4. **Daily breakdown table** — Day | Study | Workout | Rest
5. Korean names in parentheses: "Yewoo (여우)", "Yeseo (예서)"
6. Font: Arial, sans-serif; max-width: 600px

### HTML Template

```html
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">

<h2 style="color: #333;">Weekly Report: Feb 9 - Feb 15</h2>

<!-- Per child block -->
<div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
  <h3 style="color: #2196F3; margin-top: 0;">Yewoo (여우)</h3>

  <!-- Summary Bar -->
  <table style="width: 100%; margin-bottom: 16px;">
    <tr>
      <td style="text-align: center; padding: 8px; background: #E3F2FD; border-radius: 4px;">
        <div style="font-size: 24px; font-weight: bold;">22h40m</div>
        <div style="font-size: 12px; color: #666;">Study</div>
        <div style="color: green; font-size: 14px;">↑ vs 20h avg</div>
      </td>
      <td style="text-align: center; padding: 8px; background: #E8F5E9; border-radius: 4px;">
        <div style="font-size: 24px; font-weight: bold;">5h</div>
        <div style="font-size: 12px; color: #666;">Workout</div>
        <div style="color: #888; font-size: 14px;">→ vs 4h30m avg</div>
      </td>
      <td style="text-align: center; padding: 8px; background: #FFF3E0; border-radius: 4px;">
        <div style="font-size: 24px; font-weight: bold;">0m</div>
        <div style="font-size: 12px; color: #666;">Rest</div>
        <div style="font-size: 14px;">-</div>
      </td>
    </tr>
  </table>

  <!-- Study Breakdown -->
  <h4 style="margin-bottom: 4px;">Study Breakdown</h4>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
    <tr style="background: #f5f5f5;">
      <th style="text-align: left; padding: 4px 8px;">Subject</th>
      <th style="text-align: right; padding: 4px 8px;">This Week</th>
      <th style="text-align: right; padding: 4px 8px;">4wk Avg</th>
      <th style="text-align: center; padding: 4px 8px;">Trend</th>
    </tr>
    <!-- Rows generated dynamically -->
  </table>

  <!-- Workout Breakdown -->
  <h4 style="margin-bottom: 4px;">Workout Breakdown</h4>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
    <tr style="background: #f5f5f5;">
      <th style="text-align: left; padding: 4px 8px;">Type</th>
      <th style="text-align: right; padding: 4px 8px;">Sessions</th>
      <th style="text-align: right; padding: 4px 8px;">Total Time</th>
    </tr>
    <!-- Rows generated dynamically -->
  </table>

  <!-- Daily Breakdown -->
  <h4 style="margin-bottom: 4px;">Daily Breakdown</h4>
  <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
    <tr style="background: #f5f5f5;">
      <th style="padding: 4px;">Day</th>
      <th style="padding: 4px;">Study</th>
      <th style="padding: 4px;">Workout</th>
      <th style="padding: 4px;">Rest</th>
    </tr>
    <!-- Rows generated dynamically -->
  </table>
</div>

<!-- Second child block follows same pattern -->

</body>
</html>
```

---

## n8n Integration

| Report | Trigger | Command | Output |
|--------|---------|---------|--------|
| Daily | Cron 22:00 AEST | `python daily_report.py --format json` | JSON with per-child SMS text |
| Weekly | Cron Saturday 21:00 AEST | `python weekly_report.py --format json` | JSON with per-child SMS + HTML |

- `DB_PASSWORD` set as environment variable in n8n Execute Command node
- Scripts output to stdout; n8n captures stdout
- Exit code 0 = success, non-zero = error
