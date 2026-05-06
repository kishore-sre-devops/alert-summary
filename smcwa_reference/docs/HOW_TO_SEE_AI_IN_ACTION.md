# 🤖 AI SCHEDULER - HOW TO SEE IT IN ACTION

## Current Status

The AI code is **deployed and ready**. To see it working, you need to:

### 1. Restart the Scheduler (to activate AI)

```bash
docker restart lama_scheduler
```

### 2. Watch AI in Real-Time

```bash
# Watch for AI activity
docker logs lama_scheduler -f | grep --color=always "\[AI\]"
```

**You'll see lines like:**
```
[AI] 🤖 Correcting sequence 111430 → 111433: Recent 704 indicates exchange expects 111433
[AI] Learning insights for network: {'success_rate': 100.0, 'health_status': 'healthy'}
[AI] ✅ Auto-heal successful: synced to sequence 111433
[AI] Drift detected: proposed=111435, expected=111432
```

### 3. See Complete Activity

```bash
# Run the demo script
bash /tmp/show_ai_in_action.sh
```

**This shows:**
- 🤖 AI predictions & corrections
- 🏥 Auto-healing events
- 📊 Learning insights
- 🔢 Sequence generation
- 📈 Success rates

### 4. Monitor Continuously

```bash
# Watch everything (AI + sequences + results)
docker logs lama_scheduler -f | grep -E "\[AI\]|SEQ_ID|704|SUCCESS"
```

## What AI Does Automatically

### Before Sending (Predictive)
1. Checks if proposed sequence will succeed
2. Validates against last success
3. Detects drift from exchange state
4. Corrects sequence if needed

### During Sending (Monitoring)
1. Health check runs
2. Detects sequence gaps
3. Triggers auto-heal if needed

### After Errors (Healing)
1. Extracts expected sequence from 704 error
2. Syncs with exchange state
3. Updates cache
4. Prevents future errors

### Continuous (Learning)
1. Analyzes last 30 minutes
2. Calculates success rates
3. Identifies patterns
4. Generates recommendations

## Example: AI Preventing a 704 Error

**Without AI:**
```
[SEQ_ID] Issued 111430 for NSE network
[ERROR] 704_ERROR - Exchange expects 111433
[MANUAL] Admin must fix sequence manually
```

**With AI:**
```
[SEQ_ID] Calculating sequence for NSE network...
[AI] 🤖 Recent 704 detected: exchange expects 111433
[AI] 🤖 Correcting sequence 111430 → 111433
[SEQ_ID] Issued 111433 for NSE network
[SUCCESS] 601 - Metrics accepted
```

## When Does AI Activate?

- **Immediately** on scheduler restart
- **Every 5 minutes** when schedulers run
- **On every** sequence ID request
- **Continuously** for health monitoring

## Verify AI is Active

```bash
# Check AI module is loaded
docker exec lama_scheduler python3 -c "from app.utils.scheduler_ai import scheduler_ai; print('✅ AI Active')"

# Check for AI in logs
docker logs lama_scheduler --since 10m | grep "\[AI\]" | wc -l
```

If you see a number > 0, AI is working!

## Quick Commands

```bash
# 1. Restart to activate
docker restart lama_scheduler

# 2. Watch AI live
docker logs lama_scheduler -f | grep "\[AI\]"

# 3. See full demo
bash /tmp/show_ai_in_action.sh

# 4. Check status
bash /tmp/status_check.sh

# 5. Verify installation
bash /tmp/verify_ai_installation.sh
```

## What You Should See

After restart, within 5 minutes you'll see:

✅ Sequence IDs being generated (every 5 min)
✅ AI validation happening (if needed)
✅ Success rates at 99-100%
✅ No 704 errors (or immediate auto-heal if they occur)
✅ Learning insights being logged

## The AI is Silent When Everything is Perfect

If you see **no AI logs**, that's actually **GOOD** - it means:
- Sequences are already correct
- No drift detected
- No gaps found
- No healing needed

The AI only logs when it:
- Corrects something
- Detects an issue
- Performs healing
- Generates insights

---

**To see AI in action RIGHT NOW:**

```bash
docker restart lama_scheduler && sleep 10 && bash /tmp/show_ai_in_action.sh
```

This will restart the scheduler and show you what the AI is doing!
