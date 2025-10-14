# 🐛 DEBUG PLAN: handle_nowpayments_webhook()

**File:** `payments_webhook.py`  
**Lines:** 14-114  
**Complexity:** HIGH (handles real money, multiple payment statuses)  
**Priority:** 🔴 CRITICAL (Financial Impact)

---

## 1. FUNCTION PURPOSE

### What It Should Do:
Process NOWPayments webhook notifications and credit user balances when deposits are successful.

### Inputs:
- `data: dict` - Webhook payload from NOWPayments
- `bot` - Telegram bot instance (for notifications)

### Expected Webhook Payload:
```json
{
    "payment_id": "123456",
    "payment_status": "finished",
    "pay_amount": 0.12,
    "pay_currency": "sol",
    "price_amount": 12.00,
    "price_currency": "usd",
    "actually_paid": 12.00,
    "outcome_amount": 12.00,
    "order_id": "deposit_12345_1697123456"
}
```

### Outputs:
- `bool` - True if processed successfully, False otherwise
- Side effects: Updates database balance, sends notification

### Dependencies:
- `database.get_sync_connection()` - Database connection
- `bot.send_message()` - User notification

---

## 2. TRACE POINTS (Add Logging)

### Entry Point:
```python
logger.info(f"📥 Webhook RAW: {data}")
logger.info(f"📥 Webhook DETAILED: order_id={order_id}, status={payment_status}")
logger.info(f"   pay_amount={pay_amount} {pay_currency}")
logger.info(f"   price_amount={price_amount} {price_currency}")
logger.info(f"   outcome_amount={outcome_amount}")
logger.info(f"   actually_paid={actually_paid}")
```

### Amount Selection Logic:
```python
if price_currency == 'usd' and price_amount > 0:
    credit_amount = price_amount
    logger.info(f"💰 Using price_amount: ${credit_amount}")
elif outcome_amount > 0:
    credit_amount = outcome_amount
    logger.info(f"💰 Using outcome_amount: ${credit_amount}")
elif actually_paid > 0:
    credit_amount = actually_paid
    logger.info(f"💰 Using actually_paid: ${credit_amount}")
else:
    credit_amount = pay_amount
    logger.warning(f"⚠️ Fallback to pay_amount: ${credit_amount}")
```

### Balance Update:
```python
logger.info(f"💵 BEFORE: User {user_id} balance = ${current_balance}")
logger.info(f"💵 CREDITING: ${credit_amount}")
new_balance = current_balance + credit_amount
logger.info(f"💵 AFTER: User {user_id} balance = ${new_balance}")
```

### Notification:
```python
if bot:
    logger.info(f"📤 Sending notification to user {user_id}")
    # After send
    logger.info(f"✅ Sent notification to user {user_id}")
else:
    logger.warning(f"⚠️ No bot instance, skipping notification")
```

---

## 3. TEST CASES

### Happy Path Tests:

#### Test 1: Successful SOL Deposit ($12 USD)
```
Input:
{
    "payment_status": "finished",
    "order_id": "deposit_12345_1697123456",
    "pay_amount": 0.12,
    "pay_currency": "sol",
    "price_amount": 12.00,
    "price_currency": "usd"
}

Expected:
- Extract user_id = 12345
- Credit $12.00 to balance
- Send notification
- Return True

Trace: Verify price_amount used, not pay_amount
```

#### Test 2: Successful BTC Deposit ($50 USD)
```
Input:
{
    "payment_status": "finished",
    "order_id": "deposit_67890_1697123456",
    "pay_amount": 0.0012,
    "pay_currency": "btc",
    "price_amount": 50.00,
    "price_currency": "usd"
}

Expected:
- Extract user_id = 67890
- Credit $50.00
- Send notification
- Return True
```

#### Test 3: Partially Paid Deposit
```
Input:
{
    "payment_status": "partially_paid",
    "order_id": "deposit_11111_1697123456",
    "pay_amount": 0.08,
    "pay_currency": "sol",
    "price_amount": 10.00,
    "price_currency": "usd",
    "actually_paid": 8.50
}

Expected:
- Credit $10.00 (accept partial)
- Send notification
- Return True

Trace: Which amount is used?
```

### Edge Case Tests:

#### Test 4: Missing price_amount (NOWPayments Bug)
```
Input:
{
    "payment_status": "finished",
    "order_id": "deposit_22222_1697123456",
    "pay_amount": 0.12,
    "pay_currency": "sol",
    "price_currency": "usd",
    "outcome_amount": 12.00
}

Expected:
- Fall back to outcome_amount
- Credit $12.00
- Return True

Trace: Amount selection fallback logic
```

#### Test 5: Old order_id Format (user_12345)
```
Input:
{
    "payment_status": "finished",
    "order_id": "user_33333",
    "price_amount": 25.00,
    "price_currency": "usd"
}

Expected:
- Parse user_id = 33333
- Credit $25.00
- Return True

Trace: order_id parsing logic
```

#### Test 6: Invalid order_id Format
```
Input:
{
    "payment_status": "finished",
    "order_id": "invalid_format_abc",
    "price_amount": 10.00
}

Expected:
- Log warning
- Return False (don't credit)

Trace: order_id validation
```

#### Test 7: Missing order_id
```
Input:
{
    "payment_status": "finished",
    "price_amount": 10.00
}

Expected:
- Log warning "Missing order_id"
- Return False

Trace: Early validation
```

#### Test 8: Expired Payment
```
Input:
{
    "payment_status": "expired",
    "order_id": "deposit_44444_1697123456"
}

Expected:
- Log warning
- Don't credit
- Return True (acknowledged)
```

#### Test 9: Failed Payment
```
Input:
{
    "payment_status": "failed",
    "order_id": "deposit_55555_1697123456"
}

Expected:
- Log warning
- Don't credit
- Return True
```

#### Test 10: Duplicate Webhook (Same payment_id twice)
```
Input: Same payload sent twice

Expected:
- Credit only once
- Need to add idempotency check

Trace: Check if payment_id already processed
```

### Error Case Tests:

#### Test 11: Database Connection Failure
```
Scenario: Database unavailable

Expected:
- Log error
- Return False
- Don't lose payment data

Trace: Exception handling
```

#### Test 12: User Not in Database
```
Input: Valid webhook for user_id that doesn't exist

Expected:
- Create user with credited balance
- Or log error and hold funds

Trace: User creation/balance update
```

#### Test 13: Notification Failure (Bot API Down)
```
Scenario: Telegram API returns error

Expected:
- Balance still credited
- Log notification failure
- Return True (payment processed)

Trace: Notification error handling
```

---

## 4. ISOLATION & MOCKING

### Test Harness:
```python
# test_payments_webhook.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from payments_webhook import handle_nowpayments_webhook

@pytest.mark.asyncio
async def test_successful_deposit_usd():
    # Mock data
    webhook_data = {
        "payment_status": "finished",
        "order_id": "deposit_12345_1697123456",
        "pay_amount": 0.12,
        "pay_currency": "sol",
        "price_amount": 12.00,
        "price_currency": "usd"
    }
    
    # Mock bot
    mock_bot = AsyncMock()
    
    # Mock database
    with patch('payments_webhook.database.get_sync_connection') as mock_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (100.0,)  # Current balance
        mock_conn.execute.return_value = mock_cursor
        mock_db.return_value.__enter__.return_value = mock_conn
        
        # Execute
        result = await handle_nowpayments_webhook(webhook_data, bot=mock_bot)
        
        # Assert
        assert result is True
        # Check balance update called
        calls = [str(call) for call in mock_conn.execute.call_args_list]
        assert any('112.0' in str(call) for call in calls)  # 100 + 12
        # Check notification sent
        assert mock_bot.send_message.called
```

---

## 5. IDENTIFIED ISSUES & FIXES

### Issue 1: Using pay_amount Instead of price_amount (FIXED)
**Problem:** User deposited $12 but got $0.12 (SOL amount credited instead of USD)  
**Root Cause:** Initially used `pay_amount` (crypto) instead of `price_amount` (USD)  
**Fix:** Smart amount detection with priority: price_amount > outcome_amount > actually_paid  
**Status:** ✅ FIXED (2025-10-14)

### Issue 2: No Idempotency Check
**Problem:** Duplicate webhooks could credit balance multiple times  
**Solution:** Track processed payment_ids in database  
**Status:** ⚠️ NOT IMPLEMENTED

### Issue 3: No Retry Mechanism for Failed Notifications
**Problem:** If Telegram API fails, user never notified  
**Solution:** Queue failed notifications for retry  
**Status:** ⚠️ NOT IMPLEMENTED

### Issue 4: No Audit Trail
**Problem:** Can't verify historical payment crediting  
**Solution:** Create `payment_history` table  
**Status:** ⚠️ NOT IMPLEMENTED

### Issue 5: Float Precision Issues
**Problem:** Using float for currency (0.1 + 0.2 = 0.30000000000000004)  
**Solution:** Use Decimal for all currency operations  
**Status:** ⚠️ PARTIAL (some places still use float)

---

## 6. RECOMMENDED IMPROVEMENTS

### Short Term (1-2 days):
1. **Add payment_history table**:
   ```sql
   CREATE TABLE payment_history (
       id INTEGER PRIMARY KEY,
       payment_id TEXT UNIQUE NOT NULL,
       user_id INTEGER NOT NULL,
       amount REAL NOT NULL,
       currency TEXT NOT NULL,
       status TEXT NOT NULL,
       credited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       webhook_data TEXT
   );
   ```

2. **Add idempotency check**:
   ```python
   # Check if already processed
   cursor.execute("SELECT id FROM payment_history WHERE payment_id = ?", (payment_id,))
   if cursor.fetchone():
       logger.warning(f"⚠️ Duplicate webhook: payment_id={payment_id}")
       return True
   ```

3. **Use Decimal for all amounts**:
   ```python
   from decimal import Decimal
   credit_amount = Decimal(str(price_amount))
   ```

### Medium Term (1 week):
1. **Implement notification queue** for failed sends
2. **Add webhook signature verification** (NOWPayments IPN secret)
3. **Create admin dashboard** to view payment history
4. **Add balance reconciliation** script

### Long Term (2+ weeks):
1. **Implement automatic refunds** for failed games
2. **Add fraud detection** (unusual deposit patterns)
3. **Create financial reports** (daily/weekly/monthly)
4. **Add currency conversion history** tracking

---

## 7. DEBUGGING CHECKLIST

When a balance issue is reported:

- [ ] Check webhook logs for RAW data
- [ ] Verify which amount field was used
- [ ] Check order_id parsing (user_id extracted correctly?)
- [ ] Verify database query executed
- [ ] Check balance before/after in logs
- [ ] Verify notification sent
- [ ] Check for duplicate payment_id
- [ ] Compare NOWPayments dashboard vs database
- [ ] Check for timezone issues
- [ ] Verify currency conversion if applicable

---

## 8. MONITORING & ALERTS

### Metrics to Track:
- Webhooks received per hour
- Successful vs failed credits
- Average credit amount
- Time from payment to credit
- Notification success rate

### Alert Conditions:
- Webhook failure rate > 1%
- Credit amount mismatch detected
- Database error during credit
- No webhooks received for > 1 hour (during business hours)
- Balance reconciliation mismatch

### Dashboard Queries:
```sql
-- Daily deposits
SELECT DATE(credited_at), COUNT(*), SUM(amount)
FROM payment_history
WHERE status = 'finished'
GROUP BY DATE(credited_at);

-- Failed webhooks
SELECT * FROM payment_history
WHERE status IN ('failed', 'expired')
ORDER BY credited_at DESC
LIMIT 10;

-- Pending/stuck payments
SELECT * FROM payment_history
WHERE status NOT IN ('finished', 'failed', 'expired')
AND credited_at < datetime('now', '-1 hour');
```

---

## 9. ROLLBACK PROCEDURE

If incorrect balance credited:

1. **Query payment_history** to find transaction
2. **Manual balance correction**:
   ```sql
   -- Check current balance
   SELECT balance FROM users WHERE user_id = ?;
   
   -- Adjust balance
   UPDATE users 
   SET balance = balance - <incorrect_amount> + <correct_amount>
   WHERE user_id = ?;
   ```
3. **Document in payment_history**
4. **Notify user** of correction
5. **Investigate root cause**

---

**Status:** ✅ DEBUG PLAN COMPLETE  
**Last Updated:** 2025-10-14  
**Next Review:** After financial reconciliation or incident

