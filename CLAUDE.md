# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pygame rocket shooter steered by eye gaze. The webcam feed goes through MediaPipe FaceMesh to classify gaze as `"Left"`, `"Center"`, `"Right"` or `"No Face"`, and that string drives the rocket.

## Commands

There is no dependency manifest, test suite, linter config, or build step. Dependencies are `pygame`, `opencv-python` and `mediapipe`.

The system `python3` is 3.14, which does not work for this project: the code uses the legacy `mp.solutions.face_mesh` API, which is absent from every mediapipe release installable on 3.14 (0.10.30 and later), and `pygame` has no 3.14 wheel. Use the project's `.venv` (Python 3.12, `mediapipe==0.10.21`), created with `uv`:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python "mediapipe==0.10.21" pygame opencv-python

.venv/bin/python main_game.py        # the game (needs a webcam and a display)
.venv/bin/python eye_detection.py    # standalone gaze debug window, press q to quit

.venv/bin/python -m py_compile main_game.py eye_tracker.py eye_detection.py   # only automated check available
```

Moving to a newer mediapipe means porting both gaze files to the Tasks API (`FaceLandmarker`), which also needs a downloaded model file.

Both entry points open webcam index 0 and a GUI window, so they cannot be exercised headlessly. `py_compile` plus an import smoke test is how changes have been verified so far (see `TODO.md`).

## Architecture

Three files, two of which hold the same gaze logic:

- `eye_detection.py` is the original prototype: a script with module-level side effects (opens the camera and enters a blocking `while True` loop at import). Never import it. It is kept as a debugging tool for tuning gaze detection visually.
- `eye_tracker.py` is that logic repackaged as `EyeTracker`, which runs capture + FaceMesh in a daemon thread and exposes results through the lock-guarded `get_state()` / `get_direction()`. This is what the game uses.
- `main_game.py` holds the `Game` state machine (`home` → `playing` → `game_over`), the `Rocket` / `Bullet` / `Asteroid` classes, and all drawing. All tuning constants (speeds, spawn rate, lives, window size) are at the top of the file.

The landmark indices, the 0.40 / 0.60 ratio thresholds and the 5-frame majority-vote smoothing are duplicated between `eye_detection.py` and `eye_tracker.py`. A change to gaze detection has to be made in both to keep the debug tool representative of the game.

### Gaze detection

Only the right iris is used (`RIGHT_IRIS` landmarks 469–472, which require `refine_landmarks=True`). The iris centre's horizontal position between that eye's corners (33 and 133) gives a 0–1 ratio: below 0.40 is Left, above 0.60 is Right. The frame is flipped horizontally before processing so that directions match the player's perspective, and the corner x-values are min/max-sorted so the ratio is independent of the flip. The `LEFT_*` constants are defined but unused. There is no vertical gaze detection.

### Control mapping (`Game.update`)

- Gaze Left/Right moves the rocket; held arrow keys override gaze.
- Gaze `"Center"` auto-fires (subject to `BULLET_COOLDOWN`), as does Space. Looking straight ahead therefore shoots continuously.
- `P` returns to the home screen rather than pausing; clicking PLAY (or pressing Enter) from there calls `start_game()`, which resets score and lives.
- The game loop runs at 60 FPS and counts time in frames (`ASTEROID_SPAWN`, `BULLET_COOLDOWN` are frame counts).

### Rendering

Everything is drawn procedurally; there are no image assets. Asteroids, the rocket, hearts, glows and the nebula backdrop are built once with numpy into cached pygame surfaces (lit from the upper left), then blitted each frame. Text, panels and glows go through module-level caches in `main_game.py` (`render_text`, `draw_panel`, `get_glow`), so use those helpers instead of creating fonts or surfaces inside the frame loop.

The camera overlay reads `EyeTracker.get_frame()`, the frame the tracker thread already captured. Do not call `tracker.cap.read()` from the game loop: it blocks on the camera and dropped the game to about 15 FPS when it was done that way.

Visual changes can be checked without a webcam or window by setting `SDL_VIDEODRIVER=dummy`, replacing `sys.modules["eye_tracker"]` with a stub `EyeTracker` before importing `main_game`, and saving `game.screen` with `pygame.image.save`.

### Known rough edges

- `EyeTracker` opens the camera in `__init__`, and `Game.__init__` constructs and starts it, so the webcam is live from the home screen onward.
- `cap.release()` is called both at the end of `_run` and in `stop()`.
- Collision uses axis-aligned bounding rects for everything, including the round asteroids. Asteroid radius is 24–51 px (`ASTEROID_MIN_RADIUS` / `ASTEROID_MAX_RADIUS`) and the drawn outline is lumpy, so hits do not match the visible edge exactly.
