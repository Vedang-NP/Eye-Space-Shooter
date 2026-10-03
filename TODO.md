# Task Steps

- [x] Analyze project files and dependencies
- [x] Confirm plan with user
- [x] Create `eye_tracker.py` (non-blocking eye tracking module)
- [x] Write `main_game.py` (pygame rocket shooter with home page, play button, asteroids, eye-based movement)
- [x] Test by running `python -m py_compile` (syntax check passed)
- [x] Smoke test imports (both modules import without errors)
- [x] Fixed indentation bug in `eye_tracker.py` (line 71 `self.direction_history` was outside `__init__`)
- [x] Verified all modules compile cleanly (`py_compile` exit 0)
- [x] Game launched successfully via `python main_game.py`
- [x] Fixed black screen: added missing `pygame.display.flip()` to main loop
- [x] Fixed crash after a few seconds: replaced non-existent `Vector2.rotate_degrees()` with `Vector2.rotate()` in asteroid vertex generation
- [x] Verified asteroid rotation works (`rotate()` returns correct values) and game stays running
