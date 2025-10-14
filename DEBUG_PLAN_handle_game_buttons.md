# 🐛 DEBUG PLAN: handle_game_buttons()

**File:** `games.py`  
**Lines:** 272-558  
**Complexity:** HIGH (handles all 4 crypto games, multiple phases)  
**Priority:** 🔴 CRITICAL

---

## 1. FUNCTION PURPOSE

### What It Should Do:
Handle ALL button interactions for crypto games (dice, basketball, football, bowling):
- Setup phase buttons (mode selection, points selection, confirmation)
- Challenge phase buttons (accept, cancel, play again, double bet)
- In-game phase buttons (roll dice, take shot, kick, bowl)

### Inputs:
- `update: Update` - Telegram update object with callback query
- `context: ContextTypes.DEFAULT_TYPE` - Bot context with user_data and bot_data

### Outputs:
- None (async function, sends messages/edits inline keyboards)

### Dependencies:
- `user_games` dict in `context.bot_data` - Maps (chat_id, user_id) → game_key
- `games` dict in `context.bot_data` - Maps game_key → game_state
- `pending_challenges` dict in `context.bot_data` - Maps game_id → challenge info
- User balance from `payments.py`

---

## 2. TRACE POINTS (Add Logging)

### Entry Point Logging:
```python
logger.info(f"🎮 GAME BUTTON CLICKED: data={data}, user={user_id}, chat={chat_id}")
logger.debug(f"   user_data keys: {list(context.user_data.keys())}")
logger.debug(f"   bot_data keys: {list(context.bot_data.keys())}")
```

### Game Type Detection:
```python
logger.info(f"✅ GAME BUTTON: Detected game_type={game_type}")
# OR
logger.warning(f"❌ GAME BUTTON: Unknown game type for data={data}")
```

### Phase Detection:
```python
if setup_key in context.user_data:
    logger.info(f"📝 SETUP PHASE: User has active setup")
elif data.startswith(f"{game_type}_roll_"):
    logger.info(f"🎲 IN-GAME PHASE: Roll button clicked")
elif data.startswith(f"{game_type}_accept_"):
    logger.info(f"✅ CHALLENGE PHASE: Accept button clicked")
```

### Game State Logging:
```python
logger.info(f"🎮 GAME STATE: {game}")
logger.info(f"   Current player: {game['current_player']}")
logger.info(f"   Scores: {game['scores']}")
logger.info(f"   Round: {game['round_number']}")
logger.info(f"   Message ID: {game.get('message_id')}")
```

### Decision Points:
```python
# Before validation checks
logger.debug(f"🔍 Validating: message_id={query.message.message_id} vs game={game.get('message_id')}")
logger.debug(f"🔍 Validating: player_key={player_key} vs current={game['current_player']}")
logger.debug(f"🔍 Validating: turn_round={turn_round} vs game round={game['round_number']}")

# After each validation
if validation_failed:
    logger.warning(f"⚠️ VALIDATION FAILED: {reason}")
```

### Exit Points:
```python
# Success
logger.info(f"✅ GAME BUTTON: Processed successfully")

# Early return
logger.warning(f"⚠️ GAME BUTTON: Early return - {reason}")

# Error
logger.error(f"❌ GAME BUTTON: Error - {str(e)}", exc_info=True)
```

---

## 3. TEST CASES

### Happy Path Tests:

#### Test 1: Complete Game Flow (Normal Mode)
```
Steps:
1. User A: /dice 2
2. User A: Select "Normal" mode
3. User A: Select "1 point"
4. User A: Confirm setup
5. User A: Click "Challenge"
6. User A: Type "@UserB"
7. User B: Click "Accept"
8. User A: Click "Roll Dice"
9. User B: Click "Roll Dice"
10. System: Evaluate round, determine winner

Expected: Game completes, winner gets prize, balance updated

Trace: Full logs from entry to winner announcement
```

#### Test 2: Double Mode (2 Rolls Per Player)
```
Steps:
1-7. Same as Test 1
8. User A: Click "Roll Dice" (1st roll)
9. System: Show "Roll again" button
10. User A: Click "Roll Dice" (2nd roll)
11. User B: Click "Roll Dice" (1st roll)
12. System: Show "Roll again" button
13. User B: Click "Roll Dice" (2nd roll)
14. System: Evaluate round

Expected: Both players roll twice, correct scoring

Trace: Verify roll_count increments correctly
```

#### Test 3: Multi-Round Game (First to 3 Points)
```
Steps:
1. Setup game with "First to 3 points"
2. Play multiple rounds
3. Verify score tracking across rounds
4. Verify round_number increments
5. Verify game ends at 3 points

Expected: Scores persist, game ends correctly

Trace: Round transitions, score updates
```

### Edge Case Tests:

#### Test 4: Message ID Validation
```
Scenario: Old button clicked after new message sent

Steps:
1. User A rolls (message 1)
2. System sends "User B's turn" (message 2)
3. User A clicks button on message 1 again

Expected: "Šis mygtukas ne tau!" error

Trace: message_id comparison logs
```

#### Test 5: Wrong Turn
```
Scenario: User clicks when it's not their turn

Steps:
1. User A's turn (current_player = 'player1')
2. User B clicks "Roll Dice"

Expected: "Ne tavo eilė!" error

Trace: player_key vs current_player check
```

#### Test 6: Insufficient Balance
```
Scenario: Challenge user with low balance

Steps:
1. User A has $10 balance
2. User A: /dice 20
3. System should block setup

Expected: Error about insufficient funds

Trace: Balance check logs
```

#### Test 7: Both Players Already Playing
```
Scenario: User already in another game

Steps:
1. User A in active game with User C
2. User B challenges User A
3. User A clicks "Accept"

Expected: "Vienas iš jūsų jau žaidžia!" error

Trace: user_games dictionary check
```

#### Test 8: Challenge Cancellation
```
Scenario: Cancel a pending challenge

Steps:
1. User A challenges User B
2. User B clicks "Cancel"
3. Verify challenge removed from pending_challenges

Expected: Challenge cancelled, no game created

Trace: pending_challenges dict before/after
```

### Error Case Tests:

#### Test 9: Missing Game State
```
Scenario: Game state lost (bot restart)

Steps:
1. Start game
2. Simulate bot restart (clear bot_data)
3. User clicks "Roll Dice"

Expected: "Žaidimas nerastas!" error

Trace: game_key lookup failure
```

#### Test 10: Corrupted Game State
```
Scenario: Game state missing required fields

Steps:
1. Manually corrupt game dict (remove 'current_player')
2. User clicks button

Expected: Graceful error, not crash

Trace: KeyError handling
```

#### Test 11: Telegram API Failure
```
Scenario: send_dice() fails

Steps:
1. Mock send_dice to raise exception
2. User clicks "Roll Dice"

Expected: Error message to user, game state preserved

Trace: Exception handling logs
```

---

## 4. ISOLATION & MOCKING

### Can This Function Be Tested Independently?
**Partially** - Requires mocking:
- Telegram Update/CallbackQuery objects
- Context with bot_data
- Balance check functions from payments.py

### Required Mocks:
```python
# Mock Update object
mock_update = Mock(spec=Update)
mock_update.callback_query = Mock()
mock_update.callback_query.from_user.id = 12345
mock_update.callback_query.message.chat_id = -100123
mock_update.callback_query.message.message_id = 678
mock_update.callback_query.data = "dice_roll_1"

# Mock Context
mock_context = Mock()
mock_context.bot_data = {
    'games': {},
    'user_games': {},
    'pending_challenges': {}
}
mock_context.user_data = {}

# Mock payments functions
with patch('games.get_user_balance', return_value=100.0):
    with patch('games.update_user_balance'):
        await handle_game_buttons(mock_update, mock_context)
```

### Test Harness:
```python
# test_games.py
import pytest
from unittest.mock import Mock, patch, AsyncMock
from games import handle_game_buttons

@pytest.mark.asyncio
async def test_roll_dice_happy_path():
    # Setup
    update = create_mock_update("dice_roll_1", user_id=123, chat_id=-100)
    context = create_mock_context_with_active_game()
    
    # Execute
    await handle_game_buttons(update, context)
    
    # Assert
    assert context.bot.send_dice.called
    assert "game updated correctly"
```

---

## 5. IDENTIFIED ISSUES & FIXES

### Issue 1: Message ID Not Updated (FIXED)
**Problem:** After first player rolls, new message sent for second player, but `game['message_id']` not updated  
**Fix:** Update `message_id` after sending new message (lines 532, 556)  
**Status:** ✅ FIXED (2025-10-14)

### Issue 2: Setup Key Cleanup Timing (FIXED)
**Problem:** `setup_key` deleted before challenge created, causing validation to fail  
**Fix:** Only delete `setup_key` AFTER challenge is sent (line 963)  
**Status:** ✅ FIXED (2025-10-14)

### Issue 3: Decimal/Float Type Mismatch (FIXED)
**Problem:** `game['bet']` (float) subtracted from `get_user_balance()` (Decimal)  
**Fix:** Convert to Decimal before arithmetic (line 587)  
**Status:** ✅ FIXED (2025-10-14)

### Issue 4: No Timeout for Abandoned Games
**Problem:** If player doesn't respond, game stuck forever  
**Solution:** Implement 10-minute timeout with APScheduler  
**Status:** ⚠️ NOT IMPLEMENTED

### Issue 5: No Game State Persistence
**Problem:** Bot restart loses all active games  
**Solution:** Save active games to database  
**Status:** ⚠️ NOT IMPLEMENTED

### Issue 6: Insufficient Error Handling
**Problem:** Missing try-except blocks in critical sections  
**Solution:** Wrap risky operations (API calls, balance updates)  
**Status:** ⚠️ NOT IMPLEMENTED

---

## 6. RECOMMENDED IMPROVEMENTS

### Short Term (1-2 days):
1. **Add comprehensive logging** (as outlined in Section 2)
2. **Add try-except blocks** around:
   - `context.bot.send_dice()`
   - `context.bot.send_message()`
   - `update_user_balance()`
   - `get_chat_member()`
3. **Add validation helper**:
   ```python
   def validate_game_state(game: dict) -> bool:
       required_keys = ['player1', 'player2', 'current_player', 'scores', 'round_number']
       return all(key in game for key in required_keys)
   ```

### Medium Term (1 week):
1. **Split function** - too long (286 lines)
   - Extract setup phase → `handle_setup_buttons()`
   - Extract challenge phase → `handle_challenge_buttons()`
   - Extract in-game phase → `handle_ingame_buttons()`
2. **Add game state validation** before processing
3. **Implement timeout mechanism**

### Long Term (2+ weeks):
1. **Database persistence** for active games
2. **Unit tests** for each game phase
3. **Refactor to OOP** - Create `Game` class
4. **Add metrics** - track success/failure rates

---

## 7. DEBUGGING CHECKLIST

When a bug is reported for this function:

- [ ] Check logs for entry point (button clicked)
- [ ] Verify game_type detected correctly
- [ ] Check which phase (setup/challenge/in-game)
- [ ] Verify game_key exists in user_games
- [ ] Verify game state exists in games dict
- [ ] Check game state has all required fields
- [ ] Verify message_id matches
- [ ] Check current_player matches player_key
- [ ] Verify turn_round matches game round_number
- [ ] Check balance before/after operations
- [ ] Look for exceptions in logs
- [ ] Verify Telegram API responses

---

## 8. MONITORING & ALERTS

### Metrics to Track:
- Games started per hour
- Games completed vs abandoned
- Average game duration
- Error rate by game type
- Balance discrepancies

### Alert Conditions:
- Error rate > 5%
- Game duration > 30 minutes (stuck game)
- Balance mismatch detected
- Missing game state errors

---

**Status:** ✅ DEBUG PLAN COMPLETE  
**Last Updated:** 2025-10-14  
**Next Review:** After next bug report or major refactor

